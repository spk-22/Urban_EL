"""
Road Transportation Cascading Failure Model
===========================================
Physics & Behavioral Foundations:
  - Congestion Function: Bureau of Public Roads (BPR) relationship
      T(V) = T_0 * [1 + alpha * (V / C)^beta]  (alpha=0.15, beta=4.0)
  - Alternate Route Search: Yen's K-Shortest Paths (k=3)
  - Route Choice Behavior: Multinomial Logit (MNL) Discrete Choice Model
      P(k) = exp(-theta * T_k) / sum(exp(-theta * T_j))
  - Failure Condition: V / C >= theta_fail (default 1.25, severe breakdown)
  - Failed links become strictly unavailable (removed from routing topology).
  - Strict traffic volume accounting to prevent double-counting.
"""

import math
import logging
from itertools import islice
import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

class RoadCascadeSimulator:
    def __init__(
        self,
        G_road,
        k_routes=3,
        logit_theta=0.05,
        bpr_alpha=0.15,
        bpr_beta=4.0,
        failure_threshold=1.25,
        stress_threshold=1.00
    ):
        self.G_orig = G_road
        self.k_routes = k_routes
        self.logit_theta = logit_theta
        self.bpr_alpha = bpr_alpha
        self.bpr_beta = bpr_beta
        self.failure_threshold = failure_threshold
        self.stress_threshold = stress_threshold

    def _bpr(self, t0, v, c):
        """Calculates BPR travel time."""
        c_safe = max(c, 1.0)
        vc = v / c_safe
        return t0 * (1.0 + self.bpr_alpha * (vc ** self.bpr_beta))

    def run_cascade(self, initial_failed_edges, max_iterations=15):
        """
        Runs an independent cascading failure simulation on the road network.
        
        Parameters:
            initial_failed_edges: list of (u, v) tuples to fail initially.
            max_iterations: safety limit for cascade rounds.
            
        Returns:
            dict containing step-by-step logs, failed edges, stressed edges, and metrics.
        """
        # Create a deep copy for simulation
        G = self.G_orig.copy()
        
        # Track edge states
        failed_edges = set()
        stressed_edges = set()
        cascade_history = []
        
        # Helper to get canonical edge key
        def canon(u, v):
            return (u, v) if str(u) <= str(v) else (v, u)

        # 1. Trigger Initial Failures
        newly_failed = []
        for u, v in initial_failed_edges:
            if G.has_edge(u, v):
                edge_key = canon(u, v)
                if edge_key not in failed_edges:
                    failed_edges.add(edge_key)
                    G.edges[u, v]["state"] = "failed"
                    newly_failed.append((u, v, G.edges[u, v].get("current_load", 1000.0)))

        # Also check for edges that exceed failure threshold due to cross-layer capacity reduction (D2/D3)
        for u, v, edata in G.edges(data=True):
            edge_key = canon(u, v)
            if edge_key not in failed_edges:
                lr = edata.get("load_ratio", 0.0)
                if lr >= self.failure_threshold:
                    failed_edges.add(edge_key)
                    edata["state"] = "failed"
                    newly_failed.append((u, v, edata.get("current_load", 1000.0)))
        
        logger.info(f"[Road Cascade] Round 0: Initialized {len(newly_failed)} failed edges.")
        cascade_history.append({
            "round": 0,
            "new_failures": [canon(u, v) for u, v, _ in newly_failed],
            "total_failed": len(failed_edges),
            "total_stressed": 0,
            "displaced_traffic": sum(vol for _, _, vol in newly_failed)
        })

        iteration = 0
        while newly_failed and iteration < max_iterations:
            iteration += 1
            # Edges that failed in the previous round need their traffic displaced
            traffic_to_reroute = newly_failed
            newly_failed = []
            
            # Subgraph of surviving roads for path routing
            # Inactive edges are those in failed_edges
            G_active = G.copy()
            for u, v in failed_edges:
                if G_active.has_edge(u, v):
                    G_active.remove_edge(u, v)

            round_displaced = 0.0

            for u, v, disp_volume in traffic_to_reroute:
                round_displaced += disp_volume
                if disp_volume <= 0:
                    continue
                
                # Check if u and v are connected in surviving graph
                if not (G_active.has_node(u) and G_active.has_node(v) and nx.has_path(G_active, u, v)):
                    # Traffic cannot find alternative path between u and v; trips are lost / isolated
                    continue
                
                # Find top-K shortest paths using Yen's algorithm
                try:
                    path_gen = nx.shortest_simple_paths(
                        G_active, u, v, weight="current_travel_time"
                    )
                    top_k_paths = list(islice(path_gen, self.k_routes))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

                if not top_k_paths:
                    continue

                # Compute travel time for each path
                path_times = []
                for p in top_k_paths:
                    ptime = sum(
                        G_active.edges[p[i], p[i+1]].get("current_travel_time", 10.0)
                        for i in range(len(p) - 1)
                    )
                    path_times.append(ptime)

                # Multinomial Logit Choice Probabilities: P_j = exp(-theta * T_j) / sum(exp(-theta * T_m))
                min_time = min(path_times)
                # Numerical stability: subtract min_time
                exp_utilities = [math.exp(-self.logit_theta * (t - min_time)) for t in path_times]
                sum_exp = sum(exp_utilities)
                probs = [e / sum_exp for e in exp_utilities]

                # Distribute displaced traffic across candidate paths
                for path, prob in zip(top_k_paths, probs):
                    assigned_vol = disp_volume * prob
                    for i in range(len(path) - 1):
                        pu, pv = path[i], path[i+1]
                        if G.has_edge(pu, pv):
                            edata = G.edges[pu, pv]
                            if edata.get("state") != "failed":
                                edata["current_load"] = edata.get("current_load", 0.0) + assigned_vol
                                cap = edata.get("capacity", 2000.0)
                                edata["load_ratio"] = edata["current_load"] / max(cap, 1.0)
                                edata["current_travel_time"] = self._bpr(
                                    edata.get("free_flow_time", 10.0),
                                    edata["current_load"],
                                    cap
                                )

            # Scan all surviving edges for newly overloaded links
            stressed_edges.clear()
            for u, v, edata in G.edges(data=True):
                ekey = canon(u, v)
                if ekey in failed_edges:
                    continue
                vc = edata.get("load_ratio", 0.0)
                if vc >= self.failure_threshold:
                    # Mark new failure
                    edata["state"] = "failed"
                    failed_edges.add(ekey)
                    newly_failed.append((u, v, edata.get("current_load", 1000.0)))
                elif vc >= self.stress_threshold:
                    edata["state"] = "stressed"
                    stressed_edges.add(ekey)
                else:
                    edata["state"] = "normal"

            logger.info(
                f"[Road Cascade] Round {iteration}: {len(newly_failed)} newly failed, "
                f"{len(stressed_edges)} stressed, Total failed: {len(failed_edges)}"
            )
            cascade_history.append({
                "round": iteration,
                "new_failures": [canon(u, v) for u, v, _ in newly_failed],
                "total_failed": len(failed_edges),
                "total_stressed": len(stressed_edges),
                "displaced_traffic": round_displaced
            })

        # Calculate final network metrics
        total_edges = G.number_of_edges()
        failed_count = len(failed_edges)
        surviving_edges = total_edges - failed_count
        disruption_ratio = failed_count / max(total_edges, 1)

        # Average travel time inflation across surviving edges
        initial_times = [
            self._bpr(d["free_flow_time"], d["capacity"] * 0.65, d["capacity"])
            for _, _, d in G.edges(data=True) if "free_flow_time" in d
        ]
        final_times = [
            d["current_travel_time"]
            for u, v, d in G.edges(data=True) if canon(u, v) not in failed_edges and "current_travel_time" in d
        ]
        avg_t0 = np.mean(initial_times) if initial_times else 1.0
        avg_t_final = np.mean(final_times) if final_times else 1.0
        delay_factor = avg_t_final / max(avg_t0, 1e-4)

        return {
            "converged": len(newly_failed) == 0,
            "total_rounds": iteration,
            "initial_failures": [canon(u, v) for u, v in initial_failed_edges],
            "total_edges": total_edges,
            "failed_edges_count": failed_count,
            "stressed_edges_count": len(stressed_edges),
            "surviving_edges_count": surviving_edges,
            "disruption_ratio": disruption_ratio,
            "delay_inflation_factor": delay_factor,
            "cascade_history": cascade_history,
            "failed_edge_keys": list(failed_edges),
            "stressed_edge_keys": list(stressed_edges)
        }
