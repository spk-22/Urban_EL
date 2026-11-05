# RESEARCH AUDIT: MULTILAYER CASCADE PROPAGATION ACROSS BENGALURU'S POWER, WATER, AND ROAD NETWORKS

**Audit Date**: October 2026  
**Auditor Role**: Independent Research Collaborator, Scientific Software Auditor, and Peer Reviewer  
**Workspace**: `d:\new urban el\`  
**Scope**: Read-only verification of data provenance, model implementations, cascade mechanics, mathematical metrics, and literature positioning.

---

## EXECUTIVE SUMMARY & AUDIT VERDICT

| Investigation Dimension | Audit Finding | Classification |
|---|---|---|
| **Higher-Order Gain ($G = 0$)** | Confirmed exactly $G = 0$ across all 7 scenarios in raw code, logs, and tables. | **Verified Fact** |
| **Water $\to$ Road (D3) Amplification** | A water transmission burst causes 14 D3 events affecting 8 Silk Board road links. Due to baseline load ($V/C = 0.65$) and $\alpha_{wr} = 0.40$, links hit $V/C = 1.625 \ge 1.25$ and fail, displacing 7,280 vph and cascading into 1,039 failed road links across 11 rounds. | **Verified Fact** |
| **Power $\to$ Road (D2) Activity** | D2 has **0 dependency links mapped** in the entire system (`n_dependencies = 0`). It never activates in any simulation. | **Confirmed Flaw / Inactive** |
| **Power $\to$ Water (D1) Cascading** | D1 derates water facility capacity ($C \to C \cdot (1 - s_{pw})$), but `WaterCascadeSimulator` only propagates pipe ruptures. Derating a facility never ruptures pipes, so D1 cannot trigger D3. The chain $P \to W \to R$ is mathematically dead. | **Confirmed Architectural Limit** |
| **Water Network Baseline Demand** | 828 out of 881 connected components in OSM water data have no water facility attached. At baseline ($t=0$), before any failure, **33,868 junctions (98.6%)** and **16,814.0 MLD** are already recorded as "unmet demand." | **Confirmed Data Artifact** |
| **Component Accounting Metric** | $F(M)$ sums heterogeneous units (substation nodes, transmission lines, water facilities, water pipes, and road links) into a single integer without normalization. | **Methodological Limitation** |
| **Literature Positioning** | The finding of dependency dominance ($G=0$) is a valid and publishable empirical result, refuting naive claims that adding layers always causes exponential super-additive collapse. | **Defensible Contribution** |

---

## 1. PHASE A: PROJECT DISCOVERY & PROVENANCE CHAINS

### 1.1 Complete File Inventory & Roles

```
d:\new urban el\
├── models/
│   ├── graph_builder.py          # Network construction from Excel & GeoJSON
│   ├── power_cascade.py          # Capacity-headroom power load redistribution simulator
│   ├── water_cascade.py          # Topological supply-demand flow & pipe burst simulator
│   ├── road_cascade.py           # Yen's K-Shortest Path + MNL + BPR traffic cascade simulator
│   ├── dependency_mapper.py      # Spatial buffer mapping for D1, D2, and D3
│   └── multi_layer_cascade.py    # Two-loop (inner/outer) orchestrator controller
├── simulations/
│   ├── run_all_phase1_validation.py   # Single-layer validation scripts (Phase 1)
│   ├── run_phase2_analysis.py         # Coupled scenarios S1-S7 and sensitivity sweeps
│   ├── run_coupling_hierarchy.py      # M0-M7 coupling hierarchy experiment suite
│   ├── plot_m7_propagation_curves.py  # Granular M7 timeline simulation & plotting
│   └── generate_spatial_maps.py       # HTML/Folium spatial visualization generator
├── processed/
│   ├── power_infrastructure.xlsx      # 44 KPTCL substations (lat, lon, rating, voltage)
│   ├── power_network_geojson.json     # 355 features (346 transmission lines)
│   ├── water_infrastructure.xlsx      # 53 BWSSB facilities (Water Works, reservoirs, tanks)
│   ├── water_network_geojson.json     # 3,171 features (3,168 pipeline segments)
│   ├── road_infrastructure.xlsx       # 88,635 OSM road nodes
│   └── road_network_geojson.json      # 150,082 city-wide road lines (88.97 MB)
├── phase2_results/
│   ├── tables/
│   │   ├── coupling_hierarchy_ablation.csv    # Granular 56-row M0-M7 metrics
│   │   ├── coupling_hierarchy_summary.csv     # Executive summary matrix
│   │   ├── coupling_hierarchy_matrix_failures.csv # Pivot table of total failures
│   │   ├── coupling_hierarchy_matrix_road.csv     # Pivot table of road failures
│   │   ├── dependency_summary.json            # D1=3, D2=0, D3=419 summary
│   │   ├── dependency_evidence_table.csv      # 422 mapped dependency pair records
│   │   ├── independent_vs_coupled_comparison.csv # Baseline comparison
│   │   ├── sensitivity_analysis_results.csv   # Sweeps for s_pw, alpha_wr
│   │   └── m7_cascade_propagation_timeline.csv # Step-by-step t=0 to t=16 timeline
│   └── figures/
│       ├── coupling_hierarchy_failures_bar.png
│       ├── coupling_hierarchy_ablation_s4_s7.png
│       ├── coupling_amplification_heatmap.png
│       ├── m7_cascade_propagation_curves.png
│       └── sensitivity_alpha_wr_road_failures.png
├── raw/
│   ├── power.osm                      # Raw OSM XML for power infrastructure
│   ├── water.osm                      # Raw OSM XML for water infrastructure
│   └── road.osm                       # Raw OSM XML for road infrastructure
└── external data dependency:
    └── d:\urban el\data\processed\silk_board.geojson # 3,752 nodes, 4,299 links (Silk Board)
```

### 1.2 End-to-End Provenance Chains

#### Chain 1: Water $\to$ Road Cascade (1,039 Failed Edges)
1. **Input Data**: `processed/water_network_geojson.json` (pipe LineStrings) and `d:\urban el\data\processed\silk_board.geojson` (road LineStrings).
2. **Network Build**: `models/graph_builder.py` (`build_water_graph`, line 187; `build_corridor_road_graph`, line 470).
3. **Dependency Mapping**: `models/dependency_mapper.py` (`map_D3_water_to_road`, line 198) uses `cKDTree` with buffer $d \le 25\text{ m}$ between pipe junctions $\ge 10\text{ MLD}$ and road edge midpoints. Mapped 419 road links.
4. **Scenario Trigger**: `simulations/run_coupling_hierarchy.py` (line 117) seeds failure on pipe `(WJ_10506, WJ_10509)` near Silk Board junction.
5. **Cross-Layer Coupling**: `models/multi_layer_cascade.py` (lines 333-350) detects failed pipe junctions and cuts capacity of 8 unique incident road edges by $\alpha_{wr} = 0.40$ (e.g. 1400 vph $\to$ 560 vph).
6. **Inner Cascade Propagation**: `models/road_cascade.py` (`RoadCascadeSimulator.run_cascade`, lines 82-192):
   - Initial check: Baseline load $910\text{ vph} / 560\text{ vph} = 1.625 \ge 1.25$ (failure threshold). All 8 edges fail in Round 0.
   - Rounds 1–11: Displaced traffic (7,280 vph) reroutes via Yen's $k=3$ paths + MNL choice. Surrounding edges (already at $V/C = 0.65$) overload successively: Round 1 (+97), Round 2 (+231), Round 3 (+134), Round 4 (+207), Round 5 (+99), Round 6 (+59), Round 7 (+67), Round 8 (+83), Round 9 (+51), Round 10 (+3), Round 11 (+0).
7. **Output Metric**: Total road edges failed = 1,039 edges (24.17% of 4,299 corridor links). Recorded in `coupling_hierarchy_ablation.csv` (line 29).

#### Chain 2: Power Substation Trip (3 Failed Components)
1. **Input Data**: `processed/power_infrastructure.xlsx` (44 substations) and `processed/power_network_geojson.json` (346 lines).
2. **Network Build**: `models/graph_builder.py` (`build_power_graph`, lines 40-180). Snaps tower endpoints $\le 50\text{ m}$.
3. **Scenario Trigger**: Substation `SUB_25` (Banaswadi 220kV) fails initially.
4. **Cascade Propagation**: `models/power_cascade.py` (`PowerCascadeSimulator.run_cascade`, lines 71-83): Failing `SUB_25` trips its 2 incident transmission lines. Displaced load (617.5 MVA) is redistributed across surviving substations weighted by headroom and distance decay. No secondary substation or line exceeds $\theta_{\text{fail}} = 1.10$.
5. **Output Metric**: Total power components failed = 1 substation + 2 lines = 3 components.

---

## 2. PHASE B: INFRASTRUCTURE MODEL AUDITS

### 2.1 Road Transportation Model
1. **Node and Edge Definition**: Nodes are intersections/crossings (`CRN_1` to `CRN_3752`) with coordinates rounded to 6 decimals. Edges are undirected road segments (`nx.Graph()`) with length in meters (Haversine).
2. **Link Unit**: Physical undivided or bidirectional carriageway links.
3. **Capacity & Speed Assumptions**:
   - Trunk/Motorway: $v_0 = 60\text{ km/h}, C = 3600\text{ vph}$.
   - Primary: $v_0 = 45\text{ km/h}, C = 2400\text{ vph}$.
   - Secondary: $v_0 = 35\text{ km/h}, C = 1800\text{ vph}$.
   - Tertiary/Unclassified: $v_0 = 30\text{ km/h}, C = 1400\text{ vph}$.
   - Baseline load ratio: $V_0 / C = 0.65$ across all links uniformly.
4. **BPR Travel Time Function**:
   $$T(V) = T_0 \cdot \left[1 + 0.15 \cdot \left(\frac{V}{C}\right)^4\right]$$
   Implemented correctly in `models/road_cascade.py` line 42 (`_bpr`).
5. **Yen's K-Shortest Paths & MNL Route Choice**:
   - Implemented via `nx.shortest_simple_paths` taking $k=3$ shortest paths weighted by `current_travel_time` (lines 128-131).
   - Logit Choice Probability:
     $$P_j = \frac{\exp(-\theta (T_j - T_{\min}))}{\sum_{m=1}^k \exp(-\theta (T_m - T_{\min}))}$$
     where $\theta = 0.05$ (line 148-152).
6. **Traffic Volume Redistribution**:
   - Displaced volume $V_{\text{disp}}$ of failed edge $(u, v)$ is allocated to the $k$ detour paths between $u$ and $v$: link volume increases by $V_{\text{disp}} \cdot P_j$ for every link along path $j$ (lines 155-170).
7. **Failure and Stress Definitions**:
   - Failed: $V / C \ge 1.25$ (removed from active routing graph).
   - Stressed: $1.00 \le V / C < 1.25$.
8. **Network Scope Distinction**:
   - Full City: 500,170 nodes and 575,733 edges (`build_road_graph`).
   - Silk Board Focal Corridor: 3,752 nodes and 4,299 edges (`build_corridor_road_graph`).
   - **Fact**: All Phase 2 multi-layer simulations use **strictly the Silk Board focal network**, not the 500k city graph.

### 2.2 Power Grid Model
1. **Representation**: 4,063 nodes (44 substations + 4,019 tower junctions) and 4,099 edges (transmission lines).
2. **Physical Solver Status**: **No AC or DC power flow is solved**. Bus admittance matrices, reactive power, phase angles, and generator dispatch curves are omitted (classified as MISSING in OSM).
3. **Headroom Redistribution Model**:
   - Headroom: $\text{SpareCap}_j = \max(0, C_j - L_j)$.
   - Substation allocation weight: $W_j = (\text{SpareCap}_j)^\gamma / (\text{dist}_{ij})^\mu$ with $\gamma = 1.0, \mu = 1.0$ (lines 141-152).
   - Line flow redistribution: Reroutes along shortest path in active grid; if disconnected, shared among top-5 lines with spare capacity (lines 180-218).
4. **Failure Threshold**: Load ratio $L_j / C_j \ge 1.10$ triggers failure. Stressed threshold is $0.90$.
5. **Line Failures Provenance**: The "118 line failures" reported in Phase 1 occurred in scenario `P3_Critical_Transmission_Line` where the primary 220kV Peenya-Nelamangala trunk line was cut. In Phase 2 (S1, S2, S7), substations SUB_25 and SUB_19 fail, losing 2 incident lines each, but their load is safely absorbed by the meshed grid without secondary trips.

### 2.3 Water Distribution Model
1. **Representation**: 34,398 nodes (53 facilities + 34,345 pipe junctions) and 34,550 pipeline edges.
2. **Physical Solver Status**: **No EPANET, Darcy-Weisbach headloss, or pressure gradient equations**. Approximated via topological connected-component supply adequacy.
3. **Supply-Demand Equations**:
   - Localized demand: 0.5 MLD per junction.
   - Facility supply: Water Works = 120 MLD, Reservoirs = 60 MLD, Tanks = 25 MLD.
   - Component Adequacy: $\alpha = \min(1.0, \text{Supply} / \text{Demand})$.
   - Junction Deprivation: $\alpha < 0.50 \implies$ Deprived. Unmet Demand = $\text{Demand} \cdot (1 - \alpha)$.
4. **Data Artifact Forensics**:
   - The OSM water network contains **881 disconnected components**.
   - Only 53 facilities exist. Thus, at least 828 components have **zero facilities**.
   - Therefore, at baseline ($t=0$), before any simulation starts, 33,868 junctions (98.6%) have $\text{Supply} = 0$, producing **16,814.0 MLD baseline unmet demand**.
   - When facility `FAC_1` fails in S5, unmet demand rises to 16,848.0 MLD (+34 MLD). The reported 33,936 deprived junctions are an artifact of network fragmentation, not dynamic hydraulic cascade.

---

## 3. PHASE C: INVESTIGATION OF ZERO HIGHER-ORDER GAIN ($G = 0$)

### 3.1 Metric Verification & Exact Arithmetic

The higher-order gain is defined as:
$$G = F(\text{M7}) - \max(F(\text{M1}), F(\text{M2}), F(\text{M3}))$$
where $F(M)$ is the total count of failed components.

#### Recalculation from Raw Data (`coupling_hierarchy_ablation.csv`):
* **S1_Power_D1_Banaswadi**:
  - M0=3, M1=3, M2=3, M3=3, M4=3, M5=3, M6=3, M7=3.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 3$. $F(\text{M7}) = 3 \implies G = 3 - 3 = \mathbf{0}$.
* **S2_Power_D1_Padmanabha**:
  - M0=3, M1=3, M2=3, M3=3, M4=3, M5=3, M6=3, M7=3.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 3$. $F(\text{M7}) = 3 \implies G = 3 - 3 = \mathbf{0}$.
* **S3_Power_Uncoupled**:
  - M0=1, M1=1, M2=1, M3=1, M4=1, M5=1, M6=1, M7=1.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 1$. $F(\text{M7}) = 1 \implies G = 1 - 1 = \mathbf{0}$.
* **S4_Water_D3_SilkBoard**:
  - M0=1, M1=1, M2=1, M3=1040, M4=1040, M5=1040, M6=1, M7=1040.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 1040$. $F(\text{M7}) = 1040 \implies G = 1040 - 1040 = \mathbf{0}$.
* **S5_Water_Facility_Regional**:
  - M0=2, M1=2, M2=2, M3=2, M4=2, M5=2, M6=2, M7=2.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 2$. $F(\text{M7}) = 2 \implies G = 2 - 2 = \mathbf{0}$.
* **S6_Road_Bottleneck**:
  - M0=1, M1=1, M2=1, M3=1, M4=1, M5=1, M6=1, M7=1.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 1$. $F(\text{M7}) = 1 \implies G = 1 - 1 = \mathbf{0}$.
* **S7_Compound_PowerWater**:
  - M0=4, M1=4, M2=4, M3=1043, M4=1043, M5=1043, M6=4, M7=1043.
  - $\max(\text{M1}, \text{M2}, \text{M3}) = 1043$. $F(\text{M7}) = 1043 \implies G = 1043 - 1043 = \mathbf{0}$.

**Conclusion**: The arithmetic is 100% correct. $G = 0$ holds across all 7 scenarios without exception.

### 3.2 Root Causes: Why D1 and D2 Add Zero Component Failures

#### Cause 1: D2 (Power $\to$ Road) is Physically Empty
In `models/dependency_mapper.py` (lines 143-195), `map_D2_power_to_road` filters for signalized road nodes in the road graph within 300 meters of power substations.
- `silk_board.geojson` contains only 10 signalized intersection nodes.
- None of these 10 nodes are within 300 meters of any of the 44 KPTCL substations.
- As confirmed by `dependency_summary.json` line 9:
  `"D2_power_to_road": { "n_dependencies": 0 }`
- **Result**: D2 has 0 edges in the graph. It is impossible for D2 to trigger.

#### Cause 2: D1 (Power $\to$ Water) Cannot Trigger Pipe Ruptures
In `models/multi_layer_cascade.py` (lines 250-279), D1 reduces the capacity of water facility nodes (`G_wat.nodes[fac_id]["capacity"] *= 0.50`).
- D1 maps 3 pairs (`SUB_25 -> FAC_36`, `SUB_19 -> FAC_31`, `SUB_20 -> FAC_30`).
- When `SUB_25` fails, `FAC_36` capacity is derated from 80 MLD to 40 MLD.
- In `WaterCascadeSimulator`, pipe overpressurization only occurs when flow is diverted from an *already broken pipe*. Reducing facility output reduces flow through feeder pipes, which actually *relieves* hydraulic stress.
- No pipes rupture as a result of D1.
- Because D3 triggers exclusively on *failed pipe junctions*, and D1 produces zero pipe failures, D1 **never reaches the road network**.

#### Cause 3: The Inter-Layer Coupling is an Open-Loop DAG
The dependency graph between layers is:
$$\text{Power} \xrightarrow{\text{D1 (3 pairs)}} \text{Water} \xrightarrow{\text{D3 (419 pairs)}} \text{Road}$$
$$\text{Power} \xrightarrow{\text{D2 (0 pairs)}} \text{Road}$$
There are **zero backward dependencies**:
- Road failures do not affect Power.
- Road failures do not affect Water.
- Water failures do not affect Power.

Because it is an acyclic graph with no feedback loops and D1 cannot trigger D3, the system decomposes into decoupled pathways.

### 3.3 Factorial Interaction Contrasts

To test whether the system exhibits multi-factor interaction beyond the maximum pairwise comparison, we compute the standard $2^k$ factorial contrasts on Scenario S7:

| Contrast | Formula | Computed Value | Interpretation |
|---|---|:---:|---|
| **Incremental D1 given D3** | $F(\text{M4}) - F(\text{M3})$ | $1043 - 1043 = \mathbf{0}$ | Adding D1 to D3 adds 0 failures |
| **Incremental D2 given M4** | $F(\text{M7}) - F(\text{M4})$ | $1043 - 1043 = \mathbf{0}$ | Adding D2 to M4 adds 0 failures |
| **Incremental D3 given M6** | $F(\text{M7}) - F(\text{M6})$ | $1043 - 4 = \mathbf{+1039}$ | D3 produces 100% of amplification |
| **2-way Interaction (D1 $\times$ D3)** | $\text{M4} - \text{M1} - \text{M3} + \text{M0}$ | $1043 - 4 - 1043 + 4 = \mathbf{0}$ | Zero statistical interaction |
| **2-way Interaction (D2 $\times$ D3)** | $\text{M5} - \text{M2} - \text{M3} + \text{M0}$ | $1043 - 4 - 1043 + 4 = \mathbf{0}$ | Zero statistical interaction |
| **2-way Interaction (D1 $\times$ D2)** | $\text{M6} - \text{M1} - \text{M2} + \text{M0}$ | $4 - 4 - 4 + 4 = \mathbf{0}$ | Zero statistical interaction |
| **3-way Interaction (D1 $\times$ D2 $\times$ D3)** | $\text{M7} - \text{M6} - \text{M5} - \text{M4} + \text{M2} + \text{M1} + \text{M3} - \text{M0}$ | $1043 - 4 - 1043 - 1043 + 4 + 4 + 1043 - 4 = \mathbf{0}$ | Zero higher-order interaction |

**Blunt Answer**: In terms of component failure counts, the interaction is identically zero. The system is strictly additive and dominated by D3.

### 3.4 Service-Level vs Component Failure Distinction

While $G = 0$ for *component counts*, Model M7 produces a compound service degradation that M3 alone cannot represent:
- In **M3 (Water $\to$ Road only)**: Power is 100% operational; Water facility `FAC_36` operates at 100% capacity (80 MLD); only road links fail.
- In **M7 (Full Coupling)**:
  - Substation `SUB_25` is offline (displacing 617.5 MVA).
  - Water tank `FAC_36` is derated by 50% ($80 \to 40\text{ MLD}$), creating localized water supply deficits.
  - Road network incurs 1,039 failed links and a network-wide travel time inflation of $1.048\times$.

---

## 4. PHASE D: EXPERIMENTAL ROBUSTNESS AUDIT

### 4.1 Parameter Sweep Evaluation Table

| Parameter | Physical Meaning | Range Tested | Baseline Value | Sensitivity Finding | Robustness Classification |
|---|---|:---:|:---:|---|---|
| $s_{pw}$ | D1 Power $\to$ Water capacity reduction factor | $[0.0, 1.0]$ in steps of 0.25 | 0.50 | Water unmet demand changes by only +2.5 MLD at $s_{pw}=1.0$. Zero road failures. | **Robust (Inelastic)** |
| $\alpha_{wr}$ | D3 Water $\to$ Road retained capacity factor | $[0.1, 0.8]$ | 0.40 | Non-linear threshold: $\alpha_{wr} \ge 0.8 \implies 0$ fails; $\alpha_{wr} = 0.6 \implies 206$ fails; $\alpha_{wr} \le 0.5 \implies 1039$ fails. | **Sensitive (Bifurcation at 0.60)** |
| $\theta_{\text{fail}}^{\text{road}}$ | Road failure threshold ($V/C$) | $[1.15, 1.35]$ | 1.25 | Tested in `threshold_sensitivity_results.csv`. Cascade halts if threshold $> 1.65$. | **Moderately Sensitive** |
| D2 Buffer | Distance for signal-substation dependency | 300 m | 300 m | Not swept. 0 links mapped at 300m. | **Untested Vulnerability** |
| D3 Buffer | Distance for pipe-road flooding | 25 m | 25 m | Not swept. | **Untested** |
| Random Seeds | Monte Carlo traffic sampling | None (0 runs) | N/A | Simulation is 100% deterministic. | **Untested Stochasticity** |

---

## 5. PHASE E: OUTCOME METRIC ASSESSMENT

The current comparison evaluates:
$$F = N_{\text{sub}} + E_{\text{lines}} + N_{\text{fac}} + E_{\text{pipes}} + E_{\text{roads}}$$

### Breakdown of Network Scales & Component Types

| Layer | Component Entity | Total in Network | Failed in S7 (M7) | Failure Fraction (%) |
|---|---|:---:|:---:|:---:|
| **Power** | Substations (Nodes) | 44 | 1 | 2.27% |
| **Power** | Transmission Lines (Edges) | 4,099 | 2 | 0.05% |
| **Water** | Facilities (Nodes) | 53 | 0 | 0.00% |
| **Water** | Transmission Pipes (Edges) | 34,550 | 1 | 0.003% |
| **Road** | Corridor Road Segments (Edges) | 4,299 | 1,039 | **24.17%** |
| **Total** | Mixed Components | 42,995 | 1,043 | 2.43% |

**Audit Warning**: Because the road layer has 4,299 links in a congested urban bottleneck and water/power have very few initial component failures, the raw failure count $F$ is **99.6% dominated by road links**. Combining heterogeneous component types without normalization creates the illusion of single-layer dominance.

---

## 6. PHASE F: LITERATURE & NOVELTY POSITIONING

### 6.1 Critical Comparison with Key Benchmark Literature

| Reference | System Studied | Coupling Model | Key Finding | Comparison with this Project |
|---|---|---|---|---|
| **Buldyrev et al. (2010)** *Nature*, 464: 1025–1028 | Synthetic 2-layer power-internet networks | 1-to-1 interdependent percolation | Discontinuous, first-order catastrophic collapse. | Buldyrev assumed bidirectional 1-to-1 dependencies. This project uses real urban spatial data and finds that topological asymmetry prevents runaway super-additive collapse. |
| **Rinaldi et al. (2001)** *IEEE Control Syst.*, 21(6): 11–25 | Conceptual infrastructure taxonomy | Physical, cyber, geographic, logical coupling | Defined coupling categories. | This project operationalizes physical/geographic coupling (D1, D2, D3) on real GIS data for an Indian megacity. |
| **Ouyang (2014)** *Rel. Eng. & Sys. Safety*, 121: 43–60 | Review of interdependent infrastructure | Comparative review of graph vs simulation models | Emphasized that pure topological models overestimate cascades. | Confirms this project's finding: flow-based capacity constraints and localized buffers limit cascade spread. |
| **Zhang et al. (2018)** *ASCE J. Infrastruct. Syst.*, 24(4) | Power-water-gas empirical networks | Multi-layer graph flow equations | Interdependence amplifies losses non-linearly. | Zhang et al. evaluated utility-utility coupling. This project adds road transportation under dynamic traffic assignment (BPR + MNL). |

### 6.2 Truth About Novelty
- **Is $G = 0$ a failure of the model?** No. It is an honest, scientifically valid result. Claiming that multi-layer coupling *must* produce higher-order gains is a confirmation bias common in synthetic network literature.
- **Genuine Research Contribution**: Proving that on real-world spatial networks, **inter-layer dependencies do not automatically create super-additive failure cascades**; rather, cascades are bottleneck-gated and dominated by asymmetric interfaces (Water $\to$ Road).

---

## 7. PHASE G: THREE TESTABLE, PUBLISHABLE RESEARCH CONTRIBUTIONS

### Contribution 1: Topological Gating and Pathway Dominance in Real-World Infrastructure Networks
* **Research Question**: Does spatial heterogeneity in empirical urban networks prevent runaway higher-order cascading failures?
* **Hypothesis**: In contrast to synthetic multiplex models, real-world multi-layer urban networks exhibit strong topological gating where failure cascades are confined to specific asymmetric physical interfaces.
* **Falsification Condition**: Identifying any scenario where $G > 0$ under realistic operating margins.

### Contribution 2: Non-Linear Tipping Points at the Water-Road Interface
* **Research Question**: What critical capacity retention threshold governs the transition from localized flooding to network-wide traffic gridlock?
* **Hypothesis**: Traffic redistribution under BPR travel time exhibits a bifurcation at $\alpha_{wr} \approx 0.60$: capacity cuts above 40% are absorbed locally, whereas cuts $\ge 40\%$ trigger a 1,000+ link cascade.
* **Falsification Condition**: Demonstrating linear scaling between flood capacity reduction and road failure counts.

### Contribution 3: The Decoupling of Service-Level Degradation from Component-Failure Metrics
* **Research Question**: Why do component-counting resilience metrics ($F$) fail to capture multi-layer vulnerability?
* **Hypothesis**: Higher-order coupling manifests in simultaneous multi-service performance degradation (voltage drop, water pressure deficit, traffic delay) rather than secondary physical component destruction.
* **Falsification Condition**: Showing that service degradation is strictly proportional to topological component failure counts.

---

## 8. ACTIONABLE RECOMMENDATIONS FOR CODE REFINEMENT (READ-ONLY ADVICE)

If authorized to run future experiments:
1. **Fix D2 Spatial Buffer**: Expand D2 threshold from 300m to 1,000m or snap to nearest 66kV distribution substation so that D2 has non-zero mapped links.
2. **Normalize Metrics**: Report layer-specific failure fractions:
   $$F_{\text{norm}} = \frac{1}{3} \left(\frac{F_{\text{power}}}{N_{\text{power}}} + \frac{F_{\text{water}}}{N_{\text{water}}} + \frac{F_{\text{road}}}{N_{\text{road}}}\right)$$
3. **Resolve Water Baseline Demand**: Filter out disconnected pipe components without facilities so that baseline unmet demand starts at 0 MLD instead of 16,814 MLD.
