import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fname in ['power.py', 'water.py']:
    path = os.path.join(r'D:\urban el\backend\graph', fname)
    if os.path.exists(path):
        print('='*50, fname)
        with open(path, 'r', encoding='utf-8') as f:
            print(f.read())
