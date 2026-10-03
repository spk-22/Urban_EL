import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fname in ['power.py', 'water.py', 'road.py', 'cascade.py', 'create_multi_layer_graph.py']:
    path = os.path.join(r'D:\urban el\backend\graph', fname)
    if not os.path.exists(path):
        continue
    print('='*50, fname)
    with open(path, 'r', encoding='utf-8') as f:
        print(f.read())
