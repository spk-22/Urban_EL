import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fname in ['power.py', 'water.py', 'road.py']:
    path = os.path.join(r'D:\urban el\backend\graph', fname)
    if os.path.exists(path):
        print('='*50, fname)
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # print lines containing def build_graph
            for i, line in enumerate(lines):
                if 'def build_graph' in line or 'def _build' in line or 'def load' in line:
                    print(f"Line {i+1}: {line.strip()}")
                    for j in range(i, min(i+40, len(lines))):
                        print(f"  {lines[j]}", end='')
