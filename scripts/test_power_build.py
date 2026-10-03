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

# Let's inspect power graph construction
print("=== TESTING POWER GRAPH CONSTRUCTION ===")
df_p = pd.read_excel(os.path.join(processed_dir, "power_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    power_geo = json.load(f)

G_power = nx.Graph()
coord_to_pnode = {}
# Add substations from Excel
for idx, row in df_p.iterrows():
    c = (round(row['longitude'], 6), round(row['latitude'], 6))
    node_id = f"SUB_{idx+1}"
    coord_to_pnode[c] = node_id
    G_power.add_node(
        node_id,
        entity_type="substation",
        name=str(row.get('name', 'N/A')),
        operator=str(row.get('operator', 'KPTCL')),
        substation_type=str(row.get('substation', 'distribution')),
        voltage=str(row.get('voltage', '66000;11000')),
        rating=str(row.get('rating', 'unknown')),
        latitude=row['latitude'],
        longitude=row['longitude']
    )

print(f"Added {G_power.number_of_nodes()} substation nodes.")

# Add transmission lines from GeoJSON
t_counter = 0
for feat in power_geo['features']:
    props = feat.get('properties', {})
    geom = feat.get('geometry', {})
    if geom.get('type') == 'LineString':
        coords = geom.get('coordinates', [])
        prev_node = None
        for pt in coords:
            c = (round(pt[0], 6), round(pt[1], 6))
            if c not in coord_to_pnode:
                t_counter += 1
                node_id = f"TOWER_{t_counter}"
                coord_to_pnode[c] = node_id
                G_power.add_node(
                    node_id,
                    entity_type="tower_junction",
                    name=f"Tower_{t_counter}",
                    voltage=props.get('voltage', '220kV'),
                    latitude=pt[1],
                    longitude=pt[0]
                )
            curr_node = coord_to_pnode[c]
            if prev_node and prev_node != curr_node:
                lat1, lon1 = G_power.nodes[prev_node]['latitude'], G_power.nodes[prev_node]['longitude']
                lat2, lon2 = G_power.nodes[curr_node]['latitude'], G_power.nodes[curr_node]['longitude']
                dist = haversine(lat1, lon1, lat2, lon2)
                G_power.add_edge(prev_node, curr_node, length=dist, voltage=props.get('voltage', '220kV'), edge_type="transmission_line")
            prev_node = curr_node

print(f"G_power built: {G_power.number_of_nodes()} nodes ({sum(1 for _, d in G_power.nodes(data=True) if d['entity_type']=='substation')} substations, {sum(1 for _, d in G_power.nodes(data=True) if d['entity_type']=='tower_junction')} tower junctions)")
print(f"G_power edges: {G_power.number_of_edges()}")
components = list(nx.connected_components(G_power))
print(f"Connected components: {len(components)}, Largest: {len(max(components, key=len))} nodes")

# Check how many substations are in the largest component
largest_c = max(components, key=len)
subs_in_largest = sum(1 for n in largest_c if G_power.nodes[n]['entity_type'] == 'substation')
print(f"Substations in largest connected component: {subs_in_largest} / {len(df_p)}")
