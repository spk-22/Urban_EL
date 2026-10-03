import os
import json
import pandas as pd

processed_dir = r"d:\new urban el\processed"

print("="*60)
print("INSPECTING EXCEL FILES")
print("="*60)

for f in ["power_infrastructure.xlsx", "road_infrastructure.xlsx", "water_infrastructure.xlsx"]:
    path = os.path.join(processed_dir, f)
    if not os.path.exists(path):
        print(f"File {f} not found!")
        continue
    
    excel_file = pd.ExcelFile(path)
    print(f"\n>>> File: {f}")
    print(f"Sheet names: {excel_file.sheet_names}")
    for sheet in excel_file.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        print(f"  --- Sheet: {sheet} ---")
        print(f"  Shape: {df.shape}")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Data types:\n{df.dtypes}")
        print(f"  Missing values:\n{df.isnull().sum()}")
        print("  Sample 3 rows:")
        print(df.head(3))
        # check unique ID column if any
        for col in df.columns:
            if "id" in col.lower() or "name" in col.lower() or "type" in col.lower():
                print(f"  Column '{col}' unique count: {df[col].nunique()} / {len(df)}")
                if df[col].nunique() < 20:
                    print(f"    Values: {df[col].value_counts().to_dict()}")

print("\n" + "="*60)
print("INSPECTING GEOJSON FILES (Summary)")
print("="*60)

for f in ["power_network_geojson.json", "road_network_geojson.json", "water_network_geojson.json"]:
    path = os.path.join(processed_dir, f)
    if not os.path.exists(path):
        print(f"File {f} not found!")
        continue
    print(f"\n>>> File: {f} (size: {os.path.getsize(path)/1024/1024:.2f} MB)")
    # For large files, let's read streaming or inspect top features
    with open(path, 'r', encoding='utf-8') as jf:
        # read partial or load
        # road is ~98MB, can load in memory with python
        data = json.load(jf)
        print(f"  Keys: {list(data.keys())}")
        if "type" in data:
            print(f"  Type: {data['type']}")
        if "features" in data:
            features = data["features"]
            print(f"  Total features: {len(features)}")
            if len(features) > 0:
                feat0 = features[0]
                print(f"  Sample feature 0:")
                print(f"    Geometry type: {feat0.get('geometry', {}).get('type')}")
                print(f"    Properties keys: {list(feat0.get('properties', {}).keys())}")
                print(f"    Properties sample: {feat0.get('properties')}")
                # Analyze property key distribution across all features
                prop_keys = set()
                geom_types = {}
                for feat in features[:1000]:
                    g_type = feat.get('geometry', {}).get('type')
                    geom_types[g_type] = geom_types.get(g_type, 0) + 1
                    for k in feat.get('properties', {}).keys():
                        prop_keys.add(k)
                print(f"  Geometry types (first 1000): {geom_types}")
                print(f"  All property keys (first 1000): {prop_keys}")
