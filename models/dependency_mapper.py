"""
Cross-Layer Dependency Mapper
=============================
Maps physically defensible component-level dependencies between:
  D1: Power Substation -> Water Facility (electrical support)
  D2: Power Substation -> Road Intersection (signal operation)
  D3: Water Pipe Junction -> Road Segment (flooding/obstruction)

PARAMETER CLASSIFICATION (per Section 5 of Phase-2 spec):
-----------------------------------------------------------
All parameters are explicitly classified as:
  OBSERVED   : directly in data
  DERIVED    : calculated from data
  INFERRED   : strong engineering inference
  ASSUMED    : introduced because data lacks operational info
  MISSING    : required but unavailable
"""

import logging
import math
import numpy as np
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)


def haversine_m(lat1, lon1, lat2, lon2):
    """Geodesic distance in meters."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =============================================================================
# D1 PARAMETERS
# =============================================================================
# Spatial threshold: 500 m
#   INFERRED: Urban distribution substations in Indian cities (e.g. KPTCL/BESCOM
#   LT/HT feeders) serve a radius of ~300-1000 m. 500 m is a conservative proxy.
#   Real feeder routing is MISSING from OSM data.
# Source type: substations (all types in data; voltage field OBSERVED)
# Dependency: each water facility assigned to nearest substation within threshold.
#   Status: ASSUMED spatial proxy — sensitivity tested at 250 m, 500 m, 1000 m.

# Spatial threshold: 2500 m
#   INFERRED: Urban medium-voltage distribution feeders (11kV/33kV) from bulk
#   transmission substations serve an urban radius of 2000-3000 m in Indian megacities.
#   2500 m captures primary pump station feeder catchment. Real cable routing MISSING.
# Source type: substations (all types in data; voltage field OBSERVED)
# Dependency: each water facility assigned to nearest substation within threshold.

D1_SPATIAL_THRESHOLD_M = 2500.0
D1_PARAMETER_TYPE = "INFERRED"
D1_UNCERTAINTY = "Real electrical feeder routing unavailable in OSM. Threshold represents medium-voltage feeder catchment."

# Hydraulic Transient Shock parameter:
# Sudden pump trip creates backpressure surge (water hammer) on incident transmission pipes
D1_TRANSIENT_SURGE = 0.35

# =============================================================================
# D2 PARAMETERS
# =============================================================================
# Spatial threshold: 2500 m
#   INFERRED: Traffic signal controllers and local intersection cabinets are fed
#   by local distribution transformers tied to the district substation within 2500 m.
# Signal node filter: traffic_signal OBSERVED attribute in road Excel data.
# Capacity reduction alpha_pr:
#   INFERRED from HCM principles: unsignalized intersections handle ~50-70% of
#   signalized throughput. Engineering guidance suggests 20-40% reduction.
#   Central estimate: alpha_pr = 0.30. Range: 0.10-0.50.

D2_SPATIAL_THRESHOLD_M = 2500.0
D2_ALPHA_PR_CENTRAL = 0.30
D2_ALPHA_PR_RANGE = [0.10, 0.20, 0.30, 0.40, 0.50]
D2_PARAMETER_TYPE = "INFERRED"
D2_UNCERTAINTY = "Signal-feeder routing unavailable. Mapped to nearest serving district substation."

# =============================================================================
# D3 PARAMETERS
# =============================================================================
# Spatial buffer: 25 m
#   ASSUMED: Urban road lane widths are 3.0-3.7 m (IRC standard). Mains running
#   alongside/beneath roads are within ~5-25 m of the road centerline.
#   25 m is a conservative upper bound. Sensitivity: 10 m, 25 m, 50 m.
# Capacity filter: >= 10 MLD (INFERRED as transmission/district main threshold;
#   ~115 L/s, consistent with >= 200 mm diameter).
# Road capacity retention alpha_wr:
#   ASSUMED. Central estimate: 0.40 (60% reduction; one lane blocked).
#   Range: 0.20, 0.40, 0.60 (severe, moderate, mild flooding).

D3_SPATIAL_BUFFER_M = 25.0
D3_ALPHA_WR_CENTRAL = 0.40
D3_ALPHA_WR_RANGE = [0.20, 0.40, 0.60]
D3_MIN_CAPACITY_MLD = 10.0
D3_PARAMETER_TYPE = "ASSUMED"
D3_UNCERTAINTY = "Pipe diameters/pressures unavailable in OSM. Buffer and capacity factor are assumptions."

# =============================================================================
# CYCLIC FEEDBACK LOOP PARAMETERS (M7 FULL COUPLING)
# =============================================================================
# D4: Road -> Power (Repair crews, fuel tankers, and maintenance personnel access choke)
#   When road network suffers severe congestion delay (D_road > 1.0),
#   emergency technicians cannot service stressed substations, derating headroom.
D4_GAMMA_RP_CENTRAL = 0.35

# D5: Road -> Water (Emergency valve isolation and chemical logistics choke)
#   Severe traffic bottlenecks prevent water utility crews from isolating burst pipes.
D5_GAMMA_RW_CENTRAL = 0.30

# D6: Water -> Road (Community water scarcity emergency procurement travel)
#   Unmet water demand induces frantic community travel and water tanker traffic.
D6_BETA_WR_CENTRAL = 0.25


def map_D1_power_to_water(G_power, G_water, threshold_m=D1_SPATIAL_THRESHOLD_M):
    """
    Maps each water FACILITY to its nearest power SUBSTATION within threshold_m.
    D1 physical mechanism: power loss -> pump/treatment capacity reduction.
    """
    substations = [(nid, ndata) for nid, ndata in G_power.nodes(data=True)
                   if ndata.get("entity_type") == "substation"]
    if not substations:
        logger.warning("[D1] No power substations found in G_power.")
        return {}, []

    sub_ids = [s[0] for s in substations]
    sub_coords = np.array([[s[1]["longitude"], s[1]["latitude"]] for s in substations])
    tree = cKDTree(sub_coords)

    facilities = [(nid, ndata) for nid, ndata in G_water.nodes(data=True)
                  if ndata.get("entity_type") == "facility"]

    dependency_map = {}
    dependency_records = []

    for fac_id, fac_data in facilities:
        fac_coord = [fac_data["longitude"], fac_data["latitude"]]
        dist_deg, idx = tree.query(fac_coord)
        dist_m = dist_deg * 111000.0
        if dist_m <= threshold_m:
            sub_id = sub_ids[idx]
            sub_data = substations[idx][1]
            dependency_map[fac_id] = sub_id
            dependency_records.append({
                "dependency": "D1",
                "source_layer": "Power",
                "source_id": sub_id,
                "source_name": sub_data.get("name", sub_id),
                "target_layer": "Water",
                "target_id": fac_id,
                "target_name": fac_data.get("name", fac_id),
                "mechanism": "Power substation failure -> water pump/treatment loses electrical support -> capacity reduction",
                "spatial_distance_m": round(dist_m, 1),
                "evidence": "Spatial proximity proxy (< {}m); real feeder routing MISSING".format(int(threshold_m)),
                "parameter_type": D1_PARAMETER_TYPE,
                "uncertainty": D1_UNCERTAINTY
            })

    logger.info(f"[D1] Mapped {len(dependency_map)}/{len(facilities)} water facilities "
                f"to power substations (threshold={threshold_m}m).")
    return dependency_map, dependency_records


def map_D2_power_to_road(G_power, G_road, threshold_m=D2_SPATIAL_THRESHOLD_M):
    """
    Maps each SIGNALIZED road intersection to its nearest power SUBSTATION.
    D2 physical mechanism: power loss -> signal outage -> capacity reduction.
    Only nodes with traffic_signal attribute are mapped (OBSERVED data field).
    """
    substations = [(nid, ndata) for nid, ndata in G_power.nodes(data=True)
                   if ndata.get("entity_type") == "substation"]
    if not substations:
        logger.warning("[D2] No power substations found.")
        return {}, []

    sub_ids = [s[0] for s in substations]
    sub_coords = np.array([[s[1]["longitude"], s[1]["latitude"]] for s in substations])
    tree = cKDTree(sub_coords)

    # Filter: only signalized nodes (traffic_signal field OBSERVED in Excel data)
    signal_nodes = [
        (nid, ndata) for nid, ndata in G_road.nodes(data=True)
        if (str(ndata.get("traffic_signal", "none")).lower() not in ["none", "nan", ""]
            or str(ndata.get("road_node_type", "")).lower() in
               ["signalized junction", "major intersection"])
    ]

    dependency_map = {}
    dependency_records = []

    for rn_id, rn_data in signal_nodes:
        rn_coord = [rn_data["longitude"], rn_data["latitude"]]
        dist_deg, idx = tree.query(rn_coord)
        dist_m = dist_deg * 111000.0
        if dist_m <= threshold_m:
            sub_id = sub_ids[idx]
            sub_data = substations[idx][1]
            dependency_map[rn_id] = sub_id
            dependency_records.append({
                "dependency": "D2",
                "source_layer": "Power",
                "source_id": sub_id,
                "source_name": sub_data.get("name", sub_id),
                "target_layer": "Road",
                "target_id": rn_id,
                "target_name": rn_data.get("road_node_type", rn_id),
                "mechanism": "Power failure -> signal outage -> unsignalized operation -> capacity reduction",
                "spatial_distance_m": round(dist_m, 1),
                "evidence": "Traffic signal attribute OBSERVED; feeder routing INFERRED (< {}m)".format(int(threshold_m)),
                "parameter_type": D2_PARAMETER_TYPE,
                "uncertainty": D2_UNCERTAINTY
            })

    logger.info(f"[D2] Found {len(signal_nodes)} signalized nodes; "
                f"mapped {len(dependency_map)} to substations (threshold={threshold_m}m).")
    return dependency_map, dependency_records


def map_D3_water_to_road(G_water, G_road, buffer_m=D3_SPATIAL_BUFFER_M,
                          min_capacity_mld=D3_MIN_CAPACITY_MLD):
    """
    Maps water pipe junctions to nearby road EDGES within buffer_m.
    D3 physical mechanism: pipe burst -> flooding -> road capacity reduction.
    Only high-capacity junctions (>=min_capacity_mld) are flooding candidates.
    """
    water_candidates = [
        (nid, ndata) for nid, ndata in G_water.nodes(data=True)
        if ndata.get("entity_type") == "pipe_junction"
        and ndata.get("capacity", 0.0) >= min_capacity_mld
    ]
    if not water_candidates:
        logger.warning("[D3] No qualifying water pipe junctions found.")
        return {}, []

    w_ids = [w[0] for w in water_candidates]
    w_coords = np.array([[w[1]["longitude"], w[1]["latitude"]] for w in water_candidates])
    water_tree = cKDTree(w_coords)

    thresh_deg = buffer_m / 111000.0
    dependency_map = {}
    dependency_records = []

    for u, v, edata in G_road.edges(data=True):
        u_data = G_road.nodes[u]
        v_data = G_road.nodes[v]
        mid_lon = (u_data["longitude"] + v_data["longitude"]) / 2.0
        mid_lat = (u_data["latitude"] + v_data["latitude"]) / 2.0

        indices = water_tree.query_ball_point([mid_lon, mid_lat], thresh_deg)
        if indices:
            road_edge = (u, v)
            for idx in indices:
                wid = w_ids[idx]
                wdata = water_candidates[idx][1]
                dist_m = haversine_m(mid_lat, mid_lon, wdata["latitude"], wdata["longitude"])
                if road_edge not in dependency_map:
                    dependency_map[road_edge] = []
                dependency_map[road_edge].append(wid)
                dependency_records.append({
                    "dependency": "D3",
                    "source_layer": "Water",
                    "source_id": wid,
                    "source_name": wdata.get("name", wid),
                    "target_layer": "Road",
                    "target_id": "{}-{}".format(u, v),
                    "target_name": edata.get("road_name", "edge_{}-{}".format(u, v)),
                    "mechanism": "Pipe burst/failure -> road flooding -> capacity reduction",
                    "spatial_distance_m": round(dist_m, 1),
                    "evidence": (
                        "Spatial co-location (< {}m); capacity >= {} MLD "
                        "(INFERRED transmission main); flooding consequence ASSUMED"
                    ).format(int(buffer_m), int(min_capacity_mld)),
                    "parameter_type": D3_PARAMETER_TYPE,
                    "uncertainty": D3_UNCERTAINTY
                })

    logger.info(f"[D3] Mapped {len(dependency_map)} road edges to water flooding sources "
                f"(buffer={buffer_m}m, min_cap={min_capacity_mld} MLD).")
    return dependency_map, dependency_records


def build_all_dependencies(G_power, G_water, G_road,
                            d1_threshold_m=D1_SPATIAL_THRESHOLD_M,
                            d2_threshold_m=D2_SPATIAL_THRESHOLD_M,
                            d3_buffer_m=D3_SPATIAL_BUFFER_M):
    """
    Builds all three cross-layer dependency maps at once.
    Returns dict with d1_map, d2_map, d3_map, all_records, summary.
    """
    d1_map, d1_records = map_D1_power_to_water(G_power, G_water, d1_threshold_m)
    d2_map, d2_records = map_D2_power_to_road(G_power, G_road, d2_threshold_m)
    d3_map, d3_records = map_D3_water_to_road(G_water, G_road, d3_buffer_m)

    all_records = d1_records + d2_records + d3_records
    summary = {
        "D1_power_to_water": {
            "n_dependencies": len(d1_map),
            "threshold_m": d1_threshold_m,
            "parameter_type": D1_PARAMETER_TYPE,
            "uncertainty": D1_UNCERTAINTY,
        },
        "D2_power_to_road": {
            "n_dependencies": len(d2_map),
            "threshold_m": d2_threshold_m,
            "alpha_pr_central": D2_ALPHA_PR_CENTRAL,
            "alpha_pr_range": D2_ALPHA_PR_RANGE,
            "parameter_type": D2_PARAMETER_TYPE,
            "uncertainty": D2_UNCERTAINTY,
        },
        "D3_water_to_road": {
            "n_dependencies": len(d3_map),
            "buffer_m": d3_buffer_m,
            "alpha_wr_central": D3_ALPHA_WR_CENTRAL,
            "alpha_wr_range": D3_ALPHA_WR_RANGE,
            "parameter_type": D3_PARAMETER_TYPE,
            "uncertainty": D3_UNCERTAINTY,
        }
    }
    logger.info(f"[DependencyMapper] D1={len(d1_map)}, D2={len(d2_map)}, D3={len(d3_map)} total pairs.")
    return {"d1_map": d1_map, "d2_map": d2_map, "d3_map": d3_map,
            "all_records": all_records, "summary": summary}

