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

# Load Excel nodes
print("Loading road Excel nodes...")
df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
coord_to_excel = {}
for idx, row in df_r.iterrows():
    c = (round(row['longitude'], 6), round(row['latitude'], 6))
    coord_to_excel[c] = row

print(f"Loaded {len(coord_to_excel)} unique excel node coords.")

# Load GeoJSON
print("Loading road GeoJSON...")
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

G = nx.Graph()
coord_to_nid = {}
nid_counter = 0

print("Building graph from GeoJSON features...")
for feat in road_geo['features']:
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
            nid = f"R_{nid_counter}"
            coord_to_nid[c] = nid
            
            # Check if this node is in Excel
            if c in coord_to_excel:
                erow = coord_to_excel[c]
                G.add_node(
                    nid,
                    osm_node_id=int(erow['node_id']),
                    latitude=float(erow['latitude']),
                    longitude=float(erow['longitude']),
                    road_node_type=str(erow['road_node_type']),
                    highway_type=str(erow['highway_type']),
                    importance=str(erow['importance']),
                    traffic_signal=str(erow['traffic_signal']) if pd.notnull(erow['traffic_signal']) else 'none',
                    source='excel_and_geojson'
                )
            else:
                G.add_node(
                    nid,
                    osm_node_id=-1,
                    latitude=pt[1],
                    longitude=pt[0],
                    road_node_type='Intermediate Road Node',
                    highway_type=props.get('class', 'primary'),
                    importance='Normal',
                    traffic_signal='none',
                    source='geojson_only'
                )
        curr_nid = coord_to_nid[c]
        if prev_nid and prev_nid != curr_nid:
            if not G.has_edge(prev_nid, curr_nid):
                n1 = G.nodes[prev_nid]
                n2 = G.nodes[curr_nid]
                dist = haversine(n1['latitude'], n1['longitude'], n2['latitude'], n2['longitude'])
                G.add_edge(
                    prev_nid, curr_nid,
                    road_id=props.get('id', 'N/A'),
                    road_name=props.get('name', 'N/A'),
                    road_class=props.get('class', 'primary'),
                    length=dist
                )
        prev_nid = curr_nid

print(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
comps = list(nx.connected_components(G))
print(f"Connected components: {len(comps)}")
largest = max(comps, key=len)
print(f"Largest component size: {len(largest)} nodes ({len(largest)/G.number_of_nodes()*100:.1f}%)")
