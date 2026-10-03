import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("colorblind")

INPUT_DIR = r"D:\new urban el\phase2_results\tables"
OUTPUT_DIR = r"D:\new urban el\phase2_results\figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Independent vs Coupled Comparison
comp_df = pd.read_csv(os.path.join(INPUT_DIR, "independent_vs_coupled_comparison.csv"))

plt.figure(figsize=(10, 6))
# Filter scenarios where there's a difference or just plot all
x = range(len(comp_df))
width = 0.35

fig, ax = plt.subplots(figsize=(12, 6))
ax.bar([i - width/2 for i in x], comp_df['total_failures_ind'], width, label='Independent')
ax.bar([i + width/2 for i in x], comp_df['total_failures_coup'], width, label='Coupled')

ax.set_ylabel('Total Failed Components')
ax.set_title('Total Failures: Independent vs Coupled Models')
ax.set_xticks(x)
ax.set_xticklabels(comp_df['scenario'], rotation=45, ha='right')
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "independent_vs_coupled_failures.png"), dpi=300)
plt.close()

# 2. Sensitivity Analysis - alpha_wr impact on road delays
sens_df = pd.read_csv(os.path.join(INPUT_DIR, "sensitivity_analysis_results.csv"))

s4_df = sens_df[sens_df['scenario'] == 'S4_Water_D3_SilkBoard'].copy()
if not s4_df.empty:
    plt.figure(figsize=(8, 5))
    plt.plot(s4_df['parameter_value'], s4_df['road_failed_edges'], marker='o', linestyle='-', color='red')
    plt.xlabel('alpha_wr (Water-to-Road Impact Factor)')
    plt.ylabel('Road Failed Edges')
    plt.title('Sensitivity of Road Network Failures to D3 Impact Strength')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "sensitivity_alpha_wr_road_failures.png"), dpi=300)
    plt.close()

# 3. Sensitivity Analysis - s_pw strength on water failures
s1_df = sens_df[sens_df['scenario'] == 'S1_Power_D1_Banaswadi'].copy()
if not s1_df.empty:
    plt.figure(figsize=(8, 5))
    plt.plot(s1_df['parameter_value'], s1_df['water_unmet_demand_mld'], marker='s', linestyle='-', color='blue')
    plt.xlabel('s_pw (Power-to-Water Dependency Strength)')
    plt.ylabel('Water Unmet Demand (MLD)')
    plt.title('Sensitivity of Water System to D1 Dependency Strength')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "sensitivity_s_pw_water_unmet.png"), dpi=300)
    plt.close()

print(f"Figures saved to {OUTPUT_DIR}")
