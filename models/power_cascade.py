"""
Power Grid Cascading Failure Model (Capacity-Based Abstraction)
==============================================================
Methodology:
  - Stated Abstraction: Capacity-headroom redistribution model.
    (Full AC/DC power flow is not claimed, as generator admittance matrices,
     reactive power, and bus phase angles are unavailable in raw OSM data).
  - Component Representation:
      * Nodes: Substations (44) and Transmission Towers (4019).
      * Edges: High-voltage transmission lines (220kV, 66kV).
  - Spare Capacity Headroom:
      SpareCap_j = max(0, Capacity_j - CurrentLoad_j)
  - Load Redistribution:
      Transfers displaced load from failed elements to surviving topological
      neighbors weighted by spare capacity headroom and inverted distance.
  - Failure Condition:
      LoadRatio_j = CurrentLoad_j / Capacity_j >= theta_power_fail (default 1.10, emergency thermal trip).
      Stressed State: LoadRatio_j >= theta_power_stress (default 0.90).
"""

import logging
import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

class PowerCascadeSimulator:
    def __init__(
        self,
        G_power,
        failure_threshold=1.10,
        stress_threshold=0.90,
        headroom_gamma=1.0,
        distance_decay=1.0
    ):
        self.G_orig = G_power
        self.failure_threshold = failure_threshold
        self.stress_threshold = stress_threshold
        self.headroom_gamma = headroom_gamma
        self.distance_decay = distance_decay

    def run_cascade(self, initial_failed_components, max_iterations=15):
        """
        Runs an independent cascading failure simulation on the power grid.
        
        Parameters:
            initial_failed_components: list of node IDs (substations/towers)
                                       or edge tuples (u, v) to fail initially.
            max_iterations: safety limit for cascade rounds.
            
        Returns:
            dict containing step-by-step logs, failed components, unserved load, and metrics.
        """
        G = self.G_orig.copy()
        
        failed_nodes = set()
        failed_edges = set()
        stressed_nodes = set()
        stressed_edges = set()
        cascade_history = []

        def canon(u, v):
            return (u, v) if str(u) <= str(v) else (v, u)

        # 1. Trigger Initial Failures
        newly_failed_nodes = []
        newly_failed_edges = []
        
        for comp in initial_failed_components:
            if isinstance(comp, str):  # Node failure (e.g. substation)
                if G.has_node(comp) and comp not in failed_nodes:
                    failed_nodes.add(comp)
                    G.nodes[comp]["state"] = "failed"
                    load = G.nodes[comp].get("current_load", 150.0)
                    newly_failed_nodes.append((comp, load))
                    # Failing a substation also disconnects its incident transmission lines
                    for neighbor in list(G.neighbors(comp)):
                        ekey = canon(comp, neighbor)
                        if ekey not in failed_edges:
                            failed_edges.add(ekey)
                            G.edges[comp, neighbor]["state"] = "failed"
                            newly_failed_edges.append((comp, neighbor, G.edges[comp, neighbor].get("current_load", 100.0)))
            elif isinstance(comp, (list, tuple)) and len(comp) == 2:  # Edge failure
                u, v = comp
                if G.has_edge(u, v):
                    ekey = canon(u, v)
                    if ekey not in failed_edges:
                        failed_edges.add(ekey)
                        G.edges[u, v]["state"] = "failed"
                        load = G.edges[u, v].get("current_load", 100.0)
                        newly_failed_edges.append((u, v, load))

        total_disp_initial = sum(l for _, l in newly_failed_nodes) + sum(l for _, _, l in newly_failed_edges)
        logger.info(
            f"[Power Cascade] Round 0: Initialized {len(newly_failed_nodes)} failed nodes, "
            f"{len(newly_failed_edges)} failed edges. Displaced Load: {total_disp_initial:.1f} MVA"
        )
        cascade_history.append({
            "round": 0,
            "new_failed_nodes": list(failed_nodes),
            "new_failed_edges": [canon(u, v) for u, v, _ in newly_failed_edges],
            "total_failed_nodes": len(failed_nodes),
            "total_failed_edges": len(failed_edges),
            "displaced_load_mva": total_disp_initial,
            "unserved_load_mva": 0.0
        })

        iteration = 0
        total_unserved_load = 0.0

        while (newly_failed_nodes or newly_failed_edges) and iteration < max_iterations:
            iteration += 1
            nodes_to_reroute = newly_failed_nodes
            edges_to_reroute = newly_failed_edges
            newly_failed_nodes = []
            newly_failed_edges = []
            
            round_displaced = 0.0
            round_unserved = 0.0

            # Subgraph of surviving components
            G_active = G.copy()
            for n in failed_nodes:
                if G_active.has_node(n):
                    G_active.remove_node(n)
            for u, v in failed_edges:
                if G_active.has_edge(u, v):
                    G_active.remove_edge(u, v)

            # -------------------------------------------------------------
            # A. Redistribute Displaced Node (Substation) Loads
            # -------------------------------------------------------------
            for node_id, disp_load in nodes_to_reroute:
                round_displaced += disp_load
                if disp_load <= 0:
                    continue

                # Find candidate substations in the vicinity (within 2-3 hops or connected component)
                candidates = []
                for surviving_n, ndata in G_active.nodes(data=True):
                    if ndata.get("entity_type") == "substation" and surviving_n not in failed_nodes:
                        cap = ndata.get("capacity", 250.0)
                        cur = ndata.get("current_load", 0.0)
                        spare = max(0.0, cap - cur)
                        if spare > 0:
                            # Estimate topological / euclidean distance
                            orig_n = G.nodes[node_id]
                            d_lat = orig_n["latitude"] - ndata["latitude"]
                            d_lon = orig_n["longitude"] - ndata["longitude"]
                            dist = max(0.01, (d_lat**2 + d_lon**2)**0.5)
                            weight = (spare ** self.headroom_gamma) / (dist ** self.distance_decay)
                            candidates.append((surviving_n, spare, weight))

                if not candidates:
                    # Power brownout / blackout: no surviving substation with headroom
                    round_unserved += disp_load
                    continue

                total_weight = sum(w for _, _, w in candidates)
                if total_weight <= 0:
                    round_unserved += disp_load
                    continue

                # Distribute preferentially based on spare capacity headroom
                for target_n, spare, weight in candidates:
                    allocated = disp_load * (weight / total_weight)
                    ndata = G.nodes[target_n]
                    ndata["current_load"] = ndata.get("current_load", 0.0) + allocated
                    cap = ndata.get("capacity", 250.0)
                    ndata["load_ratio"] = ndata["current_load"] / max(cap, 1.0)

            # -------------------------------------------------------------
            # B. Redistribute Displaced Edge (Transmission Line) Flows
            # -------------------------------------------------------------
            for u, v, disp_flow in edges_to_reroute:
                round_displaced += disp_flow
                if disp_flow <= 0:
                    continue

                # Alternative paths between u and v in surviving grid
                if G_active.has_node(u) and G_active.has_node(v) and nx.has_path(G_active, u, v):
                    try:
                        # Find shortest path in active grid
                        path = nx.shortest_path(G_active, u, v, weight="length")
                        # Check bottleneck spare capacity along path
                        path_edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
                        # Distribute flow along detour path
                        for pu, pv in path_edges:
                            if G.has_edge(pu, pv):
                                edata = G.edges[pu, pv]
                                edata["current_load"] = edata.get("current_load", 0.0) + disp_flow
                                cap = edata.get("capacity", 350.0)
                                edata["load_ratio"] = edata["current_load"] / max(cap, 1.0)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        round_unserved += disp_flow
                else:
                    # Flow cannot be rerouted locally; attempt redistribution to parallel lines
                    parallel_candidates = []
                    for pu, pv, edata in G_active.edges(data=True):
                        cap = edata.get("capacity", 350.0)
                        cur = edata.get("current_load", 0.0)
                        spare = max(0.0, cap - cur)
                        if spare > 0:
                            weight = spare ** self.headroom_gamma
                            parallel_candidates.append((pu, pv, weight))

                    if parallel_candidates:
                        # Distribute to top 5 nearest candidates
                        top_candidates = parallel_candidates[:5]
                        tot_w = sum(w for _, _, w in top_candidates)
                        for pu, pv, w in top_candidates:
                            alloc = disp_flow * (w / tot_w)
                            edata = G.edges[pu, pv]
                            edata["current_load"] = edata.get("current_load", 0.0) + alloc
                            cap = edata.get("capacity", 350.0)
                            edata["load_ratio"] = edata["current_load"] / max(cap, 1.0)
                    else:
                        round_unserved += disp_flow

            total_unserved_load += round_unserved

            # -------------------------------------------------------------
            # C. Overload Scan for Newly Failed Elements
            # -------------------------------------------------------------
            stressed_nodes.clear()
            for n, ndata in G.nodes(data=True):
                if n in failed_nodes:
                    continue
                ratio = ndata.get("load_ratio", 0.0)
                if ratio >= self.failure_threshold:
                    ndata["state"] = "failed"
                    failed_nodes.add(n)
                    newly_failed_nodes.append((n, ndata.get("current_load", 150.0)))
                elif ratio >= self.stress_threshold:
                    ndata["state"] = "stressed"
                    stressed_nodes.add(n)
                else:
                    ndata["state"] = "normal"

            stressed_edges.clear()
            for u, v, edata in G.edges(data=True):
                ekey = canon(u, v)
                if ekey in failed_edges:
                    continue
                ratio = edata.get("load_ratio", 0.0)
                if ratio >= self.failure_threshold:
                    edata["state"] = "failed"
                    failed_edges.add(ekey)
                    newly_failed_edges.append((u, v, edata.get("current_load", 100.0)))
                elif ratio >= self.stress_threshold:
                    edata["state"] = "stressed"
                    stressed_edges.add(ekey)
                else:
                    edata["state"] = "normal"

            logger.info(
                f"[Power Cascade] Round {iteration}: Newly failed: {len(newly_failed_nodes)} nodes, "
                f"{len(newly_failed_edges)} edges. Stressed: {len(stressed_nodes)} nodes, "
                f"{len(stressed_edges)} edges. Total failed: {len(failed_nodes)} nodes, {len(failed_edges)} edges."
            )
            cascade_history.append({
                "round": iteration,
                "new_failed_nodes": list(newly_failed_nodes),
                "new_failed_edges": [canon(u, v) for u, v, _ in newly_failed_edges],
                "total_failed_nodes": len(failed_nodes),
                "total_failed_edges": len(failed_edges),
                "total_stressed_nodes": len(stressed_nodes),
                "total_stressed_edges": len(stressed_edges),
                "displaced_load_mva": round_displaced,
                "unserved_load_mva": round_unserved
            })

        # Final Grid Metrics
        total_substations = sum(1 for _, d in G.nodes(data=True) if d.get("entity_type") == "substation")
        failed_substations = sum(1 for n in failed_nodes if G.nodes[n].get("entity_type") == "substation")
        
        return {
            "converged": len(newly_failed_nodes) == 0 and len(newly_failed_edges) == 0,
            "total_rounds": iteration,
            "initial_failures": initial_failed_components,
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "failed_nodes_count": len(failed_nodes),
            "failed_edges_count": len(failed_edges),
            "failed_substations_count": failed_substations,
            "total_substations": total_substations,
            "substation_failure_rate": failed_substations / max(total_substations, 1),
            "stressed_nodes_count": len(stressed_nodes),
            "stressed_edges_count": len(stressed_edges),
            "total_unserved_load_mva": total_unserved_load,
            "cascade_history": cascade_history,
            "failed_node_ids": list(failed_nodes),
            "failed_edge_keys": list(failed_edges)
        }
