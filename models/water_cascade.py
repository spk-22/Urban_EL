"""
Water Supply & Pipeline Cascading Failure Model
===============================================
Methodology:
  - Stated Abstraction: Supply-Demand Flow Network.
    (Full hydraulic Darcy-Weisbach headloss and EPANET pressure simulation
     are not claimed due to lack of pipe diameters and valve states in raw OSM).
  - Physical Entities:
      * Sources & Reservoirs (53): Supply injection nodes (MLD).
      * Pipe Junctions (34,345): Localized municipal consumption demand nodes.
      * Pipelines (34,550): Hydraulic transmission links with finite flow capacities.
  - Cascade Mechanism:
      1. Component Failure (Facility outage or Pipe rupture).
      2. Supply reduction and loss of hydraulic transmission path.
      3. Rerouting of actual water flow through alternative connected pipelines.
      4. Pipe over-pressurization / overload check:
           Q_e / C_e >= theta_water_fail (default 1.30, burst / emergency shutoff).
      5. Downstream supply adequacy calculation:
           Adequacy_j = ReceivedFlow_j / Demand_j
           Water Outage: Adequacy_j < 0.50 (severe deficit).
      6. Iterative propagation until hydraulic flow balance is achieved.
"""

import logging
import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

class WaterCascadeSimulator:
    def __init__(
        self,
        G_water,
        pipe_failure_threshold=1.30,
        pipe_stress_threshold=1.00,
        critical_adequacy_threshold=0.50
    ):
        self.G_orig = G_water
        self.pipe_failure_threshold = pipe_failure_threshold
        self.pipe_stress_threshold = pipe_stress_threshold
        self.critical_adequacy_threshold = critical_adequacy_threshold

    def run_cascade(self, initial_failed_components, max_iterations=15):
        """
        Runs an independent cascading failure simulation on the water network.
        
        Parameters:
            initial_failed_components: list of facility IDs (e.g. 'FAC_1')
                                       or edge tuples (u, v) to fail initially.
            max_iterations: safety limit for cascade rounds.
            
        Returns:
            dict containing step-by-step logs, failed facilities/pipes, unmet demand, and metrics.
        """
        G = self.G_orig.copy()
        
        failed_facilities = set()
        failed_pipes = set()
        stressed_pipes = set()
        deprived_junctions = set()
        cascade_history = []

        def canon(u, v):
            return (u, v) if str(u) <= str(v) else (v, u)

        # 1. Trigger Initial Failures
        newly_failed_facs = []
        newly_failed_pipes = []

        for comp in initial_failed_components:
            if isinstance(comp, str):  # Facility failure
                if G.has_node(comp) and comp not in failed_facilities:
                    failed_facilities.add(comp)
                    G.nodes[comp]["state"] = "failed"
                    lost_supply = G.nodes[comp].get("supply", 100.0)
                    G.nodes[comp]["supply"] = 0.0
                    newly_failed_facs.append((comp, lost_supply))
                    # Disconnect incident feeder pipes
                    for neighbor in list(G.neighbors(comp)):
                        ekey = canon(comp, neighbor)
                        if ekey not in failed_pipes:
                            failed_pipes.add(ekey)
                            G.edges[comp, neighbor]["state"] = "failed"
                            newly_failed_pipes.append((comp, neighbor, G.edges[comp, neighbor].get("current_flow", 50.0)))
            elif isinstance(comp, (list, tuple)) and len(comp) == 2:  # Pipe failure
                u, v = comp
                if G.has_edge(u, v):
                    ekey = canon(u, v)
                    if ekey not in failed_pipes:
                        failed_pipes.add(ekey)
                        G.edges[u, v]["state"] = "failed"
                        lost_flow = G.edges[u, v].get("current_flow", 25.0)
                        newly_failed_pipes.append((u, v, lost_flow))

        total_lost_initial = sum(s for _, s in newly_failed_facs) + sum(f for _, _, f in newly_failed_pipes)
        logger.info(
            f"[Water Cascade] Round 0: Initialized {len(newly_failed_facs)} failed facilities, "
            f"{len(newly_failed_pipes)} failed pipes. Lost Flow: {total_lost_initial:.1f} MLD"
        )
        cascade_history.append({
            "round": 0,
            "new_failed_facilities": list(failed_facilities),
            "new_failed_pipes": [canon(u, v) for u, v, _ in newly_failed_pipes],
            "total_failed_facilities": len(failed_facilities),
            "total_failed_pipes": len(failed_pipes),
            "total_stressed_pipes": 0,
            "lost_flow_mld": total_lost_initial,
            "deprived_junctions_count": 0,
            "unmet_demand_mld": 0.0
        })

        iteration = 0
        total_unmet_demand = 0.0
        total_demand = 0.0

        # Check if adequacy evaluation is needed even without new hard failures
        # (e.g. from D1 electrical dependency degrading facility operating capacity/supply)
        has_degraded_supply = any(
            d.get("entity_type") == "facility" and d.get("supply", 0) < d.get("capacity", 0) * 0.99
            for _, d in G.nodes(data=True)
        )
        needs_evaluation = bool(newly_failed_facs or newly_failed_pipes or failed_facilities or failed_pipes or has_degraded_supply)

        while (newly_failed_facs or newly_failed_pipes or (iteration == 0 and needs_evaluation)) and iteration < max_iterations:
            iteration += 1
            facs_to_process = newly_failed_facs
            pipes_to_process = newly_failed_pipes
            newly_failed_facs = []
            newly_failed_pipes = []

            # Active surviving network
            G_active = G.copy()
            for f in failed_facilities:
                if G_active.has_node(f):
                    G_active.remove_node(f)
            for u, v in failed_pipes:
                if G_active.has_edge(u, v):
                    G_active.remove_edge(u, v)

            # -------------------------------------------------------------
            # A. Flow Redistribution to Alternate Pipes
            # -------------------------------------------------------------
            round_rerouted_flow = 0.0
            for u, v, disp_flow in pipes_to_process:
                if disp_flow <= 0:
                    continue
                round_rerouted_flow += disp_flow
                
                # Check if alternative path exists between pipe endpoints
                if G_active.has_node(u) and G_active.has_node(v) and nx.has_path(G_active, u, v):
                    try:
                        detour_path = nx.shortest_path(G_active, u, v, weight="length")
                        for i in range(len(detour_path) - 1):
                            du, dv = detour_path[i], detour_path[i+1]
                            if G.has_edge(du, dv):
                                edata = G.edges[du, dv]
                                edata["current_flow"] = edata.get("current_flow", 0.0) + disp_flow
                                cap = edata.get("capacity", 30.0)
                                edata["load_ratio"] = edata["current_flow"] / max(cap, 1.0)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        pass

            # -------------------------------------------------------------
            # B. Pipe Overload & Rupture Check
            # -------------------------------------------------------------
            stressed_pipes.clear()
            for u, v, edata in G.edges(data=True):
                ekey = canon(u, v)
                if ekey in failed_pipes:
                    continue
                ratio = edata.get("load_ratio", 0.0)
                if ratio >= self.pipe_failure_threshold:
                    edata["state"] = "failed"
                    failed_pipes.add(ekey)
                    newly_failed_pipes.append((u, v, edata.get("current_flow", 30.0)))
                elif ratio >= self.pipe_stress_threshold:
                    edata["state"] = "stressed"
                    stressed_pipes.add(ekey)
                else:
                    edata["state"] = "normal"

            # -------------------------------------------------------------
            # C. Downstream Supply Adequacy & Deficit Calculation
            # -------------------------------------------------------------
            # Find surviving facilities connected to each component
            active_facs = [
                n for n, d in G.nodes(data=True)
                if d.get("entity_type") == "facility" and n not in failed_facilities and d.get("supply", 0) > 0
            ]
            
            # For each connected component in G_active, check if it contains a water facility
            deprived_junctions.clear()
            total_unmet_demand = 0.0
            total_demand = 0.0

            for comp_nodes in nx.connected_components(G_active):
                comp_facs = [n for n in comp_nodes if n in active_facs]
                comp_supply = sum(G.nodes[n].get("supply", 0.0) for n in comp_facs)
                comp_demand = sum(G.nodes[n].get("demand", 0.5) for n in comp_nodes if G.nodes[n].get("entity_type") == "pipe_junction")
                total_demand += comp_demand

                if comp_demand > 0:
                    comp_adequacy = min(1.0, comp_supply / comp_demand) if comp_supply > 0 else 0.0
                else:
                    comp_adequacy = 1.0

                for n in comp_nodes:
                    if G.nodes[n].get("entity_type") == "pipe_junction":
                        G.nodes[n]["adequacy"] = comp_adequacy
                        if comp_adequacy < self.critical_adequacy_threshold:
                            deprived_junctions.add(n)
                            unmet = G.nodes[n].get("demand", 0.5) * (1.0 - comp_adequacy)
                            total_unmet_demand += unmet

            logger.info(
                f"[Water Cascade] Round {iteration}: Newly failed pipes: {len(newly_failed_pipes)}. "
                f"Stressed pipes: {len(stressed_pipes)}. Deprived junctions: {len(deprived_junctions)}. "
                f"Unmet Demand: {total_unmet_demand:.1f} MLD"
            )
            cascade_history.append({
                "round": iteration,
                "new_failed_pipes": [canon(u, v) for u, v, _ in newly_failed_pipes],
                "total_failed_facilities": len(failed_facilities),
                "total_failed_pipes": len(failed_pipes),
                "total_stressed_pipes": len(stressed_pipes),
                "deprived_junctions_count": len(deprived_junctions),
                "unmet_demand_mld": total_unmet_demand
            })

        total_facilities = sum(1 for _, d in G.nodes(data=True) if d.get("entity_type") == "facility")
        total_junctions = sum(1 for _, d in G.nodes(data=True) if d.get("entity_type") == "pipe_junction")

        return {
            "converged": len(newly_failed_facs) == 0 and len(newly_failed_pipes) == 0,
            "total_rounds": iteration,
            "initial_failures": initial_failed_components,
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "total_facilities": total_facilities,
            "total_junctions": total_junctions,
            "failed_facilities_count": len(failed_facilities),
            "failed_pipes_count": len(failed_pipes),
            "stressed_pipes_count": len(stressed_pipes),
            "deprived_junctions_count": len(deprived_junctions),
            "service_deprivation_rate": len(deprived_junctions) / max(total_junctions, 1),
            "total_unmet_demand_mld": total_unmet_demand,
            "cascade_history": cascade_history,
            "failed_facility_ids": list(failed_facilities),
            "failed_pipe_keys": list(failed_pipes)
        }
