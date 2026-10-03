"""
Multi-Layer Cascading Failure Controller
=========================================
Implements the two-loop architecture:
  INNER LOOP  : within-layer cascade until stability (uses Phase-1 simulators)
  OUTER LOOP  : cross-layer dependency propagation until system stability

Cross-layer effects (D1, D2, D3):
  D1: Power substation failure -> effective water capacity decreases
        C_water_new = C_water_old * (1 - s_pw)
  D2: Power substation failure -> effective road junction capacity decreases
        C_road_new = C_road_old * (1 - alpha_pr * s_pr)
  D3: Water pipe failure -> effective road segment capacity decreases
        C_road_new = C_road_old * alpha_wr

IDEMPOTENCY GUARANTEE:
  A dependency effect is applied ONCE per source-failure event.
  Applied dependency pairs are tracked in applied_effects to prevent
  re-application of the same reduction on subsequent outer iterations.
  C_effective = C_original * (1-s)  -- applied exactly once per failure.

TERMINATION CRITERION:
  System is stable when a complete outer iteration produces:
    1. No new component failures in any layer
    2. No dependency-induced capacity changes in any target layer
  A max_outer_iterations guard prevents infinite loops.
"""

import copy
import logging
import networkx as nx
from models.power_cascade import PowerCascadeSimulator
from models.water_cascade import WaterCascadeSimulator
from models.road_cascade import RoadCascadeSimulator
from models.dependency_mapper import (
    D2_ALPHA_PR_CENTRAL, D3_ALPHA_WR_CENTRAL
)

logger = logging.getLogger(__name__)


class MultiLayerCascadeController:
    """
    Coupled multi-layer cascading failure controller.

    Parameters
    ----------
    G_power, G_water, G_road : nx.Graph
        Phase-1 validated graphs (used as templates; copies are made per run).
    dependency_maps : dict
        Output of dependency_mapper.build_all_dependencies().
    s_pw : float
        D1 dependency strength: Power->Water capacity reduction fraction.
        Range [0, 1]. 0 = no dependency, 1 = full capacity loss.
    s_pr : float
        D2 dependency strength: Power->Road capacity reduction scaling.
    alpha_pr : float
        D2 maximum capacity reduction from signal loss (HCM-inferred).
    alpha_wr : float
        D3 remaining road capacity after pipe-burst flooding.
    power_failure_threshold : float
        Power cascade failure threshold (load ratio).
    water_failure_threshold : float
        Water cascade pipe failure threshold.
    road_failure_threshold : float
        Road cascade failure threshold (V/C ratio).
    max_outer_iterations : int
        Safety guard for outer loop.
    max_inner_iterations : int
        Safety guard for each inner cascade loop.
    """

    def __init__(
        self,
        G_power, G_water, G_road,
        dependency_maps,
        s_pw=0.50,
        s_pr=0.50,
        alpha_pr=D2_ALPHA_PR_CENTRAL,
        alpha_wr=D3_ALPHA_WR_CENTRAL,
        power_failure_threshold=1.10,
        water_failure_threshold=1.30,
        road_failure_threshold=1.25,
        max_outer_iterations=10,
        max_inner_iterations=15
    ):
        self.G_power_template = G_power
        self.G_water_template = G_water
        self.G_road_template = G_road
        self.dep = dependency_maps

        self.s_pw = s_pw
        self.s_pr = s_pr
        self.alpha_pr = alpha_pr
        self.alpha_wr = alpha_wr

        self.pft = power_failure_threshold
        self.wft = water_failure_threshold
        self.rft = road_failure_threshold
        self.max_outer = max_outer_iterations
        self.max_inner = max_inner_iterations

    def run_coupled_cascade(
        self,
        initial_power_failures=None,
        initial_water_failures=None,
        initial_road_failures=None
    ):
        """
        Runs the full coupled cascade simulation.

        Returns
        -------
        dict with:
          outer_history       : per-iteration summary
          power_result        : final power cascade state
          water_result        : final water cascade state
          road_result         : final road cascade state
          dependency_events   : log of every cross-layer effect applied
          system_summary      : aggregated metrics
        """
        initial_power_failures = initial_power_failures or []
        initial_water_failures = initial_water_failures or []
        initial_road_failures = initial_road_failures or []

        # Working copies of graphs (modified in place by dependency effects)
        G_pow = self.G_power_template.copy()
        G_wat = self.G_water_template.copy()
        G_roa = self.G_road_template.copy()

        # Track all failures across layers (persistent across outer iterations)
        all_failed_power = set()
        all_failed_water_facs = set()
        all_failed_water_pipes = set()
        all_failed_road_edges = set()

        # Applied dependency effects - idempotency tracking
        # Key: (dep_type, source_id, target_id) -> True means already applied
        applied_effects = set()

        dependency_events = []
        outer_history = []

        # =====================================================================
        # OUTER LOOP
        # =====================================================================
        outer_iter = 0
        system_changed = True

        # Seed initial failures into persistent sets
        for f in initial_power_failures:
            if isinstance(f, str):
                all_failed_power.add(f)
            elif isinstance(f, (list, tuple)):
                all_failed_power.add(tuple(f))

        for f in initial_water_failures:
            if isinstance(f, str):
                all_failed_water_facs.add(f)
            elif isinstance(f, (list, tuple)):
                all_failed_water_pipes.add(tuple(f))

        for f in initial_road_failures:
            all_failed_road_edges.add(tuple(f))

        # Track failures at start of each outer iteration to detect changes
        prev_pow_count = -1
        prev_wat_count = -1
        prev_roa_count = -1

        power_result = None
        water_result = None
        road_result = None

        while system_changed and outer_iter < self.max_outer:
            outer_iter += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"[MultiLayer] OUTER ITERATION {outer_iter}")
            logger.info(f"[MultiLayer] Known failures: Power={len(all_failed_power)}, "
                        f"Water-Fac={len(all_failed_water_facs)}, "
                        f"Water-Pipe={len(all_failed_water_pipes)}, "
                        f"Road={len(all_failed_road_edges)}")

            # -----------------------------------------------------------------
            # INNER LOOP — POWER (if any power failures are pending)
            # -----------------------------------------------------------------
            power_init = list(all_failed_power)
            pow_sim = PowerCascadeSimulator(
                G_pow,
                failure_threshold=self.pft,
                stress_threshold=0.90
            )
            power_result = pow_sim.run_cascade(power_init, max_iterations=self.max_inner)
            # Update G_pow state
            G_pow = pow_sim.G_orig  # simulator modifies a copy; access it

            # Merge newly cascaded failures
            for nid in power_result.get("failed_node_ids", []):
                all_failed_power.add(nid)
            for ekey in power_result.get("failed_edge_keys", []):
                all_failed_power.add(ekey)

            # -----------------------------------------------------------------
            # INNER LOOP — WATER (if any water failures are pending)
            # -----------------------------------------------------------------
            water_init = list(all_failed_water_facs) + [list(k) for k in all_failed_water_pipes]
            wat_sim = WaterCascadeSimulator(
                G_wat,
                pipe_failure_threshold=self.wft,
                pipe_stress_threshold=1.00,
                critical_adequacy_threshold=0.50
            )
            water_result = wat_sim.run_cascade(water_init, max_iterations=self.max_inner)
            G_wat = wat_sim.G_orig

            for fid in water_result.get("failed_facility_ids", []):
                all_failed_water_facs.add(fid)
            for pk in water_result.get("failed_pipe_keys", []):
                all_failed_water_pipes.add(pk if isinstance(pk, tuple) else tuple(pk))

            # -----------------------------------------------------------------
            # INNER LOOP — ROAD (if any road failures are pending)
            # -----------------------------------------------------------------
            road_init = [list(k) for k in all_failed_road_edges]
            roa_sim = RoadCascadeSimulator(
                G_roa,
                failure_threshold=self.rft,
                stress_threshold=1.00
            )
            road_result = roa_sim.run_cascade(road_init, max_iterations=self.max_inner)
            G_roa = roa_sim.G_orig

            for ek in road_result.get("failed_edge_keys", []):
                all_failed_road_edges.add(ek if isinstance(ek, tuple) else tuple(ek))

            # -----------------------------------------------------------------
            # CROSS-LAYER DEPENDENCY APPLICATION
            # -----------------------------------------------------------------
            dep_changes_this_iter = 0

            # --- D1: Power -> Water -------------------------------------------
            # For every newly failed power substation, reduce capacity of
            # dependent water facilities that have not yet been affected.
            d1_map = self.dep.get("d1_map", {})
            pow_failed_substations = {
                n for n in all_failed_power
                if isinstance(n, str) and G_pow.has_node(n)
                and G_pow.nodes[n].get("entity_type") == "substation"
            }
            for fac_id, sub_id in d1_map.items():
                effect_key = ("D1", sub_id, fac_id)
                if (sub_id in pow_failed_substations
                        and effect_key not in applied_effects
                        and G_wat.has_node(fac_id)
                        and G_wat.nodes[fac_id].get("state") != "failed"):
                    applied_effects.add(effect_key)
                    orig_cap = G_wat.nodes[fac_id].get("capacity", 100.0)
                    orig_sup = G_wat.nodes[fac_id].get("supply", 80.0)
                    new_cap = orig_cap * (1.0 - self.s_pw)
                    new_sup = orig_sup * (1.0 - self.s_pw)
                    G_wat.nodes[fac_id]["capacity"] = new_cap
                    G_wat.nodes[fac_id]["supply"] = new_sup
                    dep_changes_this_iter += 1
                    event = {
                        "outer_iter": outer_iter,
                        "dependency": "D1",
                        "source_layer": "Power",
                        "source_id": sub_id,
                        "target_layer": "Water",
                        "target_id": fac_id,
                        "parameter": "s_pw={:.2f}".format(self.s_pw),
                        "effect": "capacity {:.1f} -> {:.1f} MLD, supply {:.1f} -> {:.1f} MLD".format(
                            orig_cap, new_cap, orig_sup, new_sup),
                        "new_capacity": new_cap,
                        "original_capacity": orig_cap
                    }
                    dependency_events.append(event)
                    logger.info(f"[D1] {sub_id} -> {fac_id}: cap {orig_cap:.1f} -> {new_cap:.1f} MLD")

            # --- D2: Power -> Road --------------------------------------------
            # For every failed power substation, reduce capacity of dependent
            # signalized road nodes (edges incident to them).
            d2_map = self.dep.get("d2_map", {})
            for rn_id, sub_id in d2_map.items():
                effect_key = ("D2", sub_id, rn_id)
                if (sub_id in pow_failed_substations
                        and effect_key not in applied_effects
                        and G_roa.has_node(rn_id)):
                    applied_effects.add(effect_key)
                    reduction_factor = 1.0 - self.alpha_pr * self.s_pr
                    n_affected = 0
                    for nb in G_roa.neighbors(rn_id):
                        if G_roa.has_edge(rn_id, nb):
                            edata = G_roa.edges[rn_id, nb]
                            if edata.get("state") != "failed":
                                orig_cap = edata.get("capacity", 2000.0)
                                new_cap = max(100.0, orig_cap * reduction_factor)
                                edata["capacity"] = new_cap
                                # Update V/C ratio
                                cur_load = edata.get("current_load", orig_cap * 0.65)
                                edata["load_ratio"] = cur_load / max(new_cap, 1.0)
                                t0 = edata.get("free_flow_time", 10.0)
                                edata["current_travel_time"] = t0 * (1.0 + 0.15 * (edata["load_ratio"] ** 4))
                                dep_changes_this_iter += 1
                                n_affected += 1
                    if n_affected > 0:
                        event = {
                            "outer_iter": outer_iter,
                            "dependency": "D2",
                            "source_layer": "Power",
                            "source_id": sub_id,
                            "target_layer": "Road",
                            "target_id": rn_id,
                            "parameter": "alpha_pr={:.2f}, s_pr={:.2f}".format(self.alpha_pr, self.s_pr),
                            "effect": "reduction factor {:.2f} applied to {} incident edges".format(
                                reduction_factor, n_affected),
                        }
                        dependency_events.append(event)
                        logger.info(f"[D2] {sub_id} -> {rn_id}: {n_affected} edges reduced "
                                    f"by factor {reduction_factor:.2f}")

            # --- D3: Water -> Road --------------------------------------------
            # For every failed water pipe junction, reduce capacity of nearby roads.
            d3_map = self.dep.get("d3_map", {})
            all_failed_water_junction_ids = {
                pk[0] for pk in all_failed_water_pipes
                if isinstance(pk, tuple) and len(pk) == 2
            } | {
                pk[1] for pk in all_failed_water_pipes
                if isinstance(pk, tuple) and len(pk) == 2
            }

            for road_edge, wj_list in d3_map.items():
                u, v = road_edge
                for wj_id in wj_list:
                    effect_key = ("D3", wj_id, road_edge)
                    if (wj_id in all_failed_water_junction_ids
                            and effect_key not in applied_effects
                            and G_roa.has_edge(u, v)):
                        edata = G_roa.edges[u, v]
                        if edata.get("state") != "failed":
                            applied_effects.add(effect_key)
                            orig_cap = edata.get("capacity", 2000.0)
                            new_cap = max(100.0, orig_cap * self.alpha_wr)
                            edata["capacity"] = new_cap
                            cur_load = edata.get("current_load", orig_cap * 0.65)
                            edata["load_ratio"] = cur_load / max(new_cap, 1.0)
                            t0 = edata.get("free_flow_time", 10.0)
                            edata["current_travel_time"] = t0 * (1.0 + 0.15 * (edata["load_ratio"] ** 4))
                            dep_changes_this_iter += 1
                            event = {
                                "outer_iter": outer_iter,
                                "dependency": "D3",
                                "source_layer": "Water",
                                "source_id": wj_id,
                                "target_layer": "Road",
                                "target_id": "{}-{}".format(u, v),
                                "parameter": "alpha_wr={:.2f}".format(self.alpha_wr),
                                "effect": "capacity {:.1f} -> {:.1f} vph".format(orig_cap, new_cap),
                            }
                            dependency_events.append(event)
                            logger.info(f"[D3] {wj_id} -> road({u},{v}): "
                                        f"cap {orig_cap:.0f} -> {new_cap:.0f} vph")

            # -----------------------------------------------------------------
            # STABILITY CHECK
            # -----------------------------------------------------------------
            new_pow_count = len(all_failed_power)
            new_wat_count = len(all_failed_water_facs) + len(all_failed_water_pipes)
            new_roa_count = len(all_failed_road_edges)

            outer_history.append({
                "outer_iter": outer_iter,
                "power_failed_total": new_pow_count,
                "water_fac_failed_total": len(all_failed_water_facs),
                "water_pipe_failed_total": len(all_failed_water_pipes),
                "road_edge_failed_total": new_roa_count,
                "dep_changes_this_iter": dep_changes_this_iter,
                "power_cascade_rounds": power_result.get("total_rounds", 0) if power_result else 0,
                "water_cascade_rounds": water_result.get("total_rounds", 0) if water_result else 0,
                "road_cascade_rounds": road_result.get("total_rounds", 0) if road_result else 0,
            })

            system_changed = (
                (new_pow_count > prev_pow_count or
                 new_wat_count > prev_wat_count or
                 new_roa_count > prev_roa_count) or
                dep_changes_this_iter > 0
            )
            prev_pow_count = new_pow_count
            prev_wat_count = new_wat_count
            prev_roa_count = new_roa_count

            logger.info(
                f"[MultiLayer] Outer {outer_iter} complete: "
                f"dep_changes={dep_changes_this_iter}, system_changed={system_changed}"
            )

        # =====================================================================
        # FINAL SUMMARY
        # =====================================================================
        total_pow_nodes = G_pow.number_of_nodes()
        total_pow_edges = G_pow.number_of_edges()
        total_wat_nodes = G_wat.number_of_nodes()
        total_wat_edges = G_wat.number_of_edges()
        total_roa_edges = G_roa.number_of_edges()

        failed_pow_substations = sum(
            1 for n in all_failed_power
            if isinstance(n, str) and G_pow.has_node(n)
            and G_pow.nodes[n].get("entity_type") == "substation"
        )

        system_summary = {
            "outer_iterations": outer_iter,
            "system_stable": not system_changed,
            # Power
            "power_failed_nodes": len([n for n in all_failed_power if isinstance(n, str)]),
            "power_failed_substations": failed_pow_substations,
            "power_failed_edges": len([e for e in all_failed_power if isinstance(e, tuple)]),
            "power_total_nodes": total_pow_nodes,
            "power_total_edges": total_pow_edges,
            # Water
            "water_failed_facilities": len(all_failed_water_facs),
            "water_failed_pipes": len(all_failed_water_pipes),
            "water_total_nodes": total_wat_nodes,
            "water_total_edges": total_wat_edges,
            "water_unmet_demand_mld": water_result.get("total_unmet_demand_mld", 0.0) if water_result else 0.0,
            "water_deprived_junctions": water_result.get("deprived_junctions_count", 0) if water_result else 0,
            # Road
            "road_failed_edges": len(all_failed_road_edges),
            "road_total_edges": total_roa_edges,
            "road_disruption_ratio": len(all_failed_road_edges) / max(total_roa_edges, 1),
            "road_delay_factor": road_result.get("delay_inflation_factor", 1.0) if road_result else 1.0,
            # Dependencies
            "total_dep_events": len(dependency_events),
            "d1_events": sum(1 for e in dependency_events if e["dependency"] == "D1"),
            "d2_events": sum(1 for e in dependency_events if e["dependency"] == "D2"),
            "d3_events": sum(1 for e in dependency_events if e["dependency"] == "D3"),
            # Parameters
            "s_pw": self.s_pw,
            "s_pr": self.s_pr,
            "alpha_pr": self.alpha_pr,
            "alpha_wr": self.alpha_wr,
        }

        logger.info(f"[MultiLayer] COMPLETE after {outer_iter} outer iterations.")
        logger.info(f"[MultiLayer] {system_summary}")

        return {
            "outer_history": outer_history,
            "power_result": power_result,
            "water_result": water_result,
            "road_result": road_result,
            "dependency_events": dependency_events,
            "system_summary": system_summary,
            "final_failed_power": list(all_failed_power),
            "final_failed_water_facs": list(all_failed_water_facs),
            "final_failed_water_pipes": [list(p) for p in all_failed_water_pipes],
            "final_failed_road_edges": [list(e) for e in all_failed_road_edges],
        }

