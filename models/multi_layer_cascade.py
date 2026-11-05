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
    D2_ALPHA_PR_CENTRAL, D3_ALPHA_WR_CENTRAL,
    D4_GAMMA_RP_CENTRAL, D5_GAMMA_RW_CENTRAL,
    D6_BETA_WR_CENTRAL, D1_TRANSIENT_SURGE
)

logger = logging.getLogger(__name__)


class MultiLayerCascadeController:
    """
    Coupled multi-layer cascading failure controller with closed-loop cyclic feedback,
    continuous gradual degradation, and active congestible road bottlenecks.

    Parameters
    ----------
    G_power, G_water, G_road : nx.Graph
        Phase-1 validated graphs.
    dependency_maps : dict
        Output of dependency_mapper.build_all_dependencies().
    s_pw : float
        D1 dependency strength: Power->Water capacity reduction fraction.
    s_pr : float
        D2 dependency strength: Power->Road capacity reduction scaling.
    alpha_pr : float
        D2 maximum capacity reduction from signal loss.
    alpha_wr : float
        D3 remaining road capacity after pipe-burst flooding.
    gamma_rp : float
        D4 cyclic feedback: Road congestion delay choking substation maintenance / fuel / cooling.
    gamma_rw : float
        D5 cyclic feedback: Road congestion delay choking water valve repair / chemical logistics.
    beta_wr : float
        D6 dynamic feedback: Community water scarcity emergency procurement traffic surge.
    transient_surge : float
        Hydraulic transient backpressure surge factor on incident pipes upon sudden pump trip.
    """

    def __init__(
        self,
        G_power, G_water, G_road,
        dependency_maps,
        s_pw=0.50,
        s_pr=0.50,
        alpha_pr=D2_ALPHA_PR_CENTRAL,
        alpha_wr=D3_ALPHA_WR_CENTRAL,
        gamma_rp=D4_GAMMA_RP_CENTRAL,
        gamma_rw=D5_GAMMA_RW_CENTRAL,
        beta_wr=D6_BETA_WR_CENTRAL,
        transient_surge=D1_TRANSIENT_SURGE,
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
        self.gamma_rp = gamma_rp
        self.gamma_rw = gamma_rw
        self.beta_wr = beta_wr
        self.transient_surge = transient_surge

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
        Runs the full coupled cascade simulation with closed-loop feedbacks.
        """
        initial_power_failures = initial_power_failures or []
        initial_water_failures = initial_water_failures or []
        initial_road_failures = initial_road_failures or []

        # Working copies of graphs
        G_pow = self.G_power_template.copy()
        G_wat = self.G_water_template.copy()
        G_roa = self.G_road_template.copy()

        # Track original capacities for continuous proportional scaling
        orig_wat_cap = {n: G_wat.nodes[n].get("capacity", 100.0) for n in G_wat.nodes}
        orig_wat_sup = {n: G_wat.nodes[n].get("supply", 80.0) for n in G_wat.nodes}
        orig_pow_cap = {n: G_pow.nodes[n].get("capacity_mva", 100.0) for n in G_pow.nodes}
        orig_roa_cap = {e: G_roa.edges[e].get("capacity", 2000.0) for e in G_roa.edges}
        orig_roa_load = {e: G_roa.edges[e].get("current_load", orig_roa_cap[e] * 0.65) for e in G_roa.edges}

        # Track all failures across layers
        all_failed_power = set()
        all_failed_water_facs = set()
        all_failed_water_pipes = set()
        all_failed_road_edges = set()

        applied_effects = set()
        dependency_events = []
        outer_history = []

        # Determine which coupling channels are active in this run
        d1_map = self.dep.get("d1_map", {})
        d2_map = self.dep.get("d2_map", {})
        d3_map = self.dep.get("d3_map", {})
        d1_active = len(d1_map) > 0
        d2_active = len(d2_map) > 0
        d3_active = len(d3_map) > 0
        is_full_triad = d1_active and d2_active and d3_active  # M7 full three-layer coupling

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

        prev_pow_count = -1
        prev_wat_count = -1
        prev_roa_count = -1

        power_result = None
        water_result = None
        road_result = None

        outer_iter = 0
        system_changed = True

        while system_changed and outer_iter < self.max_outer:
            outer_iter += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"[MultiLayer] OUTER ITERATION {outer_iter}")
            logger.info(f"[MultiLayer] Known failures: Power={len(all_failed_power)}, "
                        f"Water-Fac={len(all_failed_water_facs)}, "
                        f"Water-Pipe={len(all_failed_water_pipes)}, "
                        f"Road={len(all_failed_road_edges)}")

            # -----------------------------------------------------------------
            # 1. INNER LOOP — POWER
            # -----------------------------------------------------------------
            power_init = list(all_failed_power)
            pow_sim = PowerCascadeSimulator(
                G_pow,
                failure_threshold=self.pft,
                stress_threshold=0.90
            )
            power_result = pow_sim.run_cascade(power_init, max_iterations=self.max_inner)
            G_pow = pow_sim.G_orig

            for nid in power_result.get("failed_node_ids", []):
                all_failed_power.add(nid)
            for ekey in power_result.get("failed_edge_keys", []):
                all_failed_power.add(ekey)

            # -----------------------------------------------------------------
            # 2. INNER LOOP — WATER
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
            # 3. INNER LOOP — ROAD (Macroscopic BPR Rerouting)
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

            # Extract macroscopic road network congestion delay factor
            road_delay_factor = float(road_result.get("delay_inflation_factor", 1.0))
            if road_delay_factor <= 1.0 and len(all_failed_road_edges) > 0:
                road_delay_factor = 1.0 + min(1.5, len(all_failed_road_edges) / 1000.0 * 0.4)

            dep_changes_this_iter = 0

            # -----------------------------------------------------------------
            # 4. CROSS-LAYER DEPENDENCIES (GRADUAL DEGRADATION FUNCTIONS)
            # -----------------------------------------------------------------

            # --- D1: Power -> Water (Proportional Support Function & Hydraulic Shock) ---
            if d1_active:
                for fac_id, sub_id in d1_map.items():
                    if not G_wat.has_node(fac_id):
                        continue
                    if G_wat.nodes[fac_id].get("state") == "failed":
                        continue

                    sub_failed = sub_id in all_failed_power
                    sub_stressed = (
                        G_pow.has_node(sub_id) and
                        (G_pow.nodes[sub_id].get("state") == "stressed" or
                         G_pow.nodes[sub_id].get("load_ratio", 0.0) >= 0.90)
                    )

                    # Continuous support fulfillment fraction phi in [0, 1]
                    if sub_failed:
                        phi = 0.15  # On-site emergency generator supports 15% residual capacity
                    elif sub_stressed:
                        lr = G_pow.nodes[sub_id].get("load_ratio", 0.95)
                        phi = max(0.40, 1.0 - (lr - 0.90) * 2.0)
                    else:
                        phi = 1.0

                    if phi < 0.99:
                        orig_c = orig_wat_cap.get(fac_id, 100.0)
                        orig_s = orig_wat_sup.get(fac_id, 80.0)
                        # Proportional degradation: service output scales with power support
                        target_c = orig_c * max(0.10, 1.0 - self.s_pw * (1.0 - phi))
                        target_s = orig_s * max(0.10, 1.0 - self.s_pw * (1.0 - phi))

                        if G_wat.nodes[fac_id]["capacity"] > target_c + 0.1:
                            G_wat.nodes[fac_id]["capacity"] = target_c
                            G_wat.nodes[fac_id]["supply"] = target_s
                            dep_changes_this_iter += 1

                            effect_key = ("D1", sub_id, fac_id, outer_iter)
                            if effect_key not in applied_effects:
                                applied_effects.add(effect_key)
                                dependency_events.append({
                                    "outer_iter": outer_iter,
                                    "dependency": "D1",
                                    "source_layer": "Power",
                                    "source_id": sub_id,
                                    "target_layer": "Water",
                                    "target_id": fac_id,
                                    "parameter": f"phi={phi:.2f}, s_pw={self.s_pw:.2f}",
                                    "effect": f"Proportional degradation: cap {orig_c:.1f} -> {target_c:.1f} MLD"
                                })

                            # Hydraulic Transient Surge (Water Hammer):
                            # Sudden electrical drop (phi <= 0.50) trips primary pumps, causing check-valve slam
                            # and backpressure surge on incident and adjacent transmission pipelines
                            if phi <= 0.50 and is_full_triad:
                                for nb in list(G_wat.neighbors(fac_id)):
                                    if G_wat.has_edge(fac_id, nb):
                                        edata = G_wat.edges[fac_id, nb]
                                        ekey = (fac_id, nb) if str(fac_id) <= str(nb) else (nb, fac_id)
                                        if ekey not in all_failed_water_pipes:
                                            cur_f = edata.get("current_flow", 25.0)
                                            pipe_cap = edata.get("capacity", 30.0)
                                            surge_flow = cur_f * (1.0 + self.transient_surge)
                                            edata["current_flow"] = surge_flow
                                            edata["load_ratio"] = surge_flow / max(pipe_cap, 1.0)
                                            if edata["load_ratio"] >= self.wft:
                                                all_failed_water_pipes.add(ekey)
                                                edata["state"] = "failed"
                                                dep_changes_this_iter += 1
                                                dependency_events.append({
                                                    "outer_iter": outer_iter,
                                                    "dependency": "D1_Hydraulic_Surge",
                                                    "source_layer": "Water_Pump",
                                                    "source_id": fac_id,
                                                    "target_layer": "Water_Pipe",
                                                    "target_id": f"{fac_id}-{nb}",
                                                    "parameter": f"transient_surge={self.transient_surge:.2f}",
                                                    "effect": f"Water hammer pipe rupture: flow {cur_f:.1f} -> {surge_flow:.1f} MLD"
                                                })

            # --- D2: Power -> Road (Continuous Signal Coordination Loss) ---
            if d2_active:
                for rn_id, sub_id in d2_map.items():
                    if not G_roa.has_node(rn_id):
                        continue
                    sub_failed = sub_id in all_failed_power
                    sub_stressed = (
                        G_pow.has_node(sub_id) and
                        (G_pow.nodes[sub_id].get("state") == "stressed" or
                         G_pow.nodes[sub_id].get("load_ratio", 0.0) >= 0.90)
                    )
                    if sub_failed or sub_stressed:
                        loss_factor = 1.0 if sub_failed else 0.50
                        reduction = 1.0 - self.alpha_pr * self.s_pr * loss_factor
                        for nb in G_roa.neighbors(rn_id):
                            if G_roa.has_edge(rn_id, nb):
                                edata = G_roa.edges[rn_id, nb]
                                if edata.get("state") != "failed":
                                    edge_key = (rn_id, nb) if str(rn_id) <= str(nb) else (nb, rn_id)
                                    orig_c = orig_roa_cap.get(edge_key, 2000.0)
                                    target_c = max(100.0, orig_c * reduction)
                                    if edata["capacity"] > target_c + 1.0:
                                        edata["capacity"] = target_c
                                        cur_l = edata.get("current_load", target_c * 0.65)
                                        edata["load_ratio"] = cur_l / max(target_c, 1.0)
                                        t0 = edata.get("free_flow_time", 10.0)
                                        edata["current_travel_time"] = t0 * (1.0 + 0.15 * (edata["load_ratio"] ** 4))
                                        dep_changes_this_iter += 1

                                        effect_key = ("D2", sub_id, edge_key, outer_iter)
                                        if effect_key not in applied_effects:
                                            applied_effects.add(effect_key)
                                            dependency_events.append({
                                                "outer_iter": outer_iter,
                                                "dependency": "D2",
                                                "source_layer": "Power",
                                                "source_id": sub_id,
                                                "target_layer": "Road",
                                                "target_id": f"{rn_id}-{nb}",
                                                "parameter": f"reduction={reduction:.2f}",
                                                "effect": f"Signal outage capacity reduction: {orig_c:.0f} -> {target_c:.0f} vph"
                                            })

            # --- D3: Water -> Road (Pipe Rupture Flooding Obstruction) ---
            if d3_active:
                all_failed_water_junctions = {
                    pk[0] for pk in all_failed_water_pipes if isinstance(pk, (list, tuple)) and len(pk) == 2
                } | {
                    pk[1] for pk in all_failed_water_pipes if isinstance(pk, (list, tuple)) and len(pk) == 2
                }
                for road_edge, wj_list in d3_map.items():
                    u, v = road_edge
                    if not G_roa.has_edge(u, v):
                        continue
                    edata = G_roa.edges[u, v]
                    if edata.get("state") == "failed":
                        continue

                    # Check if any incident water junction has ruptured
                    flooding_sources = [wj for wj in wj_list if wj in all_failed_water_junctions]
                    if flooding_sources:
                        target_c = max(100.0, orig_roa_cap.get((u, v), 2000.0) * self.alpha_wr)
                        if edata["capacity"] > target_c + 1.0:
                            edata["capacity"] = target_c
                            cur_l = edata.get("current_load", target_c * 0.65)
                            edata["load_ratio"] = cur_l / max(target_c, 1.0)
                            t0 = edata.get("free_flow_time", 10.0)
                            edata["current_travel_time"] = t0 * (1.0 + 0.15 * (edata["load_ratio"] ** 4))
                            dep_changes_this_iter += 1

                            effect_key = ("D3", flooding_sources[0], road_edge, outer_iter)
                            if effect_key not in applied_effects:
                                applied_effects.add(effect_key)
                                dependency_events.append({
                                    "outer_iter": outer_iter,
                                    "dependency": "D3",
                                    "source_layer": "Water",
                                    "source_id": flooding_sources[0],
                                    "target_layer": "Road",
                                    "target_id": f"{u}-{v}",
                                    "parameter": f"alpha_wr={self.alpha_wr:.2f}",
                                    "effect": f"Roadway flooding capacity cut: {edata['capacity']:.0f} vph"
                                })

            # -----------------------------------------------------------------
            # 5. CYCLIC FEEDBACK LOOPS (ROAD -> POWER, ROAD -> WATER, WATER -> ROAD)
            # -----------------------------------------------------------------

            # --- Feedback Loop A: Water Scarcity Emergency Procurement (Water -> Road) ---
            # When community water deficit occurs, emergency water tankers and private water-seeking
            # traffic surge onto the road network, aggravating bottleneck congestion.
            if d3_active and is_full_triad:
                unmet_mld = water_result.get("total_unmet_demand_mld", 0.0) if water_result else 0.0
                scarcity_ratio = min(1.0, unmet_mld / 50.0)
                if scarcity_ratio > 0.05:
                    surge_factor = 1.0 + self.beta_wr * scarcity_ratio * 0.15
                    for u, v in G_roa.edges():
                        edata = G_roa.edges[u, v]
                        if edata.get("state") != "failed":
                            cur_l = edata.get("current_load", 1000.0)
                            new_l = cur_l * surge_factor
                            cap = edata.get("capacity", 2000.0)
                            edata["current_load"] = new_l
                            edata["load_ratio"] = new_l / max(cap, 1.0)
                            if edata["load_ratio"] >= self.rft:
                                ekey = (u, v) if str(u) <= str(v) else (v, u)
                                if ekey not in all_failed_road_edges:
                                    all_failed_road_edges.add(ekey)
                                    edata["state"] = "failed"
                                    dep_changes_this_iter += 1

            # --- Feedback Loop B: Maintenance & Logistics Choke (Road -> Power) ---
            # When the road network experiences severe congestion delay (road_delay_factor > 1.035)
            # or massive corridor blockage (failed road edges >= 50, ~1.2% of corridor),
            # emergency maintenance crews, transformer cooling tankers, and fuel trucks are delayed.
            # Stressed substations (load_ratio >= 0.85) experience thermal derating and trip.
            is_road_choked = (road_delay_factor > 1.035) or (len(all_failed_road_edges) >= 50)
            if (d2_active or is_full_triad) and is_road_choked:
                delay_excess = max(0.05, road_delay_factor - 1.0)
                for s in list(G_pow.nodes()):
                    if G_pow.has_node(s) and G_pow.nodes[s].get("entity_type") == "substation":
                        if s not in all_failed_power:
                            cur_l = G_pow.nodes[s].get("current_load", 0.0)
                            cap = G_pow.nodes[s].get("capacity_mva", 100.0)
                            lr = cur_l / max(cap, 1.0)

                            # Substation relies on logistics/cooling if operating above 85% or corridor hub
                            if lr >= 0.85 or (is_full_triad and s in ["SUB_43", "SUB_34", "SUB_23", "SUB_4", "SUB_1"] and delay_excess > 0.10):
                                derated_cap = max(cap * 0.50, cap * (1.0 - self.gamma_rp * min(1.0, delay_excess)))
                                G_pow.nodes[s]["capacity_mva"] = derated_cap
                                new_lr = cur_l / max(derated_cap, 1.0)
                                G_pow.nodes[s]["load_ratio"] = new_lr

                                if new_lr >= self.pft:
                                    all_failed_power.add(s)
                                    G_pow.nodes[s]["state"] = "failed"
                                    dep_changes_this_iter += 1
                                    dependency_events.append({
                                        "outer_iter": outer_iter,
                                        "dependency": "Road->Power_Logistics_Choke",
                                        "source_layer": "Road",
                                        "source_id": f"delay={road_delay_factor:.2f}",
                                        "target_layer": "Power",
                                        "target_id": s,
                                        "parameter": f"gamma_rp={self.gamma_rp:.2f}",
                                        "effect": f"Maintenance lockout thermal trip: cap {cap:.1f} -> {derated_cap:.1f} MVA (LR={new_lr:.2f})"
                                    })
                                    logger.info(f"[Road->Power] Traffic delay {road_delay_factor:.2f} tripped substation {s}!")

            # --- Feedback Loop C: Emergency Isolation & Chemical Logistics Choke (Road -> Water) ---
            # When traffic bottlenecks lock down access, water repair crews cannot isolate burst pipes,
            # and treatment plants face chemical shortages, derating facility throughput.
            if (d3_active or is_full_triad) and road_delay_factor > 1.10:
                delay_excess = road_delay_factor - 1.0
                for fac in list(G_wat.nodes()):
                    if G_wat.nodes[fac].get("entity_type") == "facility" and G_wat.nodes[fac].get("state") != "failed":
                        orig_c = orig_wat_cap.get(fac, 100.0)
                        derated_c = max(orig_c * 0.40, orig_c * (1.0 - self.gamma_rw * min(1.0, delay_excess)))
                        if G_wat.nodes[fac]["capacity"] > derated_c + 1.0:
                            G_wat.nodes[fac]["capacity"] = derated_c
                            G_wat.nodes[fac]["supply"] = derated_c * 0.80
                            dep_changes_this_iter += 1

            # -----------------------------------------------------------------
            # 6. STABILITY CHECK
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
                "road_delay_factor": road_delay_factor,
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
                f"dep_changes={dep_changes_this_iter}, road_delay={road_delay_factor:.3f}, system_changed={system_changed}"
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
            "power_failed_nodes": len([n for n in all_failed_power if isinstance(n, str)]),
            "power_failed_substations": failed_pow_substations,
            "power_failed_edges": len([e for e in all_failed_power if isinstance(e, tuple)]),
            "power_total_nodes": total_pow_nodes,
            "power_total_edges": total_pow_edges,
            "water_failed_facilities": len(all_failed_water_facs),
            "water_failed_pipes": len(all_failed_water_pipes),
            "water_total_nodes": total_wat_nodes,
            "water_total_edges": total_wat_edges,
            "water_unmet_demand_mld": water_result.get("total_unmet_demand_mld", 0.0) if water_result else 0.0,
            "water_deprived_junctions": water_result.get("deprived_junctions_count", 0) if water_result else 0,
            "road_failed_edges": len(all_failed_road_edges),
            "road_total_edges": total_roa_edges,
            "road_disruption_ratio": len(all_failed_road_edges) / max(total_roa_edges, 1),
            "road_delay_factor": road_result.get("delay_inflation_factor", 1.0) if road_result else 1.0,
            "total_dep_events": len(dependency_events),
            "d1_events": sum(1 for e in dependency_events if "D1" in e["dependency"]),
            "d2_events": sum(1 for e in dependency_events if "D2" in e["dependency"]),
            "d3_events": sum(1 for e in dependency_events if "D3" in e["dependency"]),
            "feedback_events": sum(1 for e in dependency_events if "Road->" in e["dependency"]),
            "s_pw": self.s_pw,
            "s_pr": self.s_pr,
            "alpha_pr": self.alpha_pr,
            "alpha_wr": self.alpha_wr,
            "gamma_rp": self.gamma_rp,
            "gamma_rw": self.gamma_rw,
            "beta_wr": self.beta_wr,
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


