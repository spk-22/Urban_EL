"""
Spatial Map Generator for Phase 1 Validation
===========================================
Generates:
  1. 3-Panel Static Spatial Overview Map (outputs/figures/bengaluru_infrastructure_layers.png)
  2. Interactive Folium Maps for Road, Power, and Water layers.
"""

import os
import sys
import json
import folium
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from models.graph_builder import (
    build_power_graph,
    build_water_graph,
    build_corridor_road_graph
)

os.makedirs("outputs/figures", exist_ok=True)

def generate_static_spatial_overview(G_road, G_power, G_water):
    print("Generating 3-Panel Static Spatial Overview...")
    fig, axes = plt.subplots(1, 3, figsize=(20, 6.5))
    
    # 1. Road (Silk Board corridor)
    ax1 = axes[0]
    r_coords = {n: (d["longitude"], d["latitude"]) for n, d in G_road.nodes(data=True)}
    for u, v in G_road.edges():
        p1, p2 = r_coords[u], r_coords[v]
        ax1.plot([p1[0], p2[0]], [p1[1], p2[1]], color='#888888', linewidth=0.7, alpha=0.6)
    r_lons = [c[0] for c in r_coords.values()]
    r_lats = [c[1] for c in r_coords.values()]
    ax1.scatter(r_lons, r_lats, color='#d9534f', s=4, alpha=0.7, zorder=3)
    ax1.set_title(f"Road Transportation Network\n({G_road.number_of_nodes()} Nodes, {G_road.number_of_edges()} Edges)", fontsize=11, fontweight='bold')
    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")
    ax1.grid(True, linestyle=":", alpha=0.4)

    # 2. Power Grid
    ax2 = axes[1]
    p_coords = {n: (d["longitude"], d["latitude"]) for n, d in G_power.nodes(data=True)}
    for u, v, d in G_power.edges(data=True):
        p1, p2 = p_coords[u], p_coords[v]
        col = '#0275d8' if d.get("voltage") == "220kV" else '#5bc0de'
        ax2.plot([p1[0], p2[0]], [p1[1], p2[1]], color=col, linewidth=0.9, alpha=0.7)
    
    # Plot substations vs towers
    sub_lons = [d["longitude"] for _, d in G_power.nodes(data=True) if d.get("entity_type") == "substation"]
    sub_lats = [d["latitude"] for _, d in G_power.nodes(data=True) if d.get("entity_type") == "substation"]
    tow_lons = [d["longitude"] for _, d in G_power.nodes(data=True) if d.get("entity_type") == "tower_junction"]
    tow_lats = [d["latitude"] for _, d in G_power.nodes(data=True) if d.get("entity_type") == "tower_junction"]
    
    ax2.scatter(tow_lons, tow_lats, color='#a0a0a0', s=2, alpha=0.3, label="Towers")
    ax2.scatter(sub_lons, sub_lats, color='#d9534f', s=35, marker='s', edgecolor='black', label="Substations (44)", zorder=4)
    ax2.set_title(f"Power Transmission Network\n({G_power.number_of_nodes()} Nodes, {G_power.number_of_edges()} Edges)", fontsize=11, fontweight='bold')
    ax2.set_xlabel("Longitude")
    ax2.set_ylabel("Latitude")
    ax2.grid(True, linestyle=":", alpha=0.4)
    ax2.legend(loc="upper left", fontsize=9)

    # 3. Water Network
    ax3 = axes[2]
    # Sample 4000 edges for clean rendering
    w_coords = {n: (d["longitude"], d["latitude"]) for n, d in G_water.nodes(data=True)}
    w_sample_edges = list(G_water.edges())[::4]
    for u, v in w_sample_edges:
        p1, p2 = w_coords[u], w_coords[v]
        ax3.plot([p1[0], p2[0]], [p1[1], p2[1]], color='#5bc0de', linewidth=0.5, alpha=0.4)
    
    fac_lons = [d["longitude"] for _, d in G_water.nodes(data=True) if d.get("entity_type") == "facility"]
    fac_lats = [d["latitude"] for _, d in G_water.nodes(data=True) if d.get("entity_type") == "facility"]
    ax3.scatter(fac_lons, fac_lats, color='#0275d8', s=35, marker='^', edgecolor='black', label="Facilities (53)", zorder=4)
    ax3.set_title(f"Water Supply & Pipeline Network\n({G_water.number_of_nodes()} Nodes, {G_water.number_of_edges()} Edges)", fontsize=11, fontweight='bold')
    ax3.set_xlabel("Longitude")
    ax3.set_ylabel("Latitude")
    ax3.grid(True, linestyle=":", alpha=0.4)
    ax3.legend(loc="upper left", fontsize=9)

    plt.tight_layout()
    out_path = "outputs/figures/bengaluru_infrastructure_layers.png"
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"Saved 3-panel static spatial overview to: {out_path}")


def generate_interactive_power_map(G_power):
    print("Generating Interactive Folium Map for Power...")
    m = folium.Map(location=[12.9716, 77.5946], zoom_start=11, tiles="OpenStreetMap")
    
    # Transmission lines
    for u, v, d in G_power.edges(data=True):
        lat1, lon1 = G_power.nodes[u]["latitude"], G_power.nodes[u]["longitude"]
        lat2, lon2 = G_power.nodes[v]["latitude"], G_power.nodes[v]["longitude"]
        folium.PolyLine(
            locations=[(lat1, lon1), (lat2, lon2)],
            color="#0275d8",
            weight=1.5,
            opacity=0.7,
            tooltip=f"Line: {d.get('edge_id', 'N/A')} ({d.get('voltage', '220kV')}, {d.get('length', 0):.0f}m)"
        ).add_to(m)

    # Substations
    for n, d in G_power.nodes(data=True):
        if d.get("entity_type") == "substation":
            folium.CircleMarker(
                location=(d["latitude"], d["longitude"]),
                radius=6,
                color="#d9534f",
                fill=True,
                fill_color="#d9534f",
                fill_opacity=0.9,
                tooltip=f"Substation: {d.get('name', 'N/A')} | Rating: {d.get('rating', 'N/A')} | Cap: {d.get('capacity', 0)} MVA"
            ).add_to(m)

    map_path = "outputs/figures/phase1_power_network_map.html"
    m.save(map_path)
    print(f"Saved interactive power map to: {map_path}")


def generate_interactive_road_cascade_map(G_road):
    print("Generating Interactive Folium Map for Road Cascade...")
    with open("outputs/logs/road_validation_results.json", "r") as f:
        road_data = json.load(f)
    
    failed_keys = set(tuple(k) for k in road_data["R2_Dual_Arterial_Bottleneck"]["failed_edge_keys"])
    stressed_keys = set(tuple(k) for k in road_data["R2_Dual_Arterial_Bottleneck"]["stressed_edge_keys"])
    init_failed = set(tuple(k) for k in road_data["R2_Dual_Arterial_Bottleneck"]["initial_failures"])

    def canon(u, v):
        return (u, v) if str(u) <= str(v) else (v, u)

    m = folium.Map(location=[12.9172, 77.6228], zoom_start=14, tiles="OpenStreetMap")

    for u, v, d in G_road.edges(data=True):
        lat1, lon1 = G_road.nodes[u]["latitude"], G_road.nodes[u]["longitude"]
        lat2, lon2 = G_road.nodes[v]["latitude"], G_road.nodes[v]["longitude"]
        k = canon(u, v)
        if k in init_failed:
            color = "#000000"
            weight = 4
            status = "Initial Failed Bottleneck"
        elif k in failed_keys:
            color = "#d9534f"
            weight = 3
            status = "Cascaded Overload Failure"
        elif k in stressed_keys:
            color = "#f0ad4e"
            weight = 2.5
            status = "Stressed Link (V/C >= 1.0)"
        else:
            color = "#5cb85c"
            weight = 1
            status = "Normal Flow"

        folium.PolyLine(
            locations=[(lat1, lon1), (lat2, lon2)],
            color=color,
            weight=weight,
            opacity=0.8,
            tooltip=f"{d.get('road_name', 'Link')} | Status: {status} | Length: {d.get('length', 0):.1f}m"
        ).add_to(m)

    map_path = "outputs/figures/phase1_road_cascade_spatial_map.html"
    m.save(map_path)
    print(f"Saved interactive road cascade map to: {map_path}")


if __name__ == "__main__":
    silk_geojson = r"d:\urban el\data\processed\silk_board.geojson"
    G_road = build_corridor_road_graph(silk_geojson)
    G_power = build_power_graph()
    G_water = build_water_graph()
    
    generate_static_spatial_overview(G_road, G_power, G_water)
    generate_interactive_power_map(G_power)
    generate_interactive_road_cascade_map(G_road)
    print("Spatial map generation complete!")
