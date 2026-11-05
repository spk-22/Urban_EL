"""
Trial Run: 5 km Radius Multi-Layer Cascade Simulation
Location: Central Silk Board Junction, South Bengaluru (12.9172° N, 77.6228° E)
================================================================================
Conducts a realistic trial run of the cascading failure model on a localized 5 km
radius urban catchment around Bengaluru's most congested transit and utility hub.

Models Evaluated:
  - M0: Independent Baseline (no cross-layer links)
  - M1: Power -> Water only (D1)
  - M2: Power -> Road only (D2)
  - M3: Water -> Road only (D3)
  - M7: Full 3-Layer Triad with Cyclic Feedback (D1 + D2 + D3 + D4/D5/D6)

Outputs:
  - Asset inventory inside the 5 km catchment
  - Component failures (inside 5 km vs spillover)
  - Higher-Order Gain metric (G = F(M7) - max(M1, M2, M3))
  - Interactive HTML Folium map: outputs/figures/trial_5km_silkboard_map.html
  - CSV results: outputs/tables/trial_5km_silkboard_results.csv
"""

import os
import sys
import math
import json
import logging
import numpy as np
import pandas as pd
import folium
from folium import plugins

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.graph_builder import build_power_graph, build_water_graph, build_corridor_road_graph
from models.dependency_mapper import (
    build_all_dependencies,
    D2_ALPHA_PR_CENTRAL, D3_ALPHA_WR_CENTRAL,
    D4_GAMMA_RP_CENTRAL, D5_GAMMA_RW_CENTRAL,
    D6_BETA_WR_CENTRAL, D1_TRANSIENT_SURGE
)
from models.multi_layer_cascade import MultiLayerCascadeController

# -----------------------------------------------------------------------------
# 1. PARAMETERS & SPATIAL GEOMETRY
# -----------------------------------------------------------------------------
CENTER_NAME = "Central Silk Board Junction (CSB), Bengaluru"
CENTER_LAT = 12.9172
CENTER_LON = 77.6228
RADIUS_M = 5000.0  # 5 km radius

SILK_BOARD_PATH = r"d:\urban el\data\processed\silk_board.geojson"
POWER_EXCEL = r"d:\new urban el\processed\power_infrastructure.xlsx"
WATER_EXCEL = r"d:\new urban el\processed\water_infrastructure.xlsx"

OUT_TABLE_DIR = r"d:\new urban el\outputs\tables"
OUT_FIG_DIR = r"d:\new urban el\outputs\figures"
os.makedirs(OUT_TABLE_DIR, exist_ok=True)
os.makedirs(OUT_FIG_DIR, exist_ok=True)


def haversine(lat1, lon1, lat2, lon2):
    """Calculates distance in meters between two coordinates."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def run_5km_trial():
    logger.info("=" * 80)
    logger.info(f"TRIAL RUN: 5 KM RADIUS CASCADE SIMULATION")
    logger.info(f"Target Nexus: {CENTER_NAME}")
    logger.info(f"Coordinates: {CENTER_LAT}° N, {CENTER_LON}° E | Radius: {RADIUS_M/1000:.1f} km")
    logger.info("=" * 80)

    # 1. Build Graphs
    logger.info("Loading infrastructure networks...")
    G_power = build_power_graph(excel_path=POWER_EXCEL)
    G_water = build_water_graph(excel_path=WATER_EXCEL)
    G_road = build_corridor_road_graph(SILK_BOARD_PATH)

    # 2. Filter Assets within 5 km Radius
    subs_5km = {}
    for n, d in G_power.nodes(data=True):
        if d.get("entity_type") == "substation":
            dist = haversine(CENTER_LAT, CENTER_LON, d.get("latitude", 0), d.get("longitude", 0))
            if dist <= RADIUS_M:
                subs_5km[n] = {**d, "dist_m": dist}

    facs_5km = {}
    for n, d in G_water.nodes(data=True):
        if d.get("entity_type") == "facility":
            dist = haversine(CENTER_LAT, CENTER_LON, d.get("latitude", 0), d.get("longitude", 0))
            if dist <= RADIUS_M:
                facs_5km[n] = {**d, "dist_m": dist}

    road_nodes_5km = set()
    for n, d in G_road.nodes(data=True):
        lat, lon = d.get("latitude", 0), d.get("longitude", 0)
        if haversine(CENTER_LAT, CENTER_LON, lat, lon) <= RADIUS_M:
            road_nodes_5km.add(n)

    road_edges_5km = set()
    for u, v in G_road.edges():
        if u in road_nodes_5km or v in road_nodes_5km:
            road_edges_5km.add((u, v) if str(u) <= str(v) else (v, u))

    logger.info("\n" + "=" * 50)
    logger.info(f"5 KM CATCHMENT ASSET INVENTORY:")
    logger.info(f"  - Power Substations: {len(subs_5km)} (out of {len([n for n, d in G_power.nodes(data=True) if d.get('entity_type') == 'substation'])} citywide)")
    for sid, sinfo in sorted(subs_5km.items(), key=lambda x: x[1]['dist_m']):
        logger.info(f"      * {sid} ({sinfo.get('name', 'Substation')}): Dist={sinfo['dist_m']:.0f}m")

    logger.info(f"  - Water Treatment Facilities / Reservoirs: {len(facs_5km)} (out of 53 citywide)")
    for fid, finfo in sorted(facs_5km.items(), key=lambda x: x[1]['dist_m']):
        logger.info(f"      * {fid} ({finfo.get('name', 'Water Works')} - {finfo.get('facility_type', '')}): Cap={finfo.get('capacity', 0)} MLD, Dist={finfo['dist_m']:.0f}m")

    logger.info(f"  - Road Corridor Network in 5 km Zone: {len(road_nodes_5km)} nodes, {len(road_edges_5km)} edges")
    logger.info("=" * 50 + "\n")

    # 3. Build Spatial Dependencies
    deps = build_all_dependencies(G_power, G_water, G_road)

    # 4. Identify Co-located Trigger Assets in 5 km Zone
    # A. Silk Board Water Transmission Pipe
    pipe_silkboard = None
    for u, v in G_water.edges():
        if "WJ_10511" in (u, v) or "WJ_10509" in (u, v):
            pipe_silkboard = (u, v)
            break
    if not pipe_silkboard:
        pipe_silkboard = list(G_water.edges())[0]

    # B. Road Bottleneck link near Silk Board
    edge_vcs = [(u, v, G_road.edges[u, v].get("load_ratio", 0)) for u, v in G_road.edges()]
    edge_vcs.sort(key=lambda x: -x[2])
    road_bottleneck = (edge_vcs[0][0], edge_vcs[0][1])

    # C. HSR Layout Substation (SUB_43 - within 3.3 km of Silk Board)
    initial_power_failures = ["SUB_43"]
    initial_water_failures = [pipe_silkboard]
    initial_road_failures = [road_bottleneck]

    logger.info(f"TRIAL SHOCK SCENARIO DEFINITION:")
    logger.info(f"  1. Power Seed: Substation SUB_43 (HSR Layout 66/11kV Substation, 3.2 km from CSB)")
    logger.info(f"  2. Water Seed: Pipe {pipe_silkboard} (Silk Board Underpass High-Pressure Transmission Main)")
    logger.info(f"  3. Road Seed: Link {road_bottleneck} (Central Silk Board Grade Intersection Choke Point)")

    # 5. Execute Simulation Hierarchy (M0, M1, M2, M3, M7)
    models_to_test = {
        "M0": {"name": "M0: Independent Baseline", "d1": False, "d2": False, "d3": False},
        "M1": {"name": "M1: Power->Water only",     "d1": True,  "d2": False, "d3": False},
        "M2": {"name": "M2: Power->Road only",      "d1": False, "d2": True,  "d3": False},
        "M3": {"name": "M3: Water->Road only",      "d1": False, "d2": False, "d3": True},
        "M7": {"name": "M7: Full 3-Layer Triad",    "d1": True,  "d2": True,  "d3": True},
    }

    results = []
    m7_detailed_res = None

    for m_key, m_cfg in models_to_test.items():
        logger.info(f"\n--- Running {m_cfg['name']} ---")
        dep_subset = {
            "d1_map": deps["d1_map"] if m_cfg["d1"] else {},
            "d2_map": deps["d2_map"] if m_cfg["d2"] else {},
            "d3_map": deps["d3_map"] if m_cfg["d3"] else {},
        }

        ctrl = MultiLayerCascadeController(
            G_power=G_power,
            G_water=G_water,
            G_road=G_road,
            dependency_maps=dep_subset,
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
        )

        res = ctrl.run_coupled_cascade(
            initial_power_failures=initial_power_failures,
            initial_water_failures=initial_water_failures,
            initial_road_failures=initial_road_failures
        )

        s = res["system_summary"]
        if m_key == "M7":
            m7_detailed_res = res

        # Calculate localized failures inside 5 km
        failed_power_nodes = set(res.get("final_failed_power", []))
        failed_subs_inside_5km = len(failed_power_nodes.intersection(set(subs_5km.keys())))

        failed_road_edges = res.get("final_failed_road_edges", [])
        failed_road_inside_5km = sum(1 for e in failed_road_edges if ((e[0], e[1]) in road_edges_5km or (e[1], e[0]) in road_edges_5km))
        # Water
        failed_wat_pipes_inside_5km = len(res.get("failed_water_pipes", []))  # pipe_silkboard is inside

        pow_fail_total = s["power_failed_nodes"] + s["power_failed_edges"]
        wat_fail_total = s["water_failed_facilities"] + s["water_failed_pipes"]
        roa_fail_total = s["road_failed_edges"]
        tot_fail = pow_fail_total + wat_fail_total + roa_fail_total

        results.append({
            "model": m_key,
            "model_name": m_cfg["name"],
            "total_failures": tot_fail,
            "power_failures": pow_fail_total,
            "water_failures": wat_fail_total,
            "road_failures": roa_fail_total,
            "road_failures_in_5km": failed_road_inside_5km,
            "substations_failed_in_5km": failed_subs_inside_5km,
            "road_delay_factor": round(float(s["road_delay_factor"]), 4),
            "unmet_water_demand_mld": round(float(s["water_unmet_demand_mld"]), 1),
            "dep_events": s["total_dep_events"],
            "outer_iterations": s["outer_iterations"]
        })

    df_res = pd.DataFrame(results)
    csv_out = os.path.join(OUT_TABLE_DIR, "trial_5km_silkboard_results.csv")
    df_res.to_csv(csv_out, index=False)
    logger.info(f"\nSaved trial results table to: {csv_out}")

    # Calculate Higher-Order Gain
    m7_tot = df_res.loc[df_res["model"] == "M7", "total_failures"].values[0]
    max_pairwise = max(
        df_res.loc[df_res["model"] == "M1", "total_failures"].values[0],
        df_res.loc[df_res["model"] == "M2", "total_failures"].values[0],
        df_res.loc[df_res["model"] == "M3", "total_failures"].values[0]
    )
    higher_order_gain = m7_tot - max_pairwise

    logger.info("\n" + "=" * 60)
    logger.info(f"TRIAL RUN RESULTS (5 KM CATCHMENT):")
    logger.info(f"  M0 (Independent):           {df_res.loc[df_res['model']=='M0', 'total_failures'].values[0]} failures")
    logger.info(f"  M1 (Power->Water):          {df_res.loc[df_res['model']=='M1', 'total_failures'].values[0]} failures")
    logger.info(f"  M2 (Power->Road):           {df_res.loc[df_res['model']=='M2', 'total_failures'].values[0]} failures")
    logger.info(f"  M3 (Water->Road):           {df_res.loc[df_res['model']=='M3', 'total_failures'].values[0]} failures")
    logger.info(f"  M7 (Full 3-Layer Triad):    {m7_tot} failures")
    logger.info(f"  HIGHER-ORDER GAIN (G):      +{higher_order_gain} FAILURES")
    logger.info("=" * 60)

    # 6. Generate Interactive Folium Map
    logger.info("Generating interactive 5 km trial map with OpenStreetMap background...")
    m = folium.Map(location=[CENTER_LAT, CENTER_LON], zoom_start=13, tiles="OpenStreetMap")

    # 5 km Radius Buffer Circle
    folium.Circle(
        location=[CENTER_LAT, CENTER_LON],
        radius=RADIUS_M,
        color="#1f77b4",
        weight=2,
        fill=True,
        fill_color="#1f77b4",
        fill_opacity=0.08,
        tooltip=f"5 km Radius Catchment Zone around {CENTER_NAME}"
    ).add_to(m)

    # Center Marker (Central Silk Board)
    folium.Marker(
        location=[CENTER_LAT, CENTER_LON],
        popup=f"<b>{CENTER_NAME}</b><br>Latitude: {CENTER_LAT}<br>Longitude: {CENTER_LON}<br>Focal Nexus Center",
        icon=folium.Icon(color="red", icon="star")
    ).add_to(m)

    # Add Power Substations inside 5 km
    failed_power_substations = set(m7_detailed_res.get("final_failed_power", []))
    for sid, sdata in subs_5km.items():
        is_failed = sid in failed_power_substations
        color = "darkred" if is_failed else "blue"
        status = "FAILED (Thermal Choke)" if is_failed else "Operational"
        folium.CircleMarker(
            location=[sdata["latitude"], sdata["longitude"]],
            radius=8 if is_failed else 6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            popup=f"<b>Substation: {sid} ({sdata.get('name', '')})</b><br>Status: {status}<br>Distance to CSB: {sdata['dist_m']:.0f} m"
        ).add_to(m)

    # Add Water Facilities inside 5 km
    for fid, fdata in facs_5km.items():
        folium.CircleMarker(
            location=[fdata["latitude"], fdata["longitude"]],
            radius=7,
            color="teal",
            fill=True,
            fill_color="cyan",
            fill_opacity=0.85,
            popup=f"<b>Water Works: {fid} ({fdata.get('name', '')})</b><br>Type: {fdata.get('facility_type', '')}<br>Capacity: {fdata.get('capacity', 0)} MLD<br>Distance: {fdata['dist_m']:.0f} m"
        ).add_to(m)

    # Add Sample Road Links (failed in M7 vs normal)
    failed_road_list = [tuple(e) for e in m7_detailed_res.get("final_failed_road_edges", [])]
    draw_count = 0
    for u, v in failed_road_list:
        if G_road.has_edge(u, v):
            u_lat, u_lon = G_road.nodes[u].get("latitude"), G_road.nodes[u].get("longitude")
            v_lat, v_lon = G_road.nodes[v].get("latitude"), G_road.nodes[v].get("longitude")
            if u_lat and v_lat:
                folium.PolyLine(
                    locations=[[u_lat, u_lon], [v_lat, v_lon]],
                    color="#d62728",
                    weight=3.5,
                    opacity=0.8,
                    tooltip=f"Failed Road Link: {u} - {v} (Flooding / Gridlock Spillover)"
                ).add_to(m)
                draw_count += 1
                if draw_count >= 600:
                    break

    html_out = os.path.join(OUT_FIG_DIR, "trial_5km_silkboard_map.html")
    m.save(html_out)
    logger.info(f"Saved interactive trial map to: {html_out}")

    return df_res, higher_order_gain, m7_detailed_res


if __name__ == "__main__":
    run_5km_trial()

