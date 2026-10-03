import sys
import json
import os
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
processed_dir = r"d:\new urban el\processed"

# 1. ROAD INVESTIGATION
df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

excel_coords = set(zip(np.round(df_r['longitude'].values, 6), np.round(df_r['latitude'].values, 6)))
print(f"Total road excel nodes: {len(df_r)}, unique coords: {len(excel_coords)}")

# Collect all unique vertices from GeoJSON lines
all_geo_coords = set()
start_end_coords = set()
line_count = len(road_geo['features'])
coords_per_line = []

for feat in road_geo['features']:
    coords = feat['geometry']['coordinates']
    coords_per_line.append(len(coords))
    s = (round(coords[0][0], 6), round(coords[0][1], 6))
    e = (round(coords[-1][0], 6), round(coords[-1][1], 6))
    start_end_coords.add(s)
    start_end_coords.add(e)
    for c in coords:
        all_geo_coords.add((round(c[0], 6), round(c[1], 6)))

print(f"Road GeoJSON: {line_count} lines")
print(f"Unique start/end endpoints: {len(start_end_coords)}")
print(f"Unique total vertices: {len(all_geo_coords)}")
print(f"Avg points per line: {np.mean(coords_per_line):.2f}, min: {np.min(coords_per_line)}, max: {np.max(coords_per_line)}")

# Overlap between Excel nodes and GeoJSON vertices
in_all_geo = len(excel_coords.intersection(all_geo_coords))
in_endpoints = len(excel_coords.intersection(start_end_coords))
print(f"Excel nodes present in GeoJSON total vertices: {in_all_geo} / {len(excel_coords)} ({in_all_geo/len(excel_coords)*100:.1f}%)")
print(f"Excel nodes present in GeoJSON start/end: {in_endpoints} / {len(excel_coords)} ({in_endpoints/len(excel_coords)*100:.1f}%)")

# How many GeoJSON vertices are NOT in Excel?
geo_not_in_excel = len(all_geo_coords - excel_coords)
print(f"GeoJSON vertices not in Excel: {geo_not_in_excel}")

# 2. WATER INVESTIGATION
df_w = pd.read_excel(os.path.join(processed_dir, "water_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    water_geo = json.load(f)

w_excel_coords = set(zip(np.round(df_w['longitude'].values, 6), np.round(df_w['latitude'].values, 6)))
w_all_geo_coords = set()
w_start_end = set()
for feat in water_geo['features']:
    if feat['geometry']['type'] == 'LineString':
        coords = feat['geometry']['coordinates']
        w_start_end.add((round(coords[0][0], 6), round(coords[0][1], 6)))
        w_start_end.add((round(coords[-1][0], 6), round(coords[-1][1], 6)))
        for c in coords:
            w_all_geo_coords.add((round(c[0], 6), round(c[1], 6)))

print(f"\nWater: unique Excel coords: {len(w_excel_coords)}")
print(f"Water: unique GeoJSON vertices: {len(w_all_geo_coords)}, start/ends: {len(w_start_end)}")
print(f"Water GeoJSON features: {len(water_geo['features'])}")

# Check distance from each water Excel node to nearest water GeoJSON vertex
from scipy.spatial import cKDTree
w_geo_arr = np.array(list(w_all_geo_coords))
w_tree = cKDTree(w_geo_arr)
w_excel_arr = np.array(list(w_excel_coords))
dists, idxs = w_tree.query(w_excel_arr)
# Convert degrees to meters approx (1 deg lat ~ 111km, 1 deg lon ~ 108km at 13N)
dists_m = dists * 111000
print(f"Water facility distance to nearest pipeline vertex (meters):")
print(f"  Min: {dists_m.min():.1f}m, Median: {np.median(dists_m):.1f}m, Mean: {np.mean(dists_m):.1f}m, Max: {dists_m.max():.1f}m")
print(f"  Within 50m: {np.sum(dists_m <= 50)} / {len(dists_m)}")
print(f"  Within 100m: {np.sum(dists_m <= 100)} / {len(dists_m)}")
print(f"  Within 250m: {np.sum(dists_m <= 250)} / {len(dists_m)}")
