import os
import json
import pandas as pd
import numpy as np

processed_dir = r"d:\new urban el\processed"

# 1. POWER
df_p = pd.read_excel(os.path.join(processed_dir, "power_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    power_geo = json.load(f)

# Collect all line endpoints
p_endpoints = []
for feat in power_geo['features']:
    if feat['geometry']['type'] == 'LineString':
        coords = feat['geometry']['coordinates']
        p_endpoints.append(coords[0])
        p_endpoints.append(coords[-1])
    elif feat['geometry']['type'] == 'Point':
        p_endpoints.append(feat['geometry']['coordinates'])

p_endpoints = np.array(p_endpoints)
print("Power GeoJSON total endpoints/points:", len(p_endpoints))
print("Power Excel nodes count:", len(df_p))

# Check distance from each Excel power node to closest GeoJSON point/endpoint
from scipy.spatial import cKDTree
p_tree = cKDTree(p_endpoints)
excel_p_coords = np.column_stack([df_p['longitude'].values, df_p['latitude'].values])
dists, idxs = p_tree.query(excel_p_coords)
print("Power: Distances from Excel nodes to closest GeoJSON coordinate (in degrees):")
print(f"  Min: {dists.min():.6f}, Median: {np.median(dists):.6f}, Max: {dists.max():.6f}")
print(f"  Nodes with dist == 0: {np.sum(dists < 1e-7)} / {len(df_p)}")
print(f"  Nodes with dist < 0.001 (~100m): {np.sum(dists < 0.001)} / {len(df_p)}")

# 2. WATER
df_w = pd.read_excel(os.path.join(processed_dir, "water_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    water_geo = json.load(f)

w_endpoints = []
for feat in water_geo['features']:
    if feat['geometry']['type'] == 'LineString':
        coords = feat['geometry']['coordinates']
        w_endpoints.append(coords[0])
        w_endpoints.append(coords[-1])
    elif feat['geometry']['type'] == 'Point':
        w_endpoints.append(feat['geometry']['coordinates'])

w_endpoints = np.array(w_endpoints)
print("\nWater GeoJSON total endpoints/points:", len(w_endpoints))
print("Water Excel nodes count:", len(df_w))

w_tree = cKDTree(w_endpoints)
excel_w_coords = np.column_stack([df_w['longitude'].values, df_w['latitude'].values])
dists_w, idxs_w = w_tree.query(excel_w_coords)
print("Water: Distances from Excel nodes to closest GeoJSON coordinate (in degrees):")
print(f"  Min: {dists_w.min():.6f}, Median: {np.median(dists_w):.6f}, Max: {dists_w.max():.6f}")
print(f"  Nodes with dist == 0: {np.sum(dists_w < 1e-7)} / {len(df_w)}")
print(f"  Nodes with dist < 0.001 (~100m): {np.sum(dists_w < 0.001)} / {len(df_w)}")

# 3. ROAD
df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
print("\nRoad Excel nodes count:", len(df_r))
# Let's inspect road GeoJSON line endpoints and properties
# Also check if road GeoJSON coordinates match road Excel coordinates!
excel_node_dict = set(zip(np.round(df_r['longitude'].values, 7), np.round(df_r['latitude'].values, 7)))
print("Unique rounded coords in road Excel:", len(excel_node_dict))

with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

matched_start = 0
matched_end = 0
matched_any = 0
sample_check = 1000
for feat in road_geo['features'][:sample_check]:
    coords = feat['geometry']['coordinates']
    s = (round(coords[0][0], 7), round(coords[0][1], 7))
    e = (round(coords[-1][0], 7), round(coords[-1][1], 7))
    if s in excel_node_dict:
        matched_start += 1
    if e in excel_node_dict:
        matched_end += 1
    if any((round(c[0], 7), round(c[1], 7)) in excel_node_dict for c in coords):
        matched_any += 1

print(f"Road sample {sample_check} lines matching Excel nodes:")
print(f"  Start matched: {matched_start} / {sample_check}")
print(f"  End matched: {matched_end} / {sample_check}")
print(f"  Any vertex matched: {matched_any} / {sample_check}")
