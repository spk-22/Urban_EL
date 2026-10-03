import sys
import json
import os
import math
import networkx as nx

sys.stdout.reconfigure(encoding='utf-8')
processed_dir = r"d:\new urban el\processed"

# Load sample or test degree distribution
# Let's count degree distribution of the 500,170 node graph
# We can do this efficiently without building full attributes
print("Analyzing node degrees in road network...")
degree_count = {}
with open(os.path.join(processed_dir, "road_network_geojson.json"), 'r', encoding='utf-8') as f:
    road_geo = json.load(f)

node_degree = {}
for feat in road_geo['features']:
    coords = feat.get('geometry', {}).get('coordinates', [])
    if len(coords) < 2:
        continue
    for i in range(len(coords) - 1):
        p1 = (round(coords[i][0], 6), round(coords[i][1], 6))
        p2 = (round(coords[i+1][0], 6), round(coords[i+1][1], 6))
        if p1 != p2:
            node_degree[p1] = node_degree.get(p1, 0) + 1
            node_degree[p2] = node_degree.get(p2, 0) + 1

from collections import Counter
c = Counter(node_degree.values())
print(f"Total unique road vertices: {len(node_degree)}")
print("Degree distribution:")
for deg in sorted(c.keys())[:10]:
    print(f"  Degree {deg}: {c[deg]} nodes ({c[deg]/len(node_degree)*100:.1f}%)")
print(f"  Degree >= 3 (true intersections): {sum(v for k, v in c.items() if k >= 3)} nodes ({sum(v for k, v in c.items() if k >= 3)/len(node_degree)*100:.1f}%)")
