import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fname in ['power.py', 'road.py']:
    path = os.path.join(r'D:\urban el\backend\graph', fname)
    if os.path.exists(path):
        print('='*50, fname)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if 'for feature in geojson_data' in line or 'ADD GEOJSON EDGES' in line or 'ADD XLSX EDGES' in line:
                    for j in range(i, min(i+70, len(lines))):
                        print(f"{j+1}: {lines[j]}", end='')
