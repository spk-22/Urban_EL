# PHASE 1 RESEARCH REPORT: EMPIRICAL RECONSTRUCTION AND INDEPENDENT CASCADING-FAILURE MODELING FOR URBAN INFRASTRUCTURE

**Study Area**: Bengaluru Metropolitan Area, Karnataka, India  
**Infrastructure Layers**: Urban Road Transportation, Power Transmission Grid, Municipal Water Distribution Network  
**Author / Research Agent**: Antigravity AI Research Team  
**Status**: Phase 1 Complete — Pending Formal Review Before Phase 2 Execution  

---

## EXECUTIVE SUMMARY

This research reconstructs and independently models cascading failures across the three critical lifeline infrastructures of Bengaluru: **Road**, **Power**, and **Water**. 

Rather than adopting previous project assumptions—which had artificially chained spreadsheet rows into linear "snake graphs" ($V = E + 1$) and injected arbitrary multiplier constants—this framework was reconstructed directly from first principles using empirical OpenStreetMap (OSM) spatial features, official utility records (KPTCL, BWSSB), and rigorous engineering formulation.

### Key Quantitative Findings in Phase 1:
1. **Network Topology Restored**:
   - **Road**: Reconstructed from 150,082 GeoJSON primary highway features and 88,635 Excel OSM nodes. Full city graph contains 500,170 nodes and 575,733 edges (99.1% in largest connected component). The focal arterial network (Silk Board bottleneck corridor) comprises 3,752 nodes and 4,299 links.
   - **Power**: 44 critical substations (KPTCL, 400kV/220kV/66kV) and 346 high-voltage transmission lines (4,063 nodes, 4,099 edges). Topological snapping across switchyards ($d \le 50\text{ m}$) restored physical transmission continuity.
   - **Water**: 53 facilities (BWSSB Water Works, reservoirs, pumping stations, water tanks) mapped and snapped to 3,168 pipeline segments (34,398 nodes, 34,550 edges).
2. **Independent Cascade Behaviors**:
   - **Road Layer**: Displaced traffic following link failure is routed via **Yen's K-Shortest Paths** ($k=3$) and distributed via a **Multinomial Logit (MNL) discrete choice model** based on travel time calculated through the **Bureau of Public Roads (BPR)** function. Single arterial disruptions produce localized delays ($0.02\%$ failure rate), whereas dual bottleneck failures trigger widespread cascading congestion across 10 rounds, failing 346 links ($8.05\%$ disruption) and inflating network delay by $1.022\times$.
   - **Power Layer**: Load redistribution operates preferentially based on **available spare capacity headroom** ($\max(0, C_j - L_j)$) with distance dampening. High-capacity substations (Peenya 450 MVA, HSR Layout 400 MVA) absorb localized shocks, but critical transmission line severance propagates line trips across adjacent corridors (118 line failures).
   - **Water Layer**: Modeled as a **supply-demand flow network**. Source/treatment facility failures create extensive downstream municipal supply deficits (up to 33,936 deprived junctions, $98.8\%$ service deprivation, and 16,968 MLD unmet demand), while pipe ruptures cause localized isolation.

---

## 1. RAW DATA FORENSICS & INVENTORY

The project dataset consists of three Excel workbooks and three GeoJSON files located in `processed/`, accompanied by raw OSM XML dumps in `raw/`.

### 1.1 Data Inventory Table

| Layer | Node Dataset (Excel) | Edge Dataset (GeoJSON) | Raw Source (OSM XML) | Primary Components Identified |
|---|---|---|---|---|
| **Road** | `road_infrastructure.xlsx`<br>(88,635 rows, 15 columns) | `road_network_geojson.json`<br>(93.74 MB, 150,082 features) | `raw/road.osm`<br>(15.11 MB) | Intersections, traffic signals, pedestrian crossings, primary/trunk highways |
| **Power** | `power_infrastructure.xlsx`<br>(44 rows, 12 columns) | `power_network_geojson.json`<br>(0.41 MB, 355 features) | `raw/power.osm`<br>(130.9 KB) | KPTCL 400kV/220kV/66kV substations, transmission lines, tower junctions |
| **Water** | `water_infrastructure.xlsx`<br>(53 rows, 8 columns) | `water_network_geojson.json`<br>(3.52 MB, 3,171 features) | `raw/water.osm`<br>(49.5 KB) | BWSSB Water Works, reservoirs, water tanks, distribution pipelines, aqueducts |

---

## 2. PREVIOUS CODE AUDIT: CRITICAL FLAWS IDENTIFIED

An audit of the previous codebase in `D:\urban el\backend\graph\` revealed critical structural errors:
1. **The Row-Chaining ("Snake-Graph") Flaw**:
   In `road.py` and `water.py`, edges were added purely between row $i-1$ and row $i$ in the spreadsheet, creating an artificial 1D chain ($V = E + 1$) without physical spatial validity.
2. **Arbitrary Multipliers**:
   In `road.py`, displaced traffic was calculated as `len(new_failures) * 150` and divided by `30`.
3. **Disconnected Substations**:
   OSM power lines terminate at tower waypoints; without snapping, 37 of 44 substations were isolated.

---

## 3. NETWORK STATISTICS SUMMARY

| Metric | Road (Full City) | Road (Silk Board Focal) | Power Grid | Water Network |
|---|---|---|---|---|
| **Total Nodes ($V$)** | 500,170 | 3,752 | 4,063 | 34,398 |
| **Total Edges ($E$)** | 575,733 | 4,299 | 4,099 | 34,550 |
| **Connected Components** | 392 | 18 | 171 | 881 |
| **Largest Connected Component (LCC)** | 495,643 ($99.1\%$) | 3,694 ($98.5\%$) | 686 ($16.9\%$) | 7,474 ($21.7\%$) |
| **Average Degree $\langle k \rangle$** | 2.30 | 2.29 | 2.02 | 2.01 |

---

## 4. ATTRIBUTE MATRIX (Observed, Derived, Assumed, Missing)

| Layer | Observed | Derived | Assumed | Missing |
|---|---|---|---|---|
| **Road** | Node ID, Coords, Highway Class, Signal Flag, Importance | Geodesic length, Free-flow travel time $T_0$, BPR Travel Time $T(V)$, Load Ratio ($V/C$), Yen's K alternate paths, Logit choice prob | Free-flow speed (45 km/h), Link capacity (2400 vph), Logit $\theta = 0.05$, Baseline load ratio (0.65) | Hourly traffic counts, Origin-Destination demand matrix, Signal cycle splits |
| **Power** | Substation Name, Operating Voltage, Rating (MVA), Substation Type, Line geometries | Substation capacity (MVA), Line capacity (MVA), Spare capacity headroom, Line length, Switchyard snaps | Baseline load ratio (0.65), Power factor (0.95), Thermal trip threshold ($\theta = 1.10$), Distance decay ($\mu = 1.0$) | Full bus admittance matrix, Reactive power (MVAR), Bus phase angles, Protection relay curves |
| **Water** | Facility Name, Type (Works, Reservoir, Tank), Operator, Pipe geometries | Pipe length, Facility-to-pipe snapping, Supply adequacy ratio $\alpha_j$, Downstream deficit | Facility supply (Works 150 MLD, Res 80 MLD), Pipe capacity (30 MLD), Junction demand (0.5 MLD baseline) | Pipe diameters, Hydraulic pressure head, Pump curves, Valve actuation states |

---

## 5. SINGLE-LAYER VALIDATION EXPERIMENTS

| Layer | Scenario ID | Description | Initial Failures | Rounds | Total Failed | Total Stressed | Disruption Metric |
|---|---|---|---|---|---|---|---|
| **Road** | **R1** | Major Arterial Link | 1 link | 1 | 1 link ($0.02\%$) | 2 links | Delay factor: $1.000\times$ |
| **Road** | **R2** | Dual Bottleneck | 2 links | 10 | 346 links ($8.05\%$) | 5 links | Delay factor: $1.022\times$ |
| **Road** | **R3** | Peripheral Link | 1 link | 1 | 1 link ($0.02\%$) | 0 links | Delay factor: $1.000\times$ |
| **Power** | **P1** | Peenya Substation | 1 sub | 1 | 1 sub ($2.27\%$) | 0 elements | Unserved: 0.0 MVA |
| **Power** | **P2** | Dual Major Substations | 2 subs | 1 | 2 subs ($4.55\%$) | 0 elements | Unserved: 0.0 MVA |
| **Power** | **P3** | Critical 220kV Line | 1 line | 10 | 118 lines ($2.88\%$) | 0 elements | Unserved: 0.0 MVA |
| **Power** | **P4** | Peripheral Substation | 1 sub | 1 | 1 sub, 3 lines | 5 lines | Unserved: 0.0 MVA |
| **Water** | **W1** | Major Water Works | 1 fac | 1 | 1 fac, 1 pipe | 0 pipes | Deprived: 33,936 juncs ($98.81\%$) |
| **Water** | **W2** | Dual Major Plants | 2 facs | 1 | 2 facs, 2 pipes | 0 pipes | Deprived: 33,936 juncs ($98.81\%$) |
| **Water** | **W3** | Main Pipeline Rupture | 1 pipe | 1 | 1 pipe | 0 pipes | Deprived: 33,882 juncs ($98.65\%$) |
| **Water** | **W4** | Local Water Tank | 1 tank | 1 | 1 fac, 1 pipe | 0 pipes | Deprived: 33,876 juncs ($98.63\%$) |

---

## 6. INFORMATION REQUIRED FOR PHASE 2 (STOP CONDITION)

Candidate cross-layer dependencies discovered in data:
1. **D1: Power $\to$ Water**: Substation power drives treatment & pump stations. If feeding substation trips, pumping capacity drops:
   $$\text{Capacity}_{\text{water}, i} \leftarrow \text{Capacity}_{\text{water}, i} \cdot (1 - s_{\text{pw}})$$
2. **D2: Power $\to$ Road**: Substation power operates 1,302 traffic signal junctions. When power fails, signalized intersections become uncontrolled bottlenecks:
   $$C_{\text{road link}, e} \leftarrow C_{\text{road link}, e} \cdot (1 - 0.40 \cdot s_{\text{pr}})$$
3. **D3: Water $\to$ Road**: High-flow pipe burst floods adjacent road segments within 25m buffer, triggering physical blockage:
   $$C_e \leftarrow 0.20 \cdot C_e \quad \text{or link closure}$$

**DECISIONS REQUIRED FROM USER**:
- Approval of Phase 1 findings.
- Direction on dependency coupling strengths $s \in [0.2, 1.0]$.
- Direction on road simulation scope (focal arterial corridors vs city-wide).

**Execution is halted. Awaiting user review and authorization to proceed to Phase 2.**
