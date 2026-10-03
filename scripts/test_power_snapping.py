import sys
import json
import os
import math
import pandas as pd
import numpy as np
import networkx as nx
from scipy.spatial import cKDTree

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

df_p = pd.read_excel(os.path.join(processed_dir, "power_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    power_geo = json.load(f)

# Test different snapping thresholds (in meters)
for snap_dist_m in [0, 25, 50, 75, 100]:
    G = nx.Graph()
    coord_to_node = {}
    
    # First add substations
    for idx, row in df_p.iterrows():
        c = (round(row['longitude'], 7), round(row['latitude'], 7))
        nid = f"SUB_{idx+1}"
        if c not in coord_to_node:
            coord_to_node[c] = nid
            G.add_node(
                nid,
                entity_type="substation",
                name=row['name'],
                operator=row['operator'],
                voltage=row['voltage'],
                substation_type=row['substation'],
                rating=row['rating'],
                latitude=row['latitude'],
                longitude=row['longitude']
            )
    
    # Add transmission lines
    t_cnt = 0
    endpoints = []
    for feat in power_geo['features']:
        if feat['geometry']['type'] == 'LineString':
            coords = feat['geometry']['coordinates']
            prev = None
            for i, pt in enumerate(coords):
                c = (round(pt[0], 7), round(pt[1], 7))
                if c not in coord_to_node:
                    t_cnt += 1
                    nid = f"T_{t_cnt}"
                    coord_to_node[c] = nid
                    G.add_node(
                        nid,
                        entity_type="tower_junction",
                        name=f"Tower_{t_cnt}",
                        voltage=feat['properties'].get('voltage', '220kV'),
                        latitude=pt[1],
                        longitude=pt[0]
                    )
                curr = coord_to_node[c]
                if prev and prev != curr:
                    dist = haversine(G.nodes[prev]['latitude'], G.nodes[prev]['longitude'],
                                     G.nodes[curr]['latitude'], G.nodes[curr]['longitude'])
                    G.add_edge(prev, curr, length=dist, voltage=feat['properties'].get('voltage', '220kV'))
                prev = curr
                if i == 0 or i == len(coords) - 1:
                    endpoints.append(curr)
    
    # Snap endpoints if snap_dist_m > 0
    if snap_dist_m > 0:
        ep_nodes = list(set(endpoints))
        ep_coords = np.array([[G.nodes[n]['longitude'], G.nodes[n]['latitude']] for n in ep_nodes])
        # Approximate meters to degrees: 1 deg ~ 111,000m
        thresh_deg = snap_dist_m / 111000.0
        tree = cKDTree(ep_coords)
        pairs = tree.query_pairs(thresh_deg)
        for i, j in pairs:
            u, v = ep_nodes[i], ep_nodes[j]
            if u != v and not G.has_edge(u, v):
                dist = haversine(G.nodes[u]['latitude'], G.nodes[u]['longitude'],
                                 G.nodes[v]['latitude'], G.nodes[v]['longitude'])
                G.add_edge(u, v, length=dist, voltage='220kV', edge_type='switchyard_connector')

    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    subs_in_comps = []
    for c in comps:
        s_count = sum(1 for n in c if G.nodes[n]['entity_type'] == 'substation')
        if s_count > 0:
            subs_in_comps.append(s_count)
    print(f"Snap {snap_dist_m:3d}m: Nodes={G.number_of_nodes()}, Edges={G.number_of_edges()}, Comps={len(comps)}, LargestComp={len(comps[0])}, SubsInLargest={subs_in_comps[0] if subs_in_comps else 0}/37")
