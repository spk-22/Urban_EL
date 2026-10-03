"""
Urban Infrastructure Graph Builder
==================================
Constructs validated, attribute-rich network models for:
  1. Power Transmission & Distribution Network (G_power)
  2. Water Supply & Pipeline Network (G_water)
  3. Urban Road Transportation Network (G_road)

Integrates source Excel node entities and GeoJSON spatial edge connections.
"""

import os
import math
import json
import logging
import pandas as pd
import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def haversine(lat1, lon1, lat2, lon2):
    """Calculates geodesic distance in meters between two (lat, lon) coordinates."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


# =============================================================================
# 1. POWER NETWORK BUILDER
# =============================================================================

def build_power_graph(
    excel_path=r"d:\new urban el\processed\power_infrastructure.xlsx",
    geojson_path=r"d:\new urban el\processed\power_network_geojson.json",
    snap_tolerance_m=50.0,
    baseline_load_ratio=0.65
):
    """
    Builds G_power combining 44 substation nodes from Excel and 346 transmission
    lines from GeoJSON, with topological snapping across switchyards/towers.
    """
    logger.info("Building Power Network...")
    df_p = pd.read_excel(excel_path)
    with open(geojson_path, "r", encoding="utf-8") as f:
        power_geo = json.load(f)

    G = nx.Graph()
    coord_to_node = {}

    # 1. Add Substation Nodes from Excel
    for idx, row in df_p.iterrows():
        c = (round(row["longitude"], 6), round(row["latitude"], 6))
        node_id = f"SUB_{idx+1}"
        
        # Rating parsing
        rating_str = str(row.get("rating", "unknown"))
        cap_mva = 250.0  # default
        if "400" in rating_str:
            cap_mva = 400.0
        elif "450" in rating_str:
            cap_mva = 450.0
        elif "100" in rating_str:
            cap_mva = 100.0
        elif "220" in str(row.get("voltage", "")):
            cap_mva = 300.0

        coord_to_node[c] = node_id
        G.add_node(
            node_id,
            node_id=node_id,
            layer="power",
            entity_type="substation",
            name=str(row.get("name", f"Substation_{idx+1}")),
            operator=str(row.get("operator", "KPTCL")),
            substation_type=str(row.get("substation", "distribution")),
            voltage=str(row.get("voltage", "220000;66000")),
            rating=rating_str,
            capacity=cap_mva,
            current_load=cap_mva * baseline_load_ratio,
            load_ratio=baseline_load_ratio,
            state="normal",
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"])
        )

    # 2. Add Transmission Lines & Intermediate Tower Nodes from GeoJSON
    tower_counter = 0
    endpoints = []
    for feat in power_geo.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates", [])
            prev_node = None
            line_id = props.get("id", f"line_{len(endpoints)//2+1}")
            voltage_str = props.get("voltage", "220kV")
            
            # Line capacity estimation
            line_cap = 350.0 if "220" in voltage_str else 150.0

            for i, pt in enumerate(coords):
                c = (round(pt[0], 6), round(pt[1], 6))
                if c not in coord_to_node:
                    tower_counter += 1
                    nid = f"TOW_{tower_counter}"
                    coord_to_node[c] = nid
                    G.add_node(
                        nid,
                        node_id=nid,
                        layer="power",
                        entity_type="tower_junction",
                        name=f"Tower_{tower_counter}",
                        operator=props.get("operator", "KPTCL"),
                        substation_type="tower",
                        voltage=voltage_str,
                        rating="N/A",
                        capacity=line_cap,
                        current_load=line_cap * baseline_load_ratio,
                        load_ratio=baseline_load_ratio,
                        state="normal",
                        latitude=pt[1],
                        longitude=pt[0]
                    )
                curr_node = coord_to_node[c]
                if prev_node and prev_node != curr_node:
                    lat1, lon1 = G.nodes[prev_node]["latitude"], G.nodes[prev_node]["longitude"]
                    lat2, lon2 = G.nodes[curr_node]["latitude"], G.nodes[curr_node]["longitude"]
                    dist = haversine(lat1, lon1, lat2, lon2)
                    G.add_edge(
                        prev_node, curr_node,
                        edge_id=f"{line_id}_{i}",
                        edge_type="transmission_line",
                        voltage=voltage_str,
                        length=dist,
                        capacity=line_cap,
                        current_load=line_cap * baseline_load_ratio,
                        load_ratio=baseline_load_ratio,
                        state="normal"
                    )
                prev_node = curr_node
                if i == 0 or i == len(coords) - 1:
                    endpoints.append(curr_node)

    # 3. Snap Endpoints across Switchyards/Corridors
    if snap_tolerance_m > 0 and endpoints:
        ep_unique = list(set(endpoints))
        ep_coords = np.array([[G.nodes[n]["longitude"], G.nodes[n]["latitude"]] for n in ep_unique])
        tree = cKDTree(ep_coords)
        thresh_deg = snap_tolerance_m / 111000.0
        pairs = tree.query_pairs(thresh_deg)
        snapped_count = 0
        for i, j in pairs:
            u, v = ep_unique[i], ep_unique[j]
            if u != v and not G.has_edge(u, v):
                dist = haversine(G.nodes[u]["latitude"], G.nodes[u]["longitude"],
                                 G.nodes[v]["latitude"], G.nodes[v]["longitude"])
                G.add_edge(
                    u, v,
                    edge_id=f"snap_{snapped_count+1}",
                    edge_type="switchyard_connector",
                    voltage="220kV",
                    length=dist,
                    capacity=350.0,
                    current_load=350.0 * baseline_load_ratio,
                    load_ratio=baseline_load_ratio,
                    state="normal"
                )
                snapped_count += 1
        logger.info(f"Power network: snapped {snapped_count} switchyard/tower gaps <= {snap_tolerance_m}m.")

    logger.info(f"Power Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
    return G


# =============================================================================
# 2. WATER NETWORK BUILDER
# =============================================================================

def build_water_graph(
    excel_path=r"d:\new urban el\processed\water_infrastructure.xlsx",
    geojson_path=r"d:\new urban el\processed\water_network_geojson.json",
    baseline_load_ratio=0.60
):
    """
    Builds G_water combining 53 facilities from Excel and 3,168 pipeline segments
    from GeoJSON. Snaps each facility to its nearest pipeline junction via a feeder edge.
    """
    logger.info("Building Water Network...")
    df_w = pd.read_excel(excel_path)
    with open(geojson_path, "r", encoding="utf-8") as f:
        water_geo = json.load(f)

    G = nx.Graph()
    coord_to_node = {}
    junction_counter = 0

    # 1. Add Pipelines and Distribution Junctions from GeoJSON
    for feat in water_geo.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        
        pipe_id = props.get("id", f"pipe_{G.number_of_edges()+1}")
        pipe_name = props.get("name", "pipeline")
        prev_node = None
        
        for pt in coords:
            c = (round(pt[0], 6), round(pt[1], 6))
            if c not in coord_to_node:
                junction_counter += 1
                nid = f"WJ_{junction_counter}"
                coord_to_node[c] = nid
                G.add_node(
                    nid,
                    node_id=nid,
                    layer="water",
                    entity_type="pipe_junction",
                    name=f"Junction_{junction_counter}",
                    operator="BWSSB",
                    facility_type="junction",
                    capacity=25.0,  # MLD hydraulic flow capacity
                    supply=0.0,
                    demand=0.5,    # baseline localized demand in MLD
                    received_flow=0.5,
                    adequacy=1.0,
                    state="normal",
                    latitude=pt[1],
                    longitude=pt[0]
                )
            curr_node = coord_to_node[c]
            if prev_node and prev_node != curr_node:
                if not G.has_edge(prev_node, curr_node):
                    lat1, lon1 = G.nodes[prev_node]["latitude"], G.nodes[prev_node]["longitude"]
                    lat2, lon2 = G.nodes[curr_node]["latitude"], G.nodes[curr_node]["longitude"]
                    dist = haversine(lat1, lon1, lat2, lon2)
                    G.add_edge(
                        prev_node, curr_node,
                        edge_id=pipe_id,
                        edge_type="pipeline",
                        name=pipe_name,
                        length=dist,
                        capacity=30.0, # MLD maximum pipe flow
                        current_flow=30.0 * baseline_load_ratio,
                        load_ratio=baseline_load_ratio,
                        state="normal"
                    )
            prev_node = curr_node

    # 2. Add and Snap Water Facilities from Excel
    pipe_nodes = list(G.nodes())
    pipe_coords = np.array([[G.nodes[n]["longitude"], G.nodes[n]["latitude"]] for n in pipe_nodes])
    tree = cKDTree(pipe_coords)

    for idx, row in df_w.iterrows():
        f_lon = float(row["longitude"])
        f_lat = float(row["latitude"])
        fac_id = f"FAC_{idx+1}"
        fac_type = str(row.get("type", "Water Works"))
        fac_name = str(row.get("name", f"Facility_{idx+1}"))
        
        # Determine capacity based on facility type
        if "Reservoir" in fac_type:
            cap_mld = 80.0
            sup_mld = 60.0
        elif "Tank" in fac_type:
            cap_mld = 30.0
            sup_mld = 25.0
        else: # Major Water Works / Pumping station
            cap_mld = 150.0
            sup_mld = 120.0

        G.add_node(
            fac_id,
            node_id=fac_id,
            layer="water",
            entity_type="facility",
            name=fac_name,
            operator=str(row.get("operator", "BWSSB")),
            facility_type=fac_type,
            man_made=str(row.get("man_made", "water_works")),
            capacity=cap_mld,
            supply=sup_mld,
            demand=0.0,
            received_flow=sup_mld,
            adequacy=1.0,
            state="normal",
            latitude=f_lat,
            longitude=f_lon
        )

        # Snap to nearest pipe node
        dist_deg, nearest_idx = tree.query([f_lon, f_lat])
        nearest_node = pipe_nodes[nearest_idx]
        p_lat = G.nodes[nearest_node]["latitude"]
        p_lon = G.nodes[nearest_node]["longitude"]
        dist_m = haversine(f_lat, f_lon, p_lat, p_lon)

        G.add_edge(
            fac_id, nearest_node,
            edge_id=f"feeder_{idx+1}",
            edge_type="facility_feeder",
            name=f"Feed to {fac_name}",
            length=dist_m,
            capacity=cap_mld,
            current_flow=sup_mld,
            load_ratio=sup_mld / cap_mld,
            state="normal"
        )

    logger.info(f"Water Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
    return G


# =============================================================================
# 3. ROAD NETWORK BUILDER
# =============================================================================

def build_road_graph(
    excel_path=r"d:\new urban el\processed\road_infrastructure.xlsx",
    geojson_path=r"d:\new urban el\processed\road_network_geojson.json",
    corridor_filter=None,  # e.g. "silk_board", "hebbal", "orr_it_corridor" or None for primary network
    max_features=None,
    baseline_load_ratio=0.60
):
    """
    Builds G_road combining intersection/crossing nodes from Excel and road links
    from GeoJSON.
    Calculates BPR travel time, capacities, and free-flow speeds.
    """
    logger.info(f"Building Road Network (corridor={corridor_filter})...")
    df_r = pd.read_excel(excel_path)
    
    # Pre-index Excel nodes by rounded coordinate
    coord_to_excel = {}
    for idx, row in df_r.iterrows():
        c = (round(row["longitude"], 6), round(row["latitude"], 6))
        coord_to_excel[c] = row

    with open(geojson_path, "r", encoding="utf-8") as f:
        road_geo = json.load(f)

    G = nx.Graph()
    coord_to_node = {}
    node_counter = 0

    features = road_geo.get("features", [])
    if max_features:
        features = features[:max_features]

    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        road_id = str(props.get("id", f"road_{G.number_of_edges()+1}"))
        road_name = str(props.get("name", "Road Link"))
        road_class = str(props.get("class", "primary"))
        
        # Corridor filtering if specified
        if corridor_filter and corridor_filter.lower() not in road_name.lower():
            continue

        # Road parameters
        if road_class in ["motorway", "trunk"]:
            speed_kmh = 60.0
            capacity_vph = 3600.0  # 2 lanes per direction ~ 1800 vph/lane
        elif road_class in ["primary"]:
            speed_kmh = 45.0
            capacity_vph = 2400.0
        elif road_class in ["secondary"]:
            speed_kmh = 35.0
            capacity_vph = 1800.0
        else:
            speed_kmh = 30.0
            capacity_vph = 1200.0

        speed_ms = speed_kmh / 3.6
        prev_node = None

        for pt in coords:
            c = (round(pt[0], 6), round(pt[1], 6))
            if c not in coord_to_node:
                node_counter += 1
                nid = f"RN_{node_counter}"
                coord_to_node[c] = nid
                
                # Check match in Excel
                if c in coord_to_excel:
                    erow = coord_to_excel[c]
                    G.add_node(
                        nid,
                        node_id=nid,
                        layer="road",
                        osm_node_id=int(erow["node_id"]),
                        entity_type="intersection",
                        road_node_type=str(erow["road_node_type"]),
                        highway_type=str(erow["highway_type"]),
                        importance=str(erow["importance"]),
                        traffic_signal=str(erow.get("traffic_signal", "none")),
                        state="normal",
                        latitude=float(erow["latitude"]),
                        longitude=float(erow["longitude"])
                    )
                else:
                    G.add_node(
                        nid,
                        node_id=nid,
                        layer="road",
                        osm_node_id=-1,
                        entity_type="road_junction",
                        road_node_type="Intermediate Node",
                        highway_type="normal",
                        importance="Normal",
                        traffic_signal="none",
                        state="normal",
                        latitude=pt[1],
                        longitude=pt[0]
                    )
            curr_node = coord_to_node[c]
            if prev_node and prev_node != curr_node:
                if not G.has_edge(prev_node, curr_node):
                    lat1, lon1 = G.nodes[prev_node]["latitude"], G.nodes[prev_node]["longitude"]
                    lat2, lon2 = G.nodes[curr_node]["latitude"], G.nodes[curr_node]["longitude"]
                    dist = haversine(lat1, lon1, lat2, lon2)
                    if dist < 0.1:
                        dist = 1.0  # minimum 1 meter to avoid division by zero
                    
                    t0_sec = dist / speed_ms
                    init_vol = capacity_vph * baseline_load_ratio
                    init_vc = baseline_load_ratio
                    # BPR Travel Time: T0 * (1 + 0.15 * (V/C)^4)
                    init_time = t0_sec * (1.0 + 0.15 * (init_vc ** 4))

                    G.add_edge(
                        prev_node, curr_node,
                        edge_id=road_id,
                        road_name=road_name,
                        road_class=road_class,
                        length=dist,
                        free_flow_speed=speed_kmh,
                        free_flow_time=t0_sec,
                        capacity=capacity_vph,
                        current_load=init_vol,
                        load_ratio=init_vc,
                        current_travel_time=init_time,
                        state="normal"
                    )
            prev_node = curr_node

    logger.info(f"Road Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
    return G


def build_corridor_road_graph(
    corridor_geojson_path,
    excel_path=r"d:\new urban el\processed\road_infrastructure.xlsx",
    baseline_load_ratio=0.65
):
    """
    Builds a road graph specifically for a focal corridor (e.g. Silk Board, Hebbal, ORR)
    using the provided GeoJSON file and matching Excel nodes.
    """
    logger.info(f"Building focal corridor road graph from: {corridor_geojson_path}")
    df_r = pd.read_excel(excel_path)
    coord_to_excel = {}
    for idx, row in df_r.iterrows():
        c = (round(row["longitude"], 6), round(row["latitude"], 6))
        coord_to_excel[c] = row

    with open(corridor_geojson_path, "r", encoding="utf-8") as f:
        corridor_geo = json.load(f)

    G = nx.Graph()
    coord_to_node = {}
    node_counter = 0

    for feat in corridor_geo.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        road_id = str(props.get("id", f"corr_{G.number_of_edges()+1}"))
        road_name = str(props.get("name", "Corridor Link"))
        road_class = str(props.get("class", props.get("highway", "primary")))

        if road_class in ["motorway", "trunk", "trunk_link"]:
            speed_kmh = 60.0
            capacity_vph = 3600.0
        elif road_class in ["primary", "primary_link"]:
            speed_kmh = 45.0
            capacity_vph = 2400.0
        elif road_class in ["secondary", "secondary_link"]:
            speed_kmh = 35.0
            capacity_vph = 1800.0
        else:
            speed_kmh = 30.0
            capacity_vph = 1400.0

        speed_ms = speed_kmh / 3.6
        prev_node = None

        for pt in coords:
            c = (round(pt[0], 6), round(pt[1], 6))
            if c not in coord_to_node:
                node_counter += 1
                nid = f"CRN_{node_counter}"
                coord_to_node[c] = nid
                if c in coord_to_excel:
                    erow = coord_to_excel[c]
                    G.add_node(
                        nid,
                        node_id=nid,
                        layer="road",
                        osm_node_id=int(erow["node_id"]),
                        entity_type="intersection",
                        road_node_type=str(erow["road_node_type"]),
                        highway_type=str(erow["highway_type"]),
                        importance=str(erow["importance"]),
                        traffic_signal=str(erow.get("traffic_signal", "none")),
                        state="normal",
                        latitude=float(erow["latitude"]),
                        longitude=float(erow["longitude"])
                    )
                else:
                    G.add_node(
                        nid,
                        node_id=nid,
                        layer="road",
                        osm_node_id=-1,
                        entity_type="road_junction",
                        road_node_type="Intermediate Node",
                        highway_type="normal",
                        importance="Normal",
                        traffic_signal="none",
                        state="normal",
                        latitude=pt[1],
                        longitude=pt[0]
                    )
            curr_node = coord_to_node[c]
            if prev_node and prev_node != curr_node:
                if not G.has_edge(prev_node, curr_node):
                    lat1, lon1 = G.nodes[prev_node]["latitude"], G.nodes[prev_node]["longitude"]
                    lat2, lon2 = G.nodes[curr_node]["latitude"], G.nodes[curr_node]["longitude"]
                    dist = haversine(lat1, lon1, lat2, lon2)
                    if dist < 0.1:
                        dist = 1.0
                    t0_sec = dist / speed_ms
                    init_vol = capacity_vph * baseline_load_ratio
                    init_vc = baseline_load_ratio
                    init_time = t0_sec * (1.0 + 0.15 * (init_vc ** 4))

                    G.add_edge(
                        prev_node, curr_node,
                        edge_id=road_id,
                        road_name=road_name,
                        road_class=road_class,
                        length=dist,
                        free_flow_speed=speed_kmh,
                        free_flow_time=t0_sec,
                        capacity=capacity_vph,
                        current_load=init_vol,
                        load_ratio=init_vc,
                        current_travel_time=init_time,
                        state="normal"
                    )
            prev_node = curr_node

    logger.info(f"Corridor Road Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
    return G


if __name__ == "__main__":
    print("Testing Graph Builders...")
    gp = build_power_graph()
    print(f"Power: {gp.number_of_nodes()} nodes, {gp.number_of_edges()} edges")
    gw = build_water_graph()
    print(f"Water: {gw.number_of_nodes()} nodes, {gw.number_of_edges()} edges")
    # Test corridor builder on Silk Board
    silk_path = r"d:\urban el\data\processed\silk_board.geojson"
    if os.path.exists(silk_path):
        gr_silk = build_corridor_road_graph(silk_path)
        print(f"Road (Silk Board): {gr_silk.number_of_nodes()} nodes, {gr_silk.number_of_edges()} edges")
