import sys
import json
import os
import pandas as pd
import numpy as np
import networkx as nx
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
processed_dir = r"d:\new urban el\processed"

print("==================================================")
print("1. POWER GRAPH RECONSTRUCTION INVESTIGATION")
print("==================================================")
df_p = pd.read_excel(os.path.join(processed_dir, "power_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    power_geo = json.load(f)

# Power nodes: 44 substations
# Let's inspect power transmission lines in GeoJSON
p_lines = [feat for feat in power_geo['features'] if feat['geometry']['type'] == 'LineString']
p_points = [feat for feat in power_geo['features'] if feat['geometry']['type'] == 'Point']
print(f"Power: {len(df_p)} substations in Excel, {len(p_lines)} LineStrings, {len(p_points)} Points in GeoJSON.")

# Check coordinates of substations vs endpoints of power lines
# Let's see how lines connect to substations or to each other
power_nodes_dict = {}
for idx, row in df_p.iterrows():
    coord = (round(row['longitude'], 6), round(row['latitude'], 6))
    power_nodes_dict[coord] = {
        'id': f"substation_{idx+1}",
        'name': row.get('name', 'N/A'),
        'operator': row.get('operator', 'KPTCL'),
        'voltage': row.get('voltage', 'unknown'),
        'substation_type': row.get('substation', 'distribution'),
        'rating': row.get('rating', 'unknown'),
        'lat': row['latitude'],
        'lon': row['longitude']
    }

print(f"Unique substation coords (rounded 6 decimals): {len(power_nodes_dict)}")

# Let's see how lines connect to these nodes or intermediate tower/junction points
all_p_coords = set()
for l in p_lines:
    coords = l['geometry']['coordinates']
    for c in coords:
        all_p_coords.add((round(c[0], 6), round(c[1], 6)))

sub_in_lines = sum(1 for c in power_nodes_dict if c in all_p_coords)
print(f"Substations appearing exactly in line coordinates: {sub_in_lines} / {len(power_nodes_dict)}")

print("\n==================================================")
print("2. WATER GRAPH RECONSTRUCTION INVESTIGATION")
print("==================================================")
df_w = pd.read_excel(os.path.join(processed_dir, "water_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    water_geo = json.load(f)

w_lines = [feat for feat in water_geo['features'] if feat['geometry']['type'] == 'LineString']
w_points = [feat for feat in water_geo['features'] if feat['geometry']['type'] == 'Point']
print(f"Water: {len(df_w)} facilities in Excel, {len(w_lines)} LineStrings, {len(w_points)} Points in GeoJSON.")

all_w_coords = set()
for l in w_lines:
    coords = l['geometry']['coordinates']
    for c in coords:
        all_w_coords.add((round(c[0], 6), round(c[1], 6)))

w_sub_in_lines = 0
for idx, row in df_w.iterrows():
    c = (round(row['longitude'], 6), round(row['latitude'], 6))
    if c in all_w_coords:
        w_sub_in_lines += 1
print(f"Water facilities appearing exactly in line coordinates: {w_sub_in_lines} / {len(df_w)}")

print("\n==================================================")
print("3. ROAD GRAPH RECONSTRUCTION INVESTIGATION")
print("==================================================")
df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

print(f"Road: {len(df_r)} nodes in Excel, {len(road_geo['features'])} features in GeoJSON.")

# Build coordinate index for road Excel nodes
road_node_coords = {}
for idx, row in df_r.iterrows():
    c = (round(row['longitude'], 6), round(row['latitude'], 6))
    road_node_coords[c] = row['node_id']

print(f"Unique road node coords: {len(road_node_coords)}")
