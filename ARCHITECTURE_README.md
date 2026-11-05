# ARCHITECTURE README
# Multi-Layer Cascading Failure Analysis — Bengaluru Power, Water & Road Networks

## Project Overview

This project models, simulates, and quantifies cascading failure propagation across **three interdependent urban infrastructure networks** in Bengaluru, India:
- **Power**: KPTCL 220/66kV transmission substations and lines
- **Water**: BWSSB water treatment works, reservoirs, tanks, and distribution pipelines
- **Road**: Silk Board arterial corridor (focus zone)

The core research question is: *Does activating all three inter-layer dependency channels simultaneously (M7) produce more system-wide failures than any pairwise coupled model (M1, M2, M3) can alone?*

The project is organized in two phases:
- **Phase 1**: Independent single-layer validation of each network's cascade simulator
- **Phase 2**: Coupled multi-layer cascade analysis using a dependency hierarchy experiment (M0–M7) with 8 scenarios (S1–S8)

---

## Repository Structure

```
d:\new urban el\
├── models\                            # Core simulation engines
│   ├── graph_builder.py               # Network construction from Excel + GeoJSON
│   ├── power_cascade.py               # Power load redistribution cascade engine
│   ├── water_cascade.py               # Water supply-demand flow cascade engine
│   ├── road_cascade.py                # BPR + Yen k-path + MNL traffic cascade engine
│   ├── dependency_mapper.py           # Spatial cross-layer dependency mapping (D1–D6)
│   └── multi_layer_cascade.py         # Two-loop orchestrator (inner + outer coupling)
│
├── simulations\                       # Experiment runner scripts
│   ├── run_all_phase1_validation.py   # Phase 1 single-layer validation
│   ├── run_phase2_analysis.py         # Phase 2 S1–S7 scenarios (full batch)
│   ├── run_coupling_hierarchy.py      # M0–M7 hierarchy + S1–S8 scenarios
│   ├── plot_m7_propagation_curves.py  # M7 round-by-round timeline plotter
│   └── generate_spatial_maps.py       # Folium HTML spatial visualizations
│
├── processed\                         # Network input data files
│   ├── power_infrastructure.xlsx      # 44 KPTCL substations (lat/lon, MVA, voltage)
│   ├── power_network_geojson.json     # 355 features (346 transmission lines)
│   ├── water_infrastructure.xlsx      # 53 BWSSB facilities (Water Works, reservoirs, tanks)
│   ├── water_network_geojson.json     # 3,171 features (3,168 pipeline segments)
│   ├── road_infrastructure.xlsx       # 88,635 OSM road nodes
│   └── road_network_geojson.json      # 150,082 city-wide road links (88.97 MB)
│
├── raw\                               # Raw OSM XML sources
│   ├── power.osm
│   ├── water.osm
│   └── road.osm
│
├── phase2_results\
│   ├── tables\                        # CSV output tables from experiments
│   └── figures\                       # Matplotlib/seaborn PNG figures
│
├── scratch\                           # Temporary test scripts
│   └── test_m0_m7.py
│
├── ARCHITECTURE_README.md             # THIS FILE
├── RESEARCH_AUDIT.md                  # Independent forensic audit of all results
├── PHASE1_REPORT.md                   # Phase 1 single-layer validation findings
├── PHASE2_REPORT.md                   # Phase 2 coupled cascade analysis findings
└── literature_comparison_and_gap_analysis.txt

External dependency (not in this repo):
  d:\urban el\data\processed\silk_board.geojson    # 3,752 nodes, 4,299 road links
```

---

## Data Sources & Network Scale

| Layer | Source | Nodes | Edges | Notes |
|---|---|---:|---:|---|
| Power | OSM + KPTCL Excel | 4,063 | 4,099 | 44 substations + 4,019 tower junctions |
| Water | OSM + BWSSB Excel | 34,398 | 34,550 | 53 facilities + 34,345 pipe junctions |
| Road (full city) | OSM | 500,170 | 575,733 | Phase 1 road experiments only |
| Road (Silk Board focal) | GeoJSON | 3,752 | 4,299 | All Phase 2 multi-layer experiments |

---

## Model Architecture

### Phase 1: Single-Layer Simulators

#### `models/graph_builder.py`
Constructs NetworkX graphs from Excel + GeoJSON.

- `build_power_graph()` — Reads 44 substations from Excel; snaps OSM tower endpoints within 50 m to their nearest substation; assigns MVA capacity and a uniform 0.65 load-ratio baseline to all edges.
- `build_water_graph()` — Reads 53 BWSSB facilities; assigns supply by type (Water Works = 120 MLD, Reservoir = 60 MLD, Tank = 25 MLD); pipe junction demand = 0.5 MLD each.
- `build_corridor_road_graph(geojson_path)` — Reads Silk Board GeoJSON; assigns BPR parameters by OSM highway class; baseline V/C = 0.65; marks signalized intersections from the `highway=traffic_signals` OSM tag.
- `build_road_graph()` — Full-city 500k node graph used only in Phase 1.

---

#### `models/power_cascade.py` — `PowerCascadeSimulator`
**Mechanism**: Headroom-weighted, distance-decay load redistribution.

When a substation or line fails:
1. Displaced load is proportionally redistributed across surviving substations:
   ```
   W_j = SpareCap_j^γ / dist(i, j)^μ     (γ = 1.0, μ = 1.0)
   ```
2. If any substation exceeds `load_ratio ≥ 1.10`, it fails and triggers another round.
3. Lines redistribution follows shortest active path; disconnected load is shared among top-5 spare-capacity lines.
4. Iterates until stable or `max_iterations` reached.

**Output**: `failed_node_ids`, `failed_edge_keys`, `total_unserved_load_mva`, `stressed_nodes_count`, `total_rounds`

---

#### `models/water_cascade.py` — `WaterCascadeSimulator`
**Mechanism**: Topological supply-demand adequacy with pipe overload detection.

1. Seed initial failures (facility outage or pipe rupture).
2. Reroute displaced flow via `nx.shortest_path` on the surviving active subgraph.
3. Pipe overload check: `Q/C ≥ 1.30` → pipe ruptures, iterating.
4. Supply adequacy calculated per connected component:
   ```
   α_j = min(1.0, ΣSupply / ΣDemand)
   Deprived if α_j < 0.50
   ```
5. **D1 degraded-supply detection**: If any facility has `supply < 0.99 × capacity` the cascade runs even without hard failures (catches gradual electrical degradation from D1).

**Output**: `failed_pipe_keys`, `failed_facility_ids`, `total_unmet_demand_mld`, `deprived_junctions_count`, `stressed_pipes_count`, `total_rounds`

---

#### `models/road_cascade.py` — `RoadCascadeSimulator`
**Mechanism**: Iterative BPR volume-delay + Yen's k-shortest paths + Multinomial Logit rerouting.

1. Remove failed edges from the routing graph.
2. Redistribute displaced volume across `k = 3` shortest alternative paths:
   ```
   T(V) = T₀ × [1 + 0.15 × (V/C)⁴]            (BPR)
   P_j  = exp(-θ(T_j - T_min)) / Σexp(...)      (MNL logit, θ = 0.05)
   ```
3. Each path link receives `V_displaced × P_j` additional volume.
4. Links with `V/C ≥ 1.25` fail and trigger another round.
5. Network-level delay inflation factor:
   ```
   D = Σ(V_e × T_congested_e) / Σ(V_e × T_free_e)
   ```

**Output**: `failed_edge_keys`, `stressed_edges_count`, `delay_inflation_factor`, `total_rounds`

---

### Phase 2: Multi-Layer Coupling Architecture

#### `models/dependency_mapper.py` — Cross-Layer Dependency Mapping

Maps physically defensible spatial interdependencies using `scipy.spatial.cKDTree` queries:

| Channel | Direction | Mechanism | Spatial Threshold | Mapped Pairs |
|---|---|---|---|---|
| **D1** | Power → Water | Substation failure cuts pump electricity | 2,500 m | 31 / 53 facilities |
| **D2** | Power → Road | Signal outage reduces junction throughput | 2,500 m | 10 / 10 signalized nodes |
| **D3** | Water → Road | Pipe burst floods and blocks lanes | 25 m buffer | 419 road edges |
| **D4** | Road → Power | Congestion delays maintenance crews | delay > 1.05 | Cyclic feedback |
| **D5** | Road → Water | Congestion blocks burst pipe isolation | delay > 1.10 | Cyclic feedback |
| **D6** | Water → Road | Water scarcity drives procurement traffic | unmet > 5% | Cyclic feedback |

**Key parameter constants** (defined in `dependency_mapper.py`):

```python
D1_SPATIAL_THRESHOLD_M = 2500.0    # Medium-voltage feeder catchment
D2_SPATIAL_THRESHOLD_M = 2500.0    # Signal cabinet supply radius
D3_SPATIAL_BUFFER_M    = 25.0      # Pipe-road proximity buffer (lane width proxy)
D3_ALPHA_WR_CENTRAL    = 0.40      # Road capacity retained after pipe flooding
D2_ALPHA_PR_CENTRAL    = 0.30      # Road capacity reduction at dark signals
D4_GAMMA_RP_CENTRAL    = 0.35      # Maintenance delay choking power substation
D5_GAMMA_RW_CENTRAL    = 0.30      # Logistics delay choking water facility
D6_BETA_WR_CENTRAL     = 0.25      # Water scarcity → procurement traffic surge
D1_TRANSIENT_SURGE     = 0.35      # Water hammer backpressure on pump trip
```

---

#### `models/multi_layer_cascade.py` — `MultiLayerCascadeController`

The central orchestrator implementing the **two-loop architecture** with **closed-loop cyclic feedback**.

##### Constructor Parameters
```python
MultiLayerCascadeController(
    G_power, G_water, G_road,
    dependency_maps,             # from build_all_dependencies()
    s_pw=0.50,                   # D1 strength (Power->Water coupling weight)
    s_pr=1.0,                    # D2 signal loss multiplier
    alpha_pr=0.30,               # D2 road capacity reduction factor
    alpha_wr=0.40,               # D3 road capacity retention after flooding
    gamma_rp=0.35,               # D4 road->power maintenance choke factor
    gamma_rw=0.30,               # D5 road->water logistics choke factor
    beta_wr=0.25,                # D6 water scarcity->road surge factor
    transient_surge=0.35,        # D1 hydraulic surge on pump trip
    power_failure_threshold=1.10,
    water_failure_threshold=1.30,
    road_failure_threshold=1.25,
    max_outer_iterations=10,     # Outer coupling loop limit
    max_inner_iterations=15      # Each single-layer cascade limit
)
```

##### Two-Loop Control Flow
```
run_coupled_cascade(initial_power_failures, initial_water_failures, initial_road_failures)
│
OUTER LOOP  ── repeated up to max_outer_iterations until no new failures
│
│   ┌── INNER LOOP 1: PowerCascadeSimulator.run_cascade()
│   │   └── Headroom redistribution until power network stable
│   │
│   ├── INNER LOOP 2: WaterCascadeSimulator.run_cascade()
│   │   └── Flow rerouting + pipe burst propagation until water stable
│   │
│   ├── INNER LOOP 3: RoadCascadeSimulator.run_cascade()
│   │   └── BPR/MNL rerouting until road network stable
│   │
│   └── CROSS-LAYER DEPENDENCY APPLICATION (order matters)
│       │
│       ├── D1: Power → Water
│       │   Applies to all (substation, water_facility) pairs in D1 map
│       │   ● Computes power fulfillment fraction φ from substation load_ratio
│       │   ● Degrades facility capacity proportionally (no binary cliff)
│       │   ● If φ ≤ 0.50 AND pump was running: injects hydraulic surge
│       │     surge_flow = current_pipe_flow × (1 + 0.35)
│       │     → If surge_flow / capacity ≥ 1.30: pipe ruptures (D3 activated next)
│       │
│       ├── D2: Power → Road
│       │   Applies to all (substation, road_signal_node) pairs in D2 map
│       │   ● Computes loss_factor (1.0 if failed, 0.50 if stressed)
│       │   ● Reduces capacity of all incident road edges at that signal node
│       │   ● Uses stored original capacities to prevent re-reduction compounding
│       │
│       └── D3: Water → Road
│           Applies to all (pipe_junction, road_edge) pairs in D3 map
│           ● If pipe junction failed: reduces adjacent road edge capacity to
│             max(100, orig_cap × 0.40) — flood lane blockage
│
│   CYCLIC FEEDBACK LOOPS (applied after D1/D2/D3 each outer iteration)
│   │
│   ├── Loop A — D6: Water Scarcity → Road Traffic Surge
│   │   scarcity_ratio = unmet_demand_mld / 50.0  (capped at 1.0)
│   │   if scarcity_ratio > 0.05:
│   │     surge_factor = 1.0 + beta_wr × scarcity_ratio × 0.15
│   │     Raises current_load on all active road edges by surge_factor
│   │     → Edges pushed past V/C ≥ 1.25 fail → new road cascade
│   │
│   ├── Loop B — D4: Road Congestion → Power Substation Choke
│   │   if road_delay_factor > 1.05:
│   │     For stressed substations (lr ≥ 0.85) or Silk Board corridor hubs:
│   │       derated_cap = cap × (1 − gamma_rp × delay_excess)
│   │       if new load_ratio ≥ 1.10: substation trips → new power cascade
│   │
│   └── Loop C — D5: Road Congestion → Water Logistics Choke
│       if road_delay_factor > 1.10:
│         Derates all surviving water facility capacities:
│           derated_cap = max(orig × 0.40, orig × (1 − gamma_rw × delay_excess))
│         Re-runs water cascade with derated inputs
│
└── Returns system_summary dict with all failure counts + timeline per outer round
```

---

#### `simulations/run_coupling_hierarchy.py` — M0–M7 Experiment Suite

Runs **8 scenarios × 8 coupling models = 64 simulation runs**.

##### Coupling Hierarchy Models

| Model | Active Channels | Description |
|---|---|---|
| M0 | None | Fully independent baseline |
| M1 | D1 | Power → Water only |
| M2 | D2 | Power → Road (signals) only |
| M3 | D3 | Water → Road (flooding) only |
| M4 | D1 + D3 | Power → Water → Road chain |
| M5 | D2 + D3 | Power → Road + Water → Road |
| M6 | D1 + D2 | Power → Water + Power → Road |
| M7 | D1 + D2 + D3 + Feedback | Full three-layer coupling with D4/D5/D6 cyclic loops |

##### Scenarios

| ID | Initial Trigger | Purpose |
|---|---|---|
| S1_Power_D1_Banaswadi | SUB_25 fails | D1-targeted: near Water Tank FAC_36 |
| S2_Power_D1_Padmanabha | SUB_19 fails | D1-targeted: near Water Facility FAC_31 |
| S3_Power_Uncoupled | SUB_1 fails (220 kV hub) | Control: no D1/D2 reach |
| S4_Water_D3_SilkBoard | Silk Board pipe burst | D3-targeted: Silk Board corridor flooding |
| S5_Water_Facility_Regional | Largest Water Works fails | Regional supply loss (240 MLD) |
| S6_Road_Bottleneck | Highest V/C link closes | Single road bottleneck seed |
| S7_Compound_PowerWater | SUB_25 + pipe burst | Dual-layer compound trigger |
| **S8_Nexus_SilkBoard** | **SUB_43 + pipe + road** | **3-layer spatial nexus compound** |

**S8 design rationale**: SUB_43 (HSR Layout) sits ~2,114 m from Silk Board and maps to 6 of the 10 signalized road intersections via D2. Triggering it alongside a water pipe burst (D3) and the peak-load bottleneck link simultaneously guarantees immediate multi-channel propagation (D1 + D2 + D3) in the same outer iteration — the strongest possible compound compound test of M7 superiority over M1, M2, M3.

##### Higher-Order Gain Metric

```python
# Measured for each scenario after all 8 models complete:
G = F(M7) - max(F(M1), F(M2), F(M3))

# F(M) = power_failed_nodes + power_failed_edges
#      + water_failed_facilities + water_failed_pipes
#      + road_failed_edges

# G > 0: Full coupling reveals failures that no pairwise model could predict
# G = 0: M7 does not add explanatory power above pairwise coupling
```

---

## Running the Project

### Install Dependencies
```bash
pip install networkx pandas numpy scipy matplotlib seaborn openpyxl folium
```

### Phase 1: Single-Layer Validation
```bash
cd "d:\new urban el"
python simulations/run_all_phase1_validation.py
```

### Phase 2: Full Coupling Hierarchy (M0–M7, S1–S8)
```bash
python simulations/run_coupling_hierarchy.py
```
Outputs:
- `phase2_results/tables/coupling_hierarchy_summary.csv`
- `phase2_results/tables/coupling_hierarchy_detailed.csv`
- `phase2_results/figures/` (heatmaps, stacked bar plots, gain metrics)

### Spatial Visualizations
```bash
python simulations/generate_spatial_maps.py
```

---

## Key Parameters Reference

| Parameter | Symbol | Value | Source |
|---|---|---|---|
| Power failure threshold | θ_fail_pow | 1.10 | Load ratio |
| Power stress threshold | | 0.90 | Load ratio |
| Water pipe burst threshold | θ_fail_wat | 1.30 | Flow ratio |
| Road failure threshold | θ_fail_roa | 1.25 | V/C ratio |
| BPR alpha | α | 0.15 | Standard BPR |
| BPR beta | β | 4 | Standard BPR |
| MNL dispersion | θ | 0.05 | Calibrated |
| Baseline road load | V₀/C | 0.65 | Uniform assumed |
| Redistribution weight exponent (power) | γ | 1.0 | |
| Distance decay exponent (power) | μ | 1.0 | |
| D1 spatial threshold | | 2,500 m | MV feeder radius |
| D2 spatial threshold | | 2,500 m | MV feeder radius |
| D3 pipe-road buffer | | 25 m | Lane width proxy |
| s_pw (D1 coupling strength) | | 0.50 | Central estimate |
| alpha_wr (D3 flood retention) | | 0.40 | Central estimate |
| alpha_pr (D2 signal reduction) | | 0.30 | HCM inferred |
| gamma_rp (D4 road→power choke) | | 0.35 | Engineering estimate |
| gamma_rw (D5 road→water choke) | | 0.30 | Engineering estimate |
| beta_wr (D6 water→road surge) | | 0.25 | Engineering estimate |
| Transient surge factor (D1) | | 0.35 | Water hammer |
| Max outer iterations | | 10 | |
| Max inner iterations | | 15 | |

---

## Known Limitations & Data Artifacts

1. **Water baseline unmet demand**: 881 disconnected OSM water components → 828 have no attached facility → 33,868 junctions (98.6%) and ~16,814 MLD are "deprived" at t = 0 before any failure. Water outage metrics should be measured as **delta from baseline**, not absolute.

2. **No AC power flow**: Power model uses capacity-headroom proxy redistribution. No bus admittance matrices, voltage angles, reactive power, or SCADA dispatch logic.

3. **No EPANET hydraulics**: Water uses topological supply-demand adequacy only. No Darcy-Weisbach headloss, pressure gradients, or pipe diameter data.

4. **Uniform road baseline**: All links assigned V/C = 0.65. No observed OD demand matrices. No time-of-day variation.

5. **Feedback loop thresholds**: D4 fires at delay_factor > 1.05 and D5 at > 1.10. These boundaries are physically motivated but not empirically calibrated from real incident data.

6. **Static network topology**: No edge repair, restoration, or partial recovery modeled. The cascade runs until stable failure state only.

---

## Improvement Roadmap

| Priority | Improvement | Impact |
|---|---|---|
| HIGH | Fix water OSM fragmentation baseline | Correct t=0 unmet demand from 16,814 → ~0 MLD |
| HIGH | Normalize F(M) metric across layer scales | Prevent road-dominated component counting |
| MED | DEM elevation routing for D3 flooding | Replace flat 25 m buffer with terrain-guided flow |
| MED | 11 kV feeder mapping for D2 | Anchor signals to distribution transformers |
| MED | UPS battery decay curves for D2 | Time-dependent signal coordination loss |
| LOW | Monte Carlo road demand sampling | Replace V/C = 0.65 with stochastic OD matrix |
| LOW | Recovery/restoration modeling | Model repair sequencing post-cascade |
