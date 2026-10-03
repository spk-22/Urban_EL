"""
Phase 2 — Multi-Layer Cascading Failure Analysis
==================================================
Run from project root: python simulations/run_phase2_analysis.py

Workflow:
  1. Build Phase-1 validated graphs (no rebuild — reuses graph_builder)
  2. Map cross-layer dependencies (D1, D2, D3)
  3. Run INDEPENDENT baselines for each layer
  4. Run COUPLED experiments (central parameters)
  5. Sensitivity analysis: dependency strengths (s_pw, s_pr) and impact parameters
  6. Export results tables and cascade progression logs to phase2_results/
"""

import os
import sys
import json
import logging
import csv
import copy
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("phase2_results/logs/phase2_run.log", mode="w", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.graph_builder import build_power_graph, build_water_graph, build_corridor_road_graph
from models.power_cascade import PowerCascadeSimulator
from models.water_cascade import WaterCascadeSimulator
from models.road_cascade import RoadCascadeSimulator
from models.dependency_mapper import (
    build_all_dependencies,
    D1_SPATIAL_THRESHOLD_M, D2_SPATIAL_THRESHOLD_M, D3_SPATIAL_BUFFER_M,
    D2_ALPHA_PR_CENTRAL, D2_ALPHA_PR_RANGE,
    D3_ALPHA_WR_CENTRAL, D3_ALPHA_WR_RANGE
)
from models.multi_layer_cascade import MultiLayerCascadeController

OUT_DIR = "phase2_results"
FIG_DIR = os.path.join(OUT_DIR, "figures")
TAB_DIR = os.path.join(OUT_DIR, "tables")
LOG_DIR = os.path.join(OUT_DIR, "logs")

SILK_BOARD_PATH = r"d:\urban el\data\processed\silk_board.geojson"
POWER_EXCEL = r"d:\new urban el\processed\power_infrastructure.xlsx"
WATER_EXCEL = r"d:\new urban el\processed\water_infrastructure.xlsx"

# Dependency strength grid (per spec Section 7)
STRENGTH_GRID = [0.0, 0.25, 0.50, 0.75, 1.00]

# Central parameter values
S_PW_CENTRAL = 0.50
S_PR_CENTRAL = 0.50
ALPHA_PR_CENTRAL = D2_ALPHA_PR_CENTRAL   # 0.30
ALPHA_WR_CENTRAL = D3_ALPHA_WR_CENTRAL   # 0.40


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def save_csv(rows, path, fieldnames=None):
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# =============================================================================
# STEP 1 — BUILD GRAPHS
# =============================================================================
def build_graphs():
    logger.info("=" * 60)
    logger.info("STEP 1: Building Phase-1 validated graphs")
    logger.info("=" * 60)
    G_power = build_power_graph(excel_path=POWER_EXCEL)
    G_water = build_water_graph(excel_path=WATER_EXCEL)
    G_road = build_corridor_road_graph(SILK_BOARD_PATH)
    logger.info(f"Power: {G_power.number_of_nodes()} nodes, {G_power.number_of_edges()} edges")
    logger.info(f"Water: {G_water.number_of_nodes()} nodes, {G_water.number_of_edges()} edges")
    logger.info(f"Road: {G_road.number_of_nodes()} nodes, {G_road.number_of_edges()} edges")
    return G_power, G_water, G_road


# =============================================================================
# STEP 2 — MAP DEPENDENCIES
# =============================================================================
def map_dependencies(G_power, G_water, G_road):
    logger.info("=" * 60)
    logger.info("STEP 2: Mapping cross-layer dependencies")
    logger.info("=" * 60)
    deps = build_all_dependencies(G_power, G_water, G_road)
    logger.info(f"D1 (Power->Water): {deps['summary']['D1_power_to_water']['n_dependencies']} pairs")
    logger.info(f"D2 (Power->Road):  {deps['summary']['D2_power_to_road']['n_dependencies']} pairs")
    logger.info(f"D3 (Water->Road):  {deps['summary']['D3_water_to_road']['n_dependencies']} pairs")

    # Save dependency evidence table
    save_csv(deps["all_records"], os.path.join(TAB_DIR, "dependency_evidence_table.csv"))
    save_json(deps["summary"], os.path.join(TAB_DIR, "dependency_summary.json"))
    logger.info("Saved dependency evidence table.")
    return deps


# =============================================================================
# STEP 3 — INDEPENDENT BASELINES
# =============================================================================
def run_independent_baselines(G_power, G_water, G_road):
    """
    Runs representative independent cascade scenarios for each layer.
    These are the Phase-1 baseline results.
    """
    logger.info("=" * 60)
    logger.info("STEP 3: Independent Baseline Experiments")
    logger.info("=" * 60)
    results = {}

    # --- Power baselines ---
    # Select representative substation: first major substation (SUB_1)
    power_subs = [n for n, d in G_power.nodes(data=True)
                  if d.get("entity_type") == "substation"]
    power_fail_scenarios = {
        "P_IND_1": [power_subs[0]] if power_subs else [],
        "P_IND_2": power_subs[:2] if len(power_subs) >= 2 else power_subs,
        "P_IND_3": power_subs[:4] if len(power_subs) >= 4 else power_subs,
    }

    power_results = {}
    for scen_id, init_fail in power_fail_scenarios.items():
        if not init_fail:
            continue
        sim = PowerCascadeSimulator(G_power, failure_threshold=1.10, stress_threshold=0.90)
        r = sim.run_cascade(init_fail)
        power_results[scen_id] = {
            "initial_failures": init_fail,
            "n_initial": len(init_fail),
            "failed_nodes": r["failed_nodes_count"],
            "failed_edges": r["failed_edges_count"],
            "failed_substations": r["failed_substations_count"],
            "total_substations": r["total_substations"],
            "stressed_nodes": r["stressed_nodes_count"],
            "stressed_edges": r["stressed_edges_count"],
            "unserved_load_mva": r["total_unserved_load_mva"],
            "cascade_rounds": r["total_rounds"],
            "converged": r["converged"],
            "substation_failure_rate": r["substation_failure_rate"],
        }
        logger.info(f"[Independent-Power] {scen_id}: failed={r['failed_nodes_count']} nodes, "
                    f"{r['failed_edges_count']} edges, rounds={r['total_rounds']}")
    results["power_independent"] = power_results

    # --- Water baselines ---
    fac_nodes = [n for n, d in G_water.nodes(data=True) if d.get("entity_type") == "facility"]
    # Find major water works (highest capacity)
    fac_caps = [(n, G_water.nodes[n].get("capacity", 0)) for n in fac_nodes]
    fac_caps.sort(key=lambda x: -x[1])
    top_facs = [f[0] for f in fac_caps[:4]]

    water_fail_scenarios = {
        "W_IND_1": [top_facs[0]] if top_facs else [],
        "W_IND_2": top_facs[:2] if len(top_facs) >= 2 else top_facs,
        "W_IND_3": top_facs[:3] if len(top_facs) >= 3 else top_facs,
    }
    water_results = {}
    for scen_id, init_fail in water_fail_scenarios.items():
        if not init_fail:
            continue
        sim = WaterCascadeSimulator(G_water, pipe_failure_threshold=1.30)
        r = sim.run_cascade(init_fail)
        water_results[scen_id] = {
            "initial_failures": init_fail,
            "n_initial": len(init_fail),
            "failed_facilities": r["failed_facilities_count"],
            "failed_pipes": r["failed_pipes_count"],
            "stressed_pipes": r["stressed_pipes_count"],
            "deprived_junctions": r["deprived_junctions_count"],
            "total_junctions": r["total_junctions"],
            "service_deprivation_rate": r["service_deprivation_rate"],
            "unmet_demand_mld": r["total_unmet_demand_mld"],
            "cascade_rounds": r["total_rounds"],
            "converged": r["converged"],
        }
        logger.info(f"[Independent-Water] {scen_id}: failed={r['failed_facilities_count']} facs, "
                    f"{r['failed_pipes_count']} pipes, deprived={r['deprived_junctions_count']}, "
                    f"unmet={r['total_unmet_demand_mld']:.1f} MLD, rounds={r['total_rounds']}")
    results["water_independent"] = water_results

    # --- Road baselines ---
    road_edges = list(G_road.edges())
    # Select edges: take edges with highest initial load/capacity ratio
    edge_vcs = [(u, v, G_road.edges[u, v].get("load_ratio", 0)) for u, v in road_edges]
    edge_vcs.sort(key=lambda x: -x[2])
    top_road_edges = [(u, v) for u, v, _ in edge_vcs[:3]]

    road_fail_scenarios = {
        "R_IND_1": [top_road_edges[0]] if top_road_edges else [],
        "R_IND_2": top_road_edges[:2] if len(top_road_edges) >= 2 else top_road_edges,
        "R_IND_3": top_road_edges[:3] if len(top_road_edges) >= 3 else top_road_edges,
    }
    road_results = {}
    for scen_id, init_fail in road_fail_scenarios.items():
        if not init_fail:
            continue
        sim = RoadCascadeSimulator(G_road, failure_threshold=1.25, stress_threshold=1.00)
        r = sim.run_cascade(init_fail)
        road_results[scen_id] = {
            "initial_failures": [list(e) for e in init_fail],
            "n_initial": len(init_fail),
            "failed_edges": r["failed_edges_count"],
            "stressed_edges": r["stressed_edges_count"],
            "total_edges": r["total_edges"],
            "disruption_ratio": r["disruption_ratio"],
            "delay_inflation_factor": r["delay_inflation_factor"],
            "cascade_rounds": r["total_rounds"],
            "converged": r["converged"],
        }
        logger.info(f"[Independent-Road] {scen_id}: failed={r['failed_edges_count']} edges, "
                    f"disruption={r['disruption_ratio']:.4f}, delay_factor={r['delay_inflation_factor']:.3f}")
    results["road_independent"] = road_results

    # Save
    save_json(results, os.path.join(LOG_DIR, "independent_baseline_results.json"))
    # Flat CSV for all independent scenarios
    all_rows = []
    for scen_id, r in power_results.items():
        r2 = dict(r); r2["scenario"] = scen_id; r2["layer"] = "Power"; all_rows.append(r2)
    for scen_id, r in water_results.items():
        r2 = dict(r); r2["scenario"] = scen_id; r2["layer"] = "Water"; all_rows.append(r2)
    for scen_id, r in road_results.items():
        r2 = dict(r); r2["scenario"] = scen_id; r2["layer"] = "Road"; all_rows.append(r2)
    save_csv(all_rows, os.path.join(TAB_DIR, "independent_baseline_summary.csv"))
    logger.info("Independent baseline results saved.")
    return results, top_facs, power_subs, top_road_edges


# =============================================================================
# STEP 4 — COUPLED EXPERIMENTS (Scenario-Matched with Independent Baselines)
# =============================================================================
def run_coupled_experiments(G_power, G_water, G_road, deps, power_subs, top_facs, top_road_edges):
    """
    Runs coupled cascade experiments with scenario-matched independent baselines.
    Scenarios are systematically chosen to test D1 (Power->Water), D2 (Power->Road),
    D3 (Water->Road), regional facilities, bottlenecks, and compound multi-layer events.
    """
    logger.info("=" * 60)
    logger.info("STEP 4: Coupled Cascade Experiments (Scenario-Matched)")
    logger.info("=" * 60)

    # 1. Identify targeted components from dependency mapper
    d1_map = deps.get("d1_map", {})
    d1_subs = sorted(list(set(d1_map.values())))
    sub_banaswadi = "SUB_25" if "SUB_25" in d1_subs else (d1_subs[0] if d1_subs else power_subs[0])
    sub_padmanabha = "SUB_19" if "SUB_19" in d1_subs else (d1_subs[1] if len(d1_subs) > 1 else power_subs[0])
    sub_uncoupled = power_subs[0] if power_subs else "SUB_1"

    # Identify D3 pipe co-located with Silk Board roads
    pipe_silkboard = None
    for u, v in G_water.edges():
        if "WJ_10511" in (u, v) or "WJ_10509" in (u, v):
            pipe_silkboard = (u, v)
            break
    if not pipe_silkboard:
        pipe_silkboard = list(G_water.edges())[0]

    fac_regional = top_facs[0] if top_facs else list(G_water.nodes())[0]
    road_bottleneck = top_road_edges[0] if top_road_edges else list(G_road.edges())[0]

    # Scenario matrix: (label, description, power_fail, water_fail, road_fail)
    scenarios = [
        (
            "S1_Power_D1_Banaswadi",
            "D1 Targeted: Substation SUB_25 (51m from BWSSB Water Tank FAC_36)",
            [sub_banaswadi], [], []
        ),
        (
            "S2_Power_D1_Padmanabha",
            "D1 Targeted: Substation SUB_19 (333m from Water Facility FAC_31)",
            [sub_padmanabha], [], []
        ),
        (
            "S3_Power_Uncoupled",
            "Uncoupled Control: Substation SUB_1 (220kV Hub, no water facility in 500m)",
            [sub_uncoupled], [], []
        ),
        (
            "S4_Water_D3_SilkBoard",
            "D3 Targeted: Transmission Main Burst near Silk Board Road corridor",
            [], [pipe_silkboard], []
        ),
        (
            "S5_Water_Facility_Regional",
            "Regional Facility: Major Water Works (240 MLD Supply Loss)",
            [], [fac_regional], []
        ),
        (
            "S6_Road_Bottleneck",
            "Road Bottleneck: Peak-flow Corridor Link Closure",
            [], [], [road_bottleneck]
        ),
        (
            "S7_Compound_PowerWater",
            "Compound Event: Concurrent Substation SUB_25 + Water Pipe Burst",
            [sub_banaswadi], [pipe_silkboard], []
        ),
    ]

    coupled_results = []
    comparison_rows = []
    coupled_jsons = {}

    for label, desc, p_fail, w_fail, r_fail in scenarios:
        logger.info(f"\n--- Scenario: {label} ({desc}) ---")

        # A. RUN COUPLED MODEL (Central Parameters)
        ctrl_coup = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=S_PW_CENTRAL,
            s_pr=S_PR_CENTRAL,
            alpha_pr=ALPHA_PR_CENTRAL,
            alpha_wr=ALPHA_WR_CENTRAL,
            power_failure_threshold=1.10,
            water_failure_threshold=1.30,
            road_failure_threshold=1.25
        )
        res_coup = ctrl_coup.run_coupled_cascade(
            initial_power_failures=p_fail,
            initial_water_failures=w_fail,
            initial_road_failures=r_fail
        )
        ss_coup = res_coup["system_summary"]
        coupled_jsons[label] = res_coup
        save_json(res_coup, os.path.join(LOG_DIR, f"coupled_{label}.json"))

        # B. RUN MATCHED INDEPENDENT BASELINE (Zero Coupling: s_pw=0, s_pr=0, alpha_wr=1.0)
        ctrl_ind = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=0.0,
            s_pr=0.0,
            alpha_pr=0.0,
            alpha_wr=1.0,
            power_failure_threshold=1.10,
            water_failure_threshold=1.30,
            road_failure_threshold=1.25
        )
        res_ind = ctrl_ind.run_coupled_cascade(
            initial_power_failures=p_fail,
            initial_water_failures=w_fail,
            initial_road_failures=r_fail
        )
        ss_ind = res_ind["system_summary"]
        save_json(res_ind, os.path.join(LOG_DIR, f"independent_{label}.json"))

        # Log summary row for coupled
        c_row = {
            "scenario": label,
            "description": desc,
            "initial_power_fail": str(p_fail),
            "initial_water_fail": str(w_fail),
            "initial_road_fail": str(r_fail),
            "s_pw": S_PW_CENTRAL, "s_pr": S_PR_CENTRAL,
            "alpha_pr": ALPHA_PR_CENTRAL, "alpha_wr": ALPHA_WR_CENTRAL,
            "outer_iterations": ss_coup["outer_iterations"],
            "system_stable": ss_coup["system_stable"],
            "power_failed_nodes": ss_coup["power_failed_nodes"],
            "power_failed_substations": ss_coup["power_failed_substations"],
            "water_failed_facilities": ss_coup["water_failed_facilities"],
            "water_failed_pipes": ss_coup["water_failed_pipes"],
            "water_unmet_demand_mld": ss_coup["water_unmet_demand_mld"],
            "water_deprived_junctions": ss_coup["water_deprived_junctions"],
            "road_failed_edges": ss_coup["road_failed_edges"],
            "road_disruption_ratio": ss_coup["road_disruption_ratio"],
            "road_delay_factor": ss_coup["road_delay_factor"],
            "total_dep_events": ss_coup["total_dep_events"],
            "d1_events": ss_coup["d1_events"],
            "d2_events": ss_coup["d2_events"],
            "d3_events": ss_coup["d3_events"],
        }
        coupled_results.append(c_row)

        # C. COMPUTE MATCHED COMPARISON METRICS
        tot_fail_ind = ss_ind["power_failed_nodes"] + ss_ind["water_failed_facilities"] + ss_ind["water_failed_pipes"] + ss_ind["road_failed_edges"]
        tot_fail_coup = ss_coup["power_failed_nodes"] + ss_coup["water_failed_facilities"] + ss_coup["water_failed_pipes"] + ss_coup["road_failed_edges"]
        delta_total = tot_fail_coup - tot_fail_ind
        rel_amp = (delta_total / max(tot_fail_ind, 1))

        delta_road = ss_coup["road_failed_edges"] - ss_ind["road_failed_edges"]
        delta_wat_fac = ss_coup["water_failed_facilities"] - ss_ind["water_failed_facilities"]
        delta_wat_pipe = ss_coup["water_failed_pipes"] - ss_ind["water_failed_pipes"]
        delta_unmet = ss_coup["water_unmet_demand_mld"] - ss_ind["water_unmet_demand_mld"]
        delta_delay = float(ss_coup["road_delay_factor"] - ss_ind["road_delay_factor"])

        # Identify mechanism
        mechs = []
        if ss_coup["d1_events"] > 0:
            mechs.append("D1:Power->Water")
        if ss_coup["d2_events"] > 0:
            mechs.append("D2:Power->Road")
        if ss_coup["d3_events"] > 0:
            mechs.append("D3:Water->Road")
        main_mech = " + ".join(mechs) if mechs else "None (Uncoupled/Isolated)"

        comp_row = {
            "scenario": label,
            "description": desc,
            # Power
            "power_failed_ind": ss_ind["power_failed_nodes"],
            "power_failed_coup": ss_coup["power_failed_nodes"],
            "delta_power_nodes": ss_coup["power_failed_nodes"] - ss_ind["power_failed_nodes"],
            # Water
            "water_fac_failed_ind": ss_ind["water_failed_facilities"],
            "water_fac_failed_coup": ss_coup["water_failed_facilities"],
            "delta_water_facs": delta_wat_fac,
            "water_pipes_failed_ind": ss_ind["water_failed_pipes"],
            "water_pipes_failed_coup": ss_coup["water_failed_pipes"],
            "delta_water_pipes": delta_wat_pipe,
            "unmet_demand_ind_mld": ss_ind["water_unmet_demand_mld"],
            "unmet_demand_coup_mld": ss_coup["water_unmet_demand_mld"],
            "delta_unmet_demand_mld": delta_unmet,
            # Road
            "road_failed_ind": ss_ind["road_failed_edges"],
            "road_failed_coup": ss_coup["road_failed_edges"],
            "delta_road_edges": delta_road,
            "delay_factor_ind": ss_ind["road_delay_factor"],
            "delay_factor_coup": ss_coup["road_delay_factor"],
            "delta_delay_factor": delta_delay,
            "disruption_ratio_ind": ss_ind["road_disruption_ratio"],
            "disruption_ratio_coup": ss_coup["road_disruption_ratio"],
            # System Total
            "total_failures_ind": tot_fail_ind,
            "total_failures_coup": tot_fail_coup,
            "delta_total_failures": delta_total,
            "relative_amplification_A": rel_amp,
            "d1_events": ss_coup["d1_events"],
            "d2_events": ss_coup["d2_events"],
            "d3_events": ss_coup["d3_events"],
            "main_mechanism": main_mech
        }
        comparison_rows.append(comp_row)
        logger.info(
            f"  [Matched Result] DeltaTotal={delta_total:+d} | "
            f"Road+{delta_road} edges | WaterUnmet+{delta_unmet:+.1f} MLD | "
            f"DelayDelta={delta_delay:+.4f} | Mechanism: {main_mech}"
        )

    save_csv(coupled_results, os.path.join(TAB_DIR, "coupled_results_central.csv"))
    save_csv(comparison_rows, os.path.join(TAB_DIR, "independent_vs_coupled_comparison.csv"))
    logger.info("Saved coupled results and scenario-matched comparison table.")
    return coupled_results, comparison_rows, coupled_jsons, scenarios


# =============================================================================
# STEP 5 — SENSITIVITY ANALYSIS
# =============================================================================
def run_sensitivity_analysis(G_power, G_water, G_road, deps, scenarios):
    """
    Systematic sensitivity analysis over:
    - Dependency strengths: s_pw on D1-coupled scenario (S1), s_pr on road signals
    - Impact parameters: alpha_wr on D3-coupled scenario (S4), alpha_pr on D2
    - Operational thresholds: Power, Water, Road thresholds
    """
    logger.info("=" * 60)
    logger.info("STEP 5: Sensitivity Analysis")
    logger.info("=" * 60)

    # Scenarios for sweeps
    s1 = [s for s in scenarios if s[0] == "S1_Power_D1_Banaswadi"][0]
    s4 = [s for s in scenarios if s[0] == "S4_Water_D3_SilkBoard"][0]
    s7 = [s for s in scenarios if s[0] == "S7_Compound_PowerWater"][0]

    all_sens_rows = []

    # 5a: s_pw Sensitivity (Power -> Water dependency strength)
    logger.info("--- 5a: s_pw Sensitivity (D1 Dependency Strength on S1) ---")
    for s_pw in STRENGTH_GRID:
        ctrl = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=s_pw, s_pr=S_PR_CENTRAL,
            alpha_pr=ALPHA_PR_CENTRAL, alpha_wr=ALPHA_WR_CENTRAL
        )
        res = ctrl.run_coupled_cascade(
            initial_power_failures=s1[2],
            initial_water_failures=s1[3],
            initial_road_failures=s1[4]
        )
        ss = res["system_summary"]
        all_sens_rows.append({
            "scenario": s1[0],
            "sweep": "s_pw_strength",
            "parameter_tested": "s_pw",
            "parameter_value": s_pw,
            "s_pw": s_pw, "s_pr": S_PR_CENTRAL,
            "alpha_pr": ALPHA_PR_CENTRAL, "alpha_wr": ALPHA_WR_CENTRAL,
            "outer_iterations": ss["outer_iterations"],
            "power_failed_nodes": ss["power_failed_nodes"],
            "water_failed_facilities": ss["water_failed_facilities"],
            "water_failed_pipes": ss["water_failed_pipes"],
            "water_unmet_demand_mld": ss["water_unmet_demand_mld"],
            "road_failed_edges": ss["road_failed_edges"],
            "road_delay_factor": ss["road_delay_factor"],
            "total_dep_events": ss["total_dep_events"],
            "d1_events": ss["d1_events"],
            "d2_events": ss["d2_events"],
            "d3_events": ss["d3_events"],
        })
    logger.info("  s_pw sensitivity done.")

    # 5b: alpha_wr Sensitivity (Water -> Road flooding impact parameter on S4)
    logger.info("--- 5b: alpha_wr Sensitivity (D3 Flooding Impact on S4) ---")
    for alpha_wr in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80]:
        ctrl = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=S_PW_CENTRAL, s_pr=S_PR_CENTRAL,
            alpha_pr=ALPHA_PR_CENTRAL, alpha_wr=alpha_wr
        )
        res = ctrl.run_coupled_cascade(
            initial_power_failures=s4[2],
            initial_water_failures=s4[3],
            initial_road_failures=s4[4]
        )
        ss = res["system_summary"]
        all_sens_rows.append({
            "scenario": s4[0],
            "sweep": "alpha_wr_impact",
            "parameter_tested": "alpha_wr",
            "parameter_value": alpha_wr,
            "s_pw": S_PW_CENTRAL, "s_pr": S_PR_CENTRAL,
            "alpha_pr": ALPHA_PR_CENTRAL, "alpha_wr": alpha_wr,
            "outer_iterations": ss["outer_iterations"],
            "power_failed_nodes": ss["power_failed_nodes"],
            "water_failed_facilities": ss["water_failed_facilities"],
            "water_failed_pipes": ss["water_failed_pipes"],
            "water_unmet_demand_mld": ss["water_unmet_demand_mld"],
            "road_failed_edges": ss["road_failed_edges"],
            "road_delay_factor": ss["road_delay_factor"],
            "total_dep_events": ss["total_dep_events"],
            "d1_events": ss["d1_events"],
            "d2_events": ss["d2_events"],
            "d3_events": ss["d3_events"],
        })
    logger.info("  alpha_wr sensitivity done.")

    # 5c: Joint Grid (s_pw x alpha_wr on Compound Scenario S7)
    logger.info("--- 5c: Joint Sensitivity Grid (s_pw x alpha_wr on S7) ---")
    for s_pw in [0.0, 0.25, 0.50, 0.75, 1.00]:
        for alpha_wr in [0.20, 0.40, 0.60]:
            ctrl = MultiLayerCascadeController(
                G_power, G_water, G_road, deps,
                s_pw=s_pw, s_pr=S_PR_CENTRAL,
                alpha_pr=ALPHA_PR_CENTRAL, alpha_wr=alpha_wr
            )
            res = ctrl.run_coupled_cascade(
                initial_power_failures=s7[2],
                initial_water_failures=s7[3],
                initial_road_failures=s7[4]
            )
            ss = res["system_summary"]
            all_sens_rows.append({
                "scenario": s7[0],
                "sweep": "joint_grid_s7",
                "parameter_tested": f"s_pw={s_pw}_alpha_wr={alpha_wr}",
                "parameter_value": s_pw,
                "s_pw": s_pw, "s_pr": S_PR_CENTRAL,
                "alpha_pr": ALPHA_PR_CENTRAL, "alpha_wr": alpha_wr,
                "outer_iterations": ss["outer_iterations"],
                "power_failed_nodes": ss["power_failed_nodes"],
                "water_failed_facilities": ss["water_failed_facilities"],
                "water_failed_pipes": ss["water_failed_pipes"],
                "water_unmet_demand_mld": ss["water_unmet_demand_mld"],
                "road_failed_edges": ss["road_failed_edges"],
                "road_delay_factor": ss["road_delay_factor"],
                "total_dep_events": ss["total_dep_events"],
                "d1_events": ss["d1_events"],
                "d2_events": ss["d2_events"],
                "d3_events": ss["d3_events"],
            })
    logger.info("  Joint grid sensitivity done.")

    # 5d: Threshold Sensitivity (Power, Water, Road thresholds)
    logger.info("--- 5d: Layer-Specific Failure Threshold Sensitivity ---")
    threshold_rows = []
    # Power failure threshold sweep
    for pft in [1.05, 1.10, 1.20]:
        ctrl = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=S_PW_CENTRAL, s_pr=S_PR_CENTRAL,
            alpha_pr=ALPHA_PR_CENTRAL, alpha_wr=ALPHA_WR_CENTRAL,
            power_failure_threshold=pft
        )
        res = ctrl.run_coupled_cascade(initial_power_failures=s1[2])
        ss = res["system_summary"]
        threshold_rows.append({
            "tested_threshold": "power_failure_threshold",
            "threshold_value": pft,
            "scenario": s1[0],
            "power_failed_nodes": ss["power_failed_nodes"],
            "water_failed_facilities": ss["water_failed_facilities"],
            "water_unmet_demand_mld": ss["water_unmet_demand_mld"],
            "road_failed_edges": ss["road_failed_edges"],
            "road_delay_factor": ss["road_delay_factor"],
        })

    # Road failure threshold sweep
    for rft in [1.15, 1.25, 1.40]:
        ctrl = MultiLayerCascadeController(
            G_power, G_water, G_road, deps,
            s_pw=S_PW_CENTRAL, s_pr=S_PR_CENTRAL,
            alpha_pr=ALPHA_PR_CENTRAL, alpha_wr=ALPHA_WR_CENTRAL,
            road_failure_threshold=rft
        )
        res = ctrl.run_coupled_cascade(initial_water_failures=s4[3])
        ss = res["system_summary"]
        threshold_rows.append({
            "tested_threshold": "road_failure_threshold",
            "threshold_value": rft,
            "scenario": s4[0],
            "power_failed_nodes": ss["power_failed_nodes"],
            "water_failed_facilities": ss["water_failed_facilities"],
            "water_unmet_demand_mld": ss["water_unmet_demand_mld"],
            "road_failed_edges": ss["road_failed_edges"],
            "road_delay_factor": ss["road_delay_factor"],
        })

    save_csv(all_sens_rows, os.path.join(TAB_DIR, "sensitivity_analysis_results.csv"))
    save_csv(threshold_rows, os.path.join(TAB_DIR, "threshold_sensitivity_results.csv"))
    logger.info(f"Sensitivity analysis complete: {len(all_sens_rows)} parameter runs and {len(threshold_rows)} threshold runs saved.")
    return all_sens_rows, threshold_rows


# =============================================================================
# STEP 6 — DEPENDENCY-INDUCED FAILURE TABLE
# =============================================================================
def build_dependency_induced_table(coupled_scenario_jsons):
    """Builds the detailed dependency-induced failure table from coupled run logs."""
    rows = []
    for label, res in coupled_scenario_jsons.items():
        for evt in res.get("dependency_events", []):
            rows.append({
                "scenario": label,
                "outer_iter": evt.get("outer_iter"),
                "dependency": evt.get("dependency"),
                "source_layer": evt.get("source_layer"),
                "source_id": evt.get("source_id"),
                "target_layer": evt.get("target_layer"),
                "target_id": evt.get("target_id"),
                "parameter": evt.get("parameter"),
                "effect": evt.get("effect"),
                "new_capacity": evt.get("new_capacity", ""),
                "original_capacity": evt.get("original_capacity", ""),
            })
    save_csv(rows, os.path.join(TAB_DIR, "dependency_induced_failure_table.csv"))
    logger.info(f"Dependency-induced failure table: {len(rows)} events saved.")
    return rows


# =============================================================================
# STEP 7 — MAIN EXECUTION
# =============================================================================
def main():
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 2 — Multi-Layer Cascading Failure Analysis")
    logger.info("=" * 70)

    # 1. Graphs
    G_power, G_water, G_road = build_graphs()

    # 2. Dependencies
    deps = map_dependencies(G_power, G_water, G_road)

    # 3. Independent Baselines
    ind_results, top_facs, power_subs, top_road_edges = run_independent_baselines(G_power, G_water, G_road)

    # 4. Coupled Experiments (Scenario-matched)
    coupled_results, comparison_rows, coupled_jsons, scenarios = run_coupled_experiments(
        G_power, G_water, G_road, deps, power_subs, top_facs, top_road_edges
    )

    # 5. Sensitivity Analysis
    sens_results, thresh_results = run_sensitivity_analysis(G_power, G_water, G_road, deps, scenarios)

    # 6. Dependency-Induced Table
    dep_induced = build_dependency_induced_table(coupled_jsons)

    # Final summary report
    logger.info("\n" + "=" * 70)
    logger.info("PHASE 2 COMPLETE — Scientific Summary")
    logger.info("=" * 70)
    logger.info(f"  Dependency pairs mapped: D1={deps['summary']['D1_power_to_water']['n_dependencies']}, "
                f"D2={deps['summary']['D2_power_to_road']['n_dependencies']}, "
                f"D3={deps['summary']['D3_water_to_road']['n_dependencies']}")
    logger.info(f"  Coupled scenarios tested: {len(coupled_results)}")
    logger.info(f"  Dependency-induced events logged: {len(dep_induced)}")
    logger.info(f"  Sensitivity runs: {len(sens_results)} parameter runs, {len(thresh_results)} threshold runs")
    logger.info(f"\n  Output directory: {os.path.abspath(OUT_DIR)}/")
    logger.info(f"  Tables: {TAB_DIR}/")
    logger.info(f"  Logs:   {LOG_DIR}/")

    logger.info("\n--- MATCHED AMPLIFICATION REPORT ---")
    for row in comparison_rows:
        logger.info(
            f"  {row['scenario']:<28} | DeltaTotal={row['delta_total_failures']:+2d} | "
            f"Road={row['delta_road_edges']:+2d} edges | "
            f"WaterUnmet={row['delta_unmet_demand_mld']:+8.1f} MLD | "
            f"DelayDelta={row['delta_delay_factor']:+7.4f} | "
            f"Mech: {row['main_mechanism']}"
        )


if __name__ == "__main__":
    main()

