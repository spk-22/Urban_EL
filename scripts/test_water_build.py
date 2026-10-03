import sys
import json
import os
import math
import pandas as pd
import numpy as np
import networkx as nx

sys.stdout.reconfigure(encoding='utf-8')
processed_dir = r"d:\new urban el\processed"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Load Excel water nodes
print("Loading water Excel facilities...")
df_w = pd.read_excel(os.path.join(processed_dir, "water_infrastructure.xlsx"))
print(f"Loaded {len(df_w)} facilities from Excel.")

# Load Water GeoJSON
print("Loading water GeoJSON...")
with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    water_geo = json.load(f)

G = nx.Graph()
coord_to_nid = {}
nid_counter = 0

print("Building pipe network from GeoJSON features...")
for feat in water_geo['features']:
    props = feat.get('properties', {})
    geom = feat.get('geometry', {})
    if geom.get('type') != 'LineString':
        continue
    coords = geom.get('coordinates', [])
    if len(coords) < 2:
        continue
    
    prev_nid = None
    for pt in coords:
        c = (round(pt[0], 6), round(pt[1], 6))
        if c not in coord_to_nid:
            nid_counter += 1
            nid = f"W_{nid_counter}"
            coord_to_nid[c] = nid
            G.add_node(
                nid,
                facility_id=-1,
                entity_type='pipe_junction',
                name=props.get('name', f"Junction_{nid_counter}"),
                water_type='junction',
                latitude=pt[1],
                longitude=pt[0]
            )
        curr_nid = coord_to_nid[c]
        if prev_nid and prev_nid != curr_nid:
            if not G.has_edge(prev_nid, curr_nid):
                n1 = G.nodes[prev_nid]
                n2 = G.nodes[curr_nid]
                dist = haversine(n1['latitude'], n1['longitude'], n2['latitude'], n2['longitude'])
                G.add_edge(
                    prev_nid, curr_nid,
                    pipe_id=props.get('id', 'N/A'),
                    name=props.get('name', 'N/A'),
                    pipe_type=props.get('type', 'pipeline'),
                    length=dist
                )
        prev_nid = curr_nid

print(f"Base pipe graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
comps = sorted(nx.connected_components(G), key=len, reverse=True)
print(f"Connected components in raw pipe network: {len(comps)}, top 5 sizes: {[len(c) for c in comps[:5]]}")

# Now connect Excel water facilities to the nearest pipeline network junction!
# Spatial index
from scipy.spatial import cKDTree
pipe_nodes = list(G.nodes())
pipe_coords = np.array([[G.nodes[n]['longitude'], G.nodes[n]['latitude']] for n in pipe_nodes])
tree = cKDTree(pipe_coords)

connected_facilities = 0
for idx, row in df_w.iterrows():
    f_lon = row['longitude']
    f_lat = row['latitude']
    f_node_id = f"FACILITY_{idx+1}"
    
    # Query nearest pipe node
    dist_deg, nearest_idx = tree.query([f_lon, f_lat])
    nearest_pnode = pipe_nodes[nearest_idx]
    p_lat = G.nodes[nearest_pnode]['latitude']
    p_lon = G.nodes[nearest_pnode]['longitude']
    dist_m = haversine(f_lat, f_lon, p_lat, p_lon)
    
    G.add_node(
        f_node_id,
        facility_id=idx+1,
        entity_type='facility',
        facility_type=str(row['type']),
        name=str(row.get('name', 'N/A')),
        operator=str(row.get('operator', 'BWSSB')),
        man_made=str(row.get('man_made', 'water_works')),
        latitude=f_lat,
        longitude=f_lon,
        water_type=str(row['type'])
    )
    # Add feeder/connection edge to pipeline network
    G.add_edge(
        f_node_id, nearest_pnode,
        pipe_id=f"feeder_{idx+1}",
        name=f"Connection to {row.get('name', 'Facility')}",
        pipe_type='feeder',
        length=dist_m
    )
    connected_facilities += 1

print(f"Added and connected {connected_facilities} facilities to water network.")
print(f"Total nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}")
comps2 = sorted(nx.connected_components(G), key=len, reverse=True)
print(f"Connected components after facility attachment: {len(comps2)}, top 5: {[len(c) for c in comps2[:5]]}")
