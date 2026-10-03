import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fname in ['power.py', 'road.py', 'water.py']:
    path = os.path.join(r'D:\urban el\backend\graph', fname)
    if os.path.exists(path):
        print('='*50, fname)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if 'def build_graph' in line:
                    for j in range(i, min(i+90, len(lines))):
                        print(f"{j+1}: {lines[j]}", end='')
