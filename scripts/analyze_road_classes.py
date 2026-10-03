import os
import json
from collections import Counter

processed_dir = r"d:\new urban el\processed"

# Road classes
print("Analyzing road_network_geojson.json classes...")
class_counter = Counter()
type_counter = Counter()
num_features = 0

with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

for feat in road_geo['features']:
    props = feat.get('properties', {})
    class_counter[props.get('class', 'missing')] += 1
    type_counter[props.get('type', 'missing')] += 1
    num_features += 1

print(f"Total road features: {num_features}")
print("Road classes distribution:")
for k, v in class_counter.most_common():
    print(f"  {k}: {v}")

print("\nRoad types distribution:")
for k, v in type_counter.most_common():
    print(f"  {k}: {v}")
