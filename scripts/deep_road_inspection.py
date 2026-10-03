import sys
import json
import os
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
processed_dir = r"d:\new urban el\processed"

df_r = pd.read_excel(os.path.join(processed_dir, "road_infrastructure.xlsx"))
print("=== ROAD EXCEL NODES ===")
print("Total rows:", len(df_r))
print("Road node types:\n", df_r['road_node_type'].value_counts())
print("Highway types:\n", df_r['highway_type'].value_counts())
print("Importance:\n", df_r['importance'].value_counts())
print("Traffic signals:\n", df_r['traffic_signal'].value_counts(dropna=False))

# Spatial bounding box of road excel nodes
lat_min, lat_max = df_r['latitude'].min(), df_r['latitude'].max()
lon_min, lon_max = df_r['longitude'].min(), df_r['longitude'].max()
print(f"Excel BBox: Lat [{lat_min:.4f}, {lat_max:.4f}], Lon [{lon_min:.4f}, {lon_max:.4f}]")

# Let's inspect road GeoJSON
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

print(f"GeoJSON features count: {len(road_geo['features'])}")
# Check bounding box of GeoJSON
lons = []
lats = []
for feat in road_geo['features'][:5000]:
    for pt in feat['geometry']['coordinates']:
        lons.append(pt[0])
        lats.append(pt[1])
print(f"GeoJSON BBox (sample): Lat [{min(lats):.4f}, {max(lats):.4f}], Lon [{min(lons):.4f}, {max(lons):.4f}]")

# How many distinct way IDs / names in GeoJSON?
names = [feat['properties'].get('name') for feat in road_geo['features']]
print("Total road features:", len(names))
print("Non-empty names count:", sum(1 for n in names if n))
unique_names = set(names)
print("Unique road names:", len(unique_names))
print("Sample names:", list(unique_names)[:10])
