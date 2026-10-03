# Cascading Failure Research Project: Multi-Layer Urban Infrastructure

## Overview

This project investigates cascading failures across the interconnected critical infrastructures of Bengaluru, India:
- **Road Transportation Network** ($G_{\text{road}}$)
- **Power Transmission Grid** ($G_{\text{power}}$)
- **Municipal Water Supply Network** ($G_{\text{water}}$)

The project is structured in two strictly separated phases. **Phase 1 is complete and currently under review.**

---

## What We Discovered in Phase 1

### 1. Forensic Audit of Previous Implementation
An audit of the previous codebase revealed fatal modeling flaws:
- **Row-Chaining Error**: In the previous code, edges were added by connecting consecutive rows in the Excel spreadsheet (`row[i-1] -> row[i]`). This created artificial 1D "snake graphs" ($V = E + 1$) that ignored real spatial road networks and water distribution loops.
- **Arbitrary Constants**: Road cascading used hard-coded values (`len(new_failures) * 150 / 30`) without physical meaning.
- **Disconnected Substations**: Raw OSM transmission lines ended at towers rather than substation centroids, isolating 37 of 44 substations.

### 2. Rigorous Grounded Reconstruction
We rebuilt all three infrastructure graphs from the ground up:
- **Road ($G_{\text{road}}$)**: Built from 150,082 primary highway LineStrings and 88,635 Excel OSM nodes. Full network: 500,170 nodes, 575,733 edges (99.1% in giant component). Focal arterial networks (e.g. Silk Board: 3,752 nodes, 4,299 edges) were established for detailed routing analysis.
- **Power ($G_{\text{power}}$)**: Built from 44 KPTCL substations and 346 transmission lines. Snapping switchyard/tower gaps ($d \le 50\text{ m}$) restored physical grid continuity (4,063 nodes, 4,099 edges).
- **Water ($G_{\text{water}}$)**: Built from 53 BWSSB facilities (treatment plants, reservoirs, tanks) snapped to 3,168 pipeline segments (34,398 nodes, 34,550 edges).

### 3. Layer-Specific Cascade Engines
- **Road Engine** (`models/road_cascade.py`):
  - Travel time calculated via **Bureau of Public Roads (BPR)** function: $T = T_0 [1 + 0.15 (V/C)^4]$.
  - Alternate routing via **Yen's K-Shortest Paths** ($k=3$).
  - Traffic redistribution via **Multinomial Logit (MNL)** discrete choice model: $P(k) \propto \exp(-\theta T_k)$.
  - Failure threshold: $V / C \ge 1.25$ (severe breakdown).
- **Power Engine** (`models/power_cascade.py`):
  - Load redistribution based on **available spare capacity headroom**: $\text{SpareCap}_j = \max(0, C_j - L_j)$.
  - Rerouting weighted by headroom and spatial distance.
  - Failure threshold: $L / C \ge 1.10$ (thermal overload trip).
- **Water Engine** (`models/water_cascade.py`):
  - Supply-demand flow balance network.
  - Pipeline rupture check: $Q / C \ge 1.30$.
  - Service adequacy tracking: $\alpha = \text{ReceivedFlow} / \text{Demand} < 0.50$ triggers service deprivation.

### 4. Phase 1 Validation Findings
- **Road**: A dual arterial bottleneck failure at Silk Board cascaded across 10 rounds, failing 346 links ($8.05\%$ disruption) and inflating network delay by $1.022\times$. Single arterial failures were absorbed without cascade ($0.02\%$).
- **Power**: High-capacity substations (400-450 MVA) absorb localized shocks, but severance of a critical 220kV transmission line triggered successive line trips across adjacent corridors (118 line failures).
- **Water**: Losing a major BWSSB treatment facility deprives downstream municipal zones, causing up to 33,936 deprived junctions ($98.8\%$ service deprivation) and 16,968 MLD unmet demand.

---

## Directory Structure

```
d:\new urban el\
├── data/
│   ├── processed/             # Excel infrastructure node sheets & GeoJSON edge collections
│   └── raw/                   # Raw OpenStreetMap XML exports
├── models/
│   ├── graph_builder.py       # Validated multi-layer graph reconstruction
│   ├── road_cascade.py        # BPR + Yen's K-Shortest Path + Logit road cascade
│   ├── power_cascade.py       # Spare capacity headroom power grid cascade
│   └── water_cascade.py       # Supply-demand flow network water cascade
├── simulations/
│   ├── run_all_phase1_validation.py  # Full validation suite across 9 scenarios
│   └── generate_spatial_maps.py     # Static overview and interactive Folium maps
├── outputs/
│   ├── figures/               # Publication charts & interactive HTML maps
│   └── logs/                  # Machine-readable JSON cascade execution histories
├── PHASE1_REPORT.md           # Comprehensive scientific report for Phase 1
└── README.md                  # This document
```

---

## Plan for Phase 2: Cross-Layer Coupled Cascading Failures

> [!IMPORTANT]
> **STOP CONDITION ACTIVE**: Phase 2 will NOT be executed until Phase 1 results are reviewed and explicitly approved by the user.

Once approved, Phase 2 will execute the following workflow:

```
[Approved Phase 1 Baseline Networks]
           |
           v
[Step 1: Cross-Layer Dependency Formulation]
  - D1: Power Substation -> Water Pumping Facility (Electric drive loss)
  - D2: Power Substation -> Road Traffic Signals (Capacity degradation)
  - D3: Water Pipeline Burst -> Road Segment Blockage (Localized inundation)
           |
           v
[Step 2: Dual-Loop Coupled Cascade Controller]
  - Inner Loop: Layer cascades independently until reaching equilibrium.
  - Outer Loop: Cross-layer impacts applied; if another layer changes, run inner loop.
  - Termination: Complete cycle produces no new failures and no state changes.
           |
           v
[Step 3: Baseline vs. Coupled Scientific Comparison]
  - Compare Independent Disruption vs. Coupled Disruption.
  - Test whether cross-layer coupling amplifies cascade depth or total failures.
           |
           v
[Step 4: Parameter Sensitivity Analysis]
  - Sweep coupling strength s in [0.2, 1.0].
  - Vary failure thresholds and initial trigger points.
           |
           v
[Step 5: Final Publication-Oriented Research Paper]
```

---

## How to Reproduce Phase 1

1. **Run Full Phase 1 Validation Suite**:
   ```bash
   python simulations/run_all_phase1_validation.py
   ```
2. **Generate Interactive Maps**:
   ```bash
   python simulations/generate_spatial_maps.py
   ```
3. **Inspect Results**:
   - `outputs/figures/phase1_single_layer_cascade_progression.png`
   - `outputs/figures/phase1_scenario_disruption_comparison.png`
   - `outputs/figures/bengaluru_infrastructure_layers.png`
   - `outputs/figures/phase1_road_cascade_spatial_map.html`
   - `outputs/figures/phase1_power_network_map.html`
   - `PHASE1_REPORT.md`
