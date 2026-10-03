import os
import json
import pandas as pd
import numpy as np

processed_dir = r"d:\new urban el\processed"

# 1. POWER
df_p = pd.read_excel(os.path.join(processed_dir, "power_infrastructure.xlsx"))
print("--- POWER EXCEL DETAILS ---")
print(df_p.info())
print(df_p[['name', 'operator', 'power', 'rating', 'substation', 'voltage', 'latitude', 'longitude']].head(10))
print("Power voltage value counts:\n", df_p['voltage'].value_counts())
print("Power 'power' col value counts:\n", df_p['power'].value_counts())
print("Power 'substation' col value counts:\n", df_p['substation'].value_counts())

with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    power_geo = json.load(f)

print(f"\nPower GeoJSON total features: {len(power_geo['features'])}")
p_types = {}
p_prop_keys = set()
for feat in power_geo['features']:
    gt = feat['geometry']['type']
    p_types[gt] = p_types.get(gt, 0) + 1
    p_prop_keys.update(feat.get('properties', {}).keys())
print("Power GeoJSON geom types:", p_types)
print("Power GeoJSON prop keys:", p_prop_keys)
print("Power GeoJSON sample features:")
for feat in power_geo['features'][:5]:
    print(feat['properties'], feat['geometry']['type'], len(feat['geometry']['coordinates']) if feat['geometry']['type'] == 'LineString' else feat['geometry']['coordinates'])

# 2. WATER
df_w = pd.read_excel(os.path.join(processed_dir, "water_infrastructure.xlsx"))
print("\n--- WATER EXCEL DETAILS ---")
print(df_w.info())
print(df_w[['type', 'node_ref', 'name', 'operator', 'man_made', 'latitude', 'longitude']].head(10))

with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    water_geo = json.load(f)

print(f"\nWater GeoJSON total features: {len(water_geo['features'])}")
w_types = {}
w_prop_keys = set()
for feat in water_geo['features']:
    gt = feat['geometry']['type']
    w_types[gt] = w_types.get(gt, 0) + 1
    w_prop_keys.update(feat.get('properties', {}).keys())
print("Water GeoJSON geom types:", w_types)
print("Water GeoJSON prop keys:", w_prop_keys)
print("Water GeoJSON sample features:")
for feat in water_geo['features'][:5]:
    print(feat['properties'], feat['geometry']['type'], len(feat['geometry']['coordinates']) if feat['geometry']['type'] == 'LineString' else feat['geometry']['coordinates'])

# 3. ROAD
df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
print("\n--- ROAD EXCEL DETAILS ---")
print(df_r.info())
print(df_r[['node_id', 'latitude', 'longitude', 'road_node_type', 'highway_type', 'importance', 'lanes', 'maxspeed']].head(10))

# Sample 5 features from road GeoJSON
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

print(f"\nRoad GeoJSON total features: {len(road_geo['features'])}")
print("Road GeoJSON sample 5 features:")
for feat in road_geo['features'][:5]:
    coords = feat['geometry']['coordinates']
    print(feat['properties'], feat['geometry']['type'], f"pts={len(coords)}", f"start={coords[0]}", f"end={coords[-1]}")
