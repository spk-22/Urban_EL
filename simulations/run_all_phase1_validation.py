"""
Phase 1 Validation Suite
========================
Executes systematic single-layer cascading failure tests across:
  - Road Network (Silk Board, Hebbal, ORR Corridors)
  - Power Grid (Bengaluru Transmission Network)
  - Water Network (Bengaluru BWSSB Municipal Water System)

Outputs detailed step logs, summary metrics, and publication-ready charts.
"""

import os
import sys
import json
import logging
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

# Set path and utf-8
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from models.graph_builder import (
    build_power_graph,
    build_water_graph,
    build_road_graph,
    build_corridor_road_graph
)
from models.road_cascade import RoadCascadeSimulator
from models.power_cascade import PowerCascadeSimulator
from models.water_cascade import WaterCascadeSimulator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

os.makedirs("outputs/figures", exist_ok=True)
os.makedirs("outputs/logs", exist_ok=True)
os.makedirs("outputs/reports", exist_ok=True)

# =============================================================================
# 1. RUN ROAD VALIDATION
# =============================================================================

def validate_road_layer():
    print("\n" + "="*70)
    print("PHASE 1: VALIDATING ROAD TRANSPORTATION CASCADE")
    print("="*70)
    
    # We test on the Silk Board corridor (one of India's most notoriously congested bottlenecks)
    silk_geojson = r"d:\urban el\data\processed\silk_board.geojson"
    hebbal_geojson = r"d:\urban el\data\processed\hebbal.geojson"
    
    G_road_silk = build_corridor_road_graph(silk_geojson)
    print(f"Road (Silk Board) Network: {G_road_silk.number_of_nodes()} nodes, {G_road_silk.number_of_edges()} edges.")
    
    sim_road = RoadCascadeSimulator(
        G_road_silk,
        k_routes=3,
        logit_theta=0.05,
        bpr_alpha=0.15,
        bpr_beta=4.0,
        failure_threshold=1.25,
        stress_threshold=1.00
    )

    # Find highest-betweenness / high-load edges for systematic scenario testing
    # Sample candidate edges
    sorted_edges = sorted(
        G_road_silk.edges(data=True),
        key=lambda e: e[2].get("current_load", 0.0),
        reverse=True
    )
    
    # Select 3 representative initial failure scenarios:
    # Scenario R1: Single Major Arterial Link Failure (Top-loaded edge)
    # Scenario R2: Dual Arterial Failure (Two critical bottlenecks)
    # Scenario R3: Peripheral Road Link Failure
    edge1 = (sorted_edges[0][0], sorted_edges[0][1])
    edge2 = (sorted_edges[1][0], sorted_edges[1][1])
    edge_periph = (sorted_edges[-5][0], sorted_edges[-5][1])

    scenarios = {
        "R1_Major_Arterial": [edge1],
        "R2_Dual_Arterial_Bottleneck": [edge1, edge2],
        "R3_Peripheral_Link": [edge_periph]
    }

    road_results = {}
    for sc_name, init_edges in scenarios.items():
        print(f"\n--- Running Road Scenario: {sc_name} ---")
        res = sim_road.run_cascade(init_edges, max_iterations=10)
        road_results[sc_name] = res
        print(f"  Converged: {res['converged']} in {res['total_rounds']} rounds.")
        print(f"  Failed Edges: {res['failed_edges_count']} / {res['total_edges']} ({res['disruption_ratio']*100:.2f}%)")
        print(f"  Stressed Edges: {res['stressed_edges_count']}")
        print(f"  Delay Inflation Factor: {res['delay_inflation_factor']:.3f}x")

    with open("outputs/logs/road_validation_results.json", "w") as f:
        json.dump(road_results, f, indent=2, default=str)

    return road_results, G_road_silk


# =============================================================================
# 2. RUN POWER VALIDATION
# =============================================================================

def validate_power_layer():
    print("\n" + "="*70)
    print("PHASE 1: VALIDATING POWER GRID CASCADE")
    print("="*70)

    G_power = build_power_graph(snap_tolerance_m=50.0)
    print(f"Power Network: {G_power.number_of_nodes()} nodes, {G_power.number_of_edges()} edges.")
    
    sim_power = PowerCascadeSimulator(
        G_power,
        failure_threshold=1.10,
        stress_threshold=0.90,
        headroom_gamma=1.0,
        distance_decay=1.0
    )

    # Identify candidate substations by rating / voltage
    substations = [
        (n, d) for n, d in G_power.nodes(data=True)
        if d.get("entity_type") == "substation"
    ]
    # Sort by capacity
    sorted_subs = sorted(substations, key=lambda s: s[1].get("capacity", 0.0), reverse=True)
    
    sub_major1 = sorted_subs[0][0]  # E.g. 450 MVA Substation (Peenya)
    sub_major2 = sorted_subs[1][0]  # E.g. 400 MVA Substation (HSR Layout)
    sub_minor = sorted_subs[-1][0]  # Lowest capacity substation
    
    # Also find a major transmission line
    sorted_p_edges = sorted(
        G_power.edges(data=True),
        key=lambda e: e[2].get("current_load", 0.0),
        reverse=True
    )
    major_line = (sorted_p_edges[0][0], sorted_p_edges[0][1])

    power_scenarios = {
        "P1_Major_Substation_Peenya": [sub_major1],
        "P2_Dual_Major_Substations": [sub_major1, sub_major2],
        "P3_Critical_Transmission_Line": [major_line],
        "P4_Peripheral_Substation": [sub_minor]
    }

    power_results = {}
    for sc_name, init_comps in power_scenarios.items():
        print(f"\n--- Running Power Scenario: {sc_name} ---")
        res = sim_power.run_cascade(init_comps, max_iterations=10)
        power_results[sc_name] = res
        print(f"  Converged: {res['converged']} in {res['total_rounds']} rounds.")
        print(f"  Failed Nodes: {res['failed_nodes_count']} (Substations: {res['failed_substations_count']} / {res['total_substations']})")
        print(f"  Failed Edges: {res['failed_edges_count']} / {res['total_edges']}")
        print(f"  Stressed Nodes: {res['stressed_nodes_count']}, Stressed Edges: {res['stressed_edges_count']}")
        print(f"  Total Unserved Load: {res['total_unserved_load_mva']:.1f} MVA")

    with open("outputs/logs/power_validation_results.json", "w") as f:
        json.dump(power_results, f, indent=2, default=str)

    return power_results, G_power


# =============================================================================
# 3. RUN WATER VALIDATION
# =============================================================================

def validate_water_layer():
    print("\n" + "="*70)
    print("PHASE 1: VALIDATING WATER NETWORK CASCADE")
    print("="*70)

    G_water = build_water_graph()
    print(f"Water Network: {G_water.number_of_nodes()} nodes, {G_water.number_of_edges()} edges.")
    
    sim_water = WaterCascadeSimulator(
        G_water,
        pipe_failure_threshold=1.30,
        pipe_stress_threshold=1.00,
        critical_adequacy_threshold=0.50
    )

    # Facilities sorted by capacity
    facilities = [
        (n, d) for n, d in G_water.nodes(data=True)
        if d.get("entity_type") == "facility"
    ]
    sorted_facs = sorted(facilities, key=lambda f: f[1].get("capacity", 0.0), reverse=True)
    
    fac_major1 = sorted_facs[0][0]  # E.g. Major BWSSB Water Works
    fac_major2 = sorted_facs[1][0]  # E.g. Second major plant
    fac_tank = [n for n, d in sorted_facs if "Tank" in d.get("facility_type", "")][0]

    # Major pipeline
    sorted_pipes = sorted(
        G_water.edges(data=True),
        key=lambda e: e[2].get("current_flow", 0.0),
        reverse=True
    )
    major_pipe = (sorted_pipes[0][0], sorted_pipes[0][1])

    water_scenarios = {
        "W1_Major_Water_Works": [fac_major1],
        "W2_Dual_Major_Facilities": [fac_major1, fac_major2],
        "W3_Critical_Main_Pipeline": [major_pipe],
        "W4_Local_Water_Tank": [fac_tank]
    }

    water_results = {}
    for sc_name, init_comps in water_scenarios.items():
        print(f"\n--- Running Water Scenario: {sc_name} ---")
        res = sim_water.run_cascade(init_comps, max_iterations=10)
        water_results[sc_name] = res
        print(f"  Converged: {res['converged']} in {res['total_rounds']} rounds.")
        print(f"  Failed Facilities: {res['failed_facilities_count']} / {res['total_facilities']}")
        print(f"  Failed Pipes: {res['failed_pipes_count']} / {res['total_edges']}")
        print(f"  Stressed Pipes: {res['stressed_pipes_count']}")
        print(f"  Deprived Junctions: {res['deprived_junctions_count']} / {res['total_junctions']} ({res['service_deprivation_rate']*100:.2f}%)")
        print(f"  Total Unmet Demand: {res['total_unmet_demand_mld']:.1f} MLD")

    with open("outputs/logs/water_validation_results.json", "w") as f:
        json.dump(water_results, f, indent=2, default=str)

    return water_results, G_water


# =============================================================================
# 4. GENERATE PUBLICATION-GRADE VISUALIZATIONS
# =============================================================================

def generate_visualizations(road_res, power_res, water_res):
    print("\n" + "="*70)
    print("GENERATING VALIDATION CHARTS AND SUMMARY FIGURES")
    print("="*70)

    # 1. Cascade Step Progression across layers (Comparing primary scenarios)
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # Road Plot
    ax1 = axes[0]
    r_hist = road_res["R2_Dual_Arterial_Bottleneck"]["cascade_history"]
    r_rounds = [h["round"] for h in r_hist]
    r_fails = [h["total_failed"] for h in r_hist]
    r_stress = [h["total_stressed"] for h in r_hist]
    ax1.plot(r_rounds, r_fails, marker='o', color='#d9534f', linewidth=2, label="Failed Links")
    ax1.plot(r_rounds, r_stress, marker='s', color='#f0ad4e', linestyle='--', label="Stressed Links")
    ax1.set_title("Road Cascade (Dual Bottleneck R2)", fontsize=12, fontweight='bold')
    ax1.set_xlabel("Cascade Iteration Round", fontsize=10)
    ax1.set_ylabel("Affected Road Links", fontsize=10)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend()

    # Power Plot
    ax2 = axes[1]
    p_hist = power_res["P2_Dual_Major_Substations"]["cascade_history"]
    p_rounds = [h["round"] for h in p_hist]
    p_fails = [h["total_failed_nodes"] for h in p_hist]
    p_unserved = [h["unserved_load_mva"] for h in p_hist]
    ax2.plot(p_rounds, p_fails, marker='o', color='#0275d8', linewidth=2, label="Failed Nodes")
    ax2_twin = ax2.twinx()
    ax2_twin.plot(p_rounds, p_unserved, marker='^', color='#5cb85c', linestyle=':', label="Unserved (MVA)")
    ax2.set_title("Power Cascade (Dual Substation P2)", fontsize=12, fontweight='bold')
    ax2.set_xlabel("Cascade Iteration Round", fontsize=10)
    ax2.set_ylabel("Failed Components", fontsize=10)
    ax2_twin.set_ylabel("Unserved Power (MVA)", fontsize=10)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left")
    ax2_twin.legend(loc="lower right")

    # Water Plot
    ax3 = axes[2]
    w_hist = water_res["W1_Major_Water_Works"]["cascade_history"]
    w_rounds = [h["round"] for h in w_hist]
    w_deprived = [h["deprived_junctions_count"] for h in w_hist]
    w_unmet = [h["unmet_demand_mld"] for h in w_hist]
    ax3.plot(w_rounds, w_deprived, marker='o', color='#5bc0de', linewidth=2, label="Deprived Junctions")
    ax3_twin = ax3.twinx()
    ax3_twin.plot(w_rounds, w_unmet, marker='v', color='#d9534f', linestyle=':', label="Unmet Demand (MLD)")
    ax3.set_title("Water Cascade (Major Plant W1)", fontsize=12, fontweight='bold')
    ax3.set_xlabel("Cascade Iteration Round", fontsize=10)
    ax3.set_ylabel("Deprived Service Junctions", fontsize=10)
    ax3_twin.set_ylabel("Unmet Supply (MLD)", fontsize=10)
    ax3.grid(True, linestyle=":", alpha=0.6)
    ax3.legend(loc="upper left")
    ax3_twin.legend(loc="lower right")

    plt.tight_layout()
    chart_path = "outputs/figures/phase1_single_layer_cascade_progression.png"
    plt.savefig(chart_path, dpi=300)
    plt.close()
    print(f"Saved cascade progression plot to: {chart_path}")

    # 2. Scenario Disruption Comparison Bar Chart
    fig, ax = plt.subplots(figsize=(10, 5))
    sc_labels = [
        "Road (R1)", "Road (R2)", "Road (R3)",
        "Power (P1)", "Power (P2)", "Power (P3)",
        "Water (W1)", "Water (W2)", "Water (W3)"
    ]
    disruption_pcts = [
        road_res["R1_Major_Arterial"]["disruption_ratio"] * 100,
        road_res["R2_Dual_Arterial_Bottleneck"]["disruption_ratio"] * 100,
        road_res["R3_Peripheral_Link"]["disruption_ratio"] * 100,
        power_res["P1_Major_Substation_Peenya"]["substation_failure_rate"] * 100,
        power_res["P2_Dual_Major_Substations"]["substation_failure_rate"] * 100,
        power_res["P3_Critical_Transmission_Line"]["failed_edges_count"] / max(power_res["P3_Critical_Transmission_Line"]["total_edges"], 1) * 100,
        water_res["W1_Major_Water_Works"]["service_deprivation_rate"] * 100,
        water_res["W2_Dual_Major_Facilities"]["service_deprivation_rate"] * 100,
        water_res["W3_Critical_Main_Pipeline"]["service_deprivation_rate"] * 100
    ]
    colors = ['#d9534f', '#d9534f', '#d9534f', '#0275d8', '#0275d8', '#0275d8', '#5bc0de', '#5bc0de', '#5bc0de']
    bars = ax.bar(sc_labels, disruption_pcts, color=colors, alpha=0.85, edgecolor='black')
    ax.set_ylabel("Disruption Level (%)", fontsize=11, fontweight='bold')
    ax.set_title("Single-Layer Cascade Disruption Across Scenarios (Phase 1 Baseline)", fontsize=13, fontweight='bold')
    plt.xticks(rotation=30, ha='right', fontsize=9)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.5, f"{h:.1f}%", ha='center', va='bottom', fontsize=8, fontweight='bold')
    ax.set_ylim(0, max(disruption_pcts) * 1.25)
    ax.grid(axis='y', linestyle=':', alpha=0.7)
    plt.tight_layout()
    bar_path = "outputs/figures/phase1_scenario_disruption_comparison.png"
    plt.savefig(bar_path, dpi=300)
    plt.close()
    print(f"Saved scenario comparison plot to: {bar_path}")


if __name__ == "__main__":
    r_res, G_r = validate_road_layer()
    p_res, G_p = validate_power_layer()
    w_res, G_w = validate_water_layer()
    generate_visualizations(r_res, p_res, w_res)
    print("\nPhase 1 Cascade Validation Run Complete!")
