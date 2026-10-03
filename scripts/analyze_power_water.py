import os
import json
from collections import Counter

processed_dir = r"d:\new urban el\processed"

print("="*60)
print("POWER GEOJSON DETAILS")
print("="*60)
with open(os.path.join(processed_dir, "power_network_geojson.json"), 'r', encoding='utf-8') as f:
    p_geo = json.load(f)

p_type_c = Counter()
p_volt_c = Counter()
p_oper_c = Counter()
p_geom_c = Counter()

for feat in p_geo['features']:
    props = feat.get('properties', {})
    geom = feat.get('geometry', {})
    p_geom_c[geom.get('type')] += 1
    p_type_c[props.get('type', 'missing')] += 1
    p_volt_c[props.get('voltage', 'missing')] += 1
    p_oper_c[props.get('operator', 'missing')] += 1

print("Geometries:", p_geom_c)
print("Types:", p_type_c)
print("Voltages:", p_volt_c)
print("Operators:", p_oper_c)

print("\n" + "="*60)
print("WATER GEOJSON DETAILS")
print("="*60)
with open(os.path.join(processed_dir, "water_network_geojson.json"), 'r', encoding='utf-8') as f:
    w_geo = json.load(f)

w_type_c = Counter()
w_name_c = Counter()
w_geom_c = Counter()

for feat in w_geo['features']:
    props = feat.get('properties', {})
    geom = feat.get('geometry', {})
    w_geom_c[geom.get('type')] += 1
    w_type_c[props.get('type', 'missing')] += 1
    if props.get('name'):
        w_name_c[props.get('name')] += 1

print("Geometries:", w_geom_c)
print("Types:", w_type_c)
print("Top 15 names:", w_name_c.most_common(15))
print("Total with distinct names:", len(w_name_c))
