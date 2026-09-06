import math
from datetime import datetime, timezone
from shapely.geometry import LineString, Polygon
from database import SessionLocal, Vessel, Incident, SpatialData, Base, engine

print("Resetting database tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# ── Geometry helpers ──────────────────────────────────────────────────────────

def make_trailing_wake(lon, lat, heading_deg, length_km):
    rad = math.radians(heading_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    nx, ny = -uy, ux
    len_deg  = length_km / 111.0
    half_l   = len_deg * 0.5
    ship_lon = lon + half_l * ux
    ship_lat = lat + half_l * uy
    w_start  = (lon - half_l * ux, lat - half_l * uy)
    w_mid1   = (lon - half_l * 0.35 * ux + 0.004 * nx, lat - half_l * 0.35 * uy + 0.004 * ny)
    w_mid2   = (lon + half_l * 0.35 * ux - 0.002 * nx, lat + half_l * 0.35 * uy - 0.002 * ny)
    w_ship   = (ship_lon, ship_lat)
    track    = LineString([w_start, w_mid1, w_mid2, w_ship])
    w_head   = (ship_lon - 0.015 * ux, ship_lat - 0.015 * uy)
    tail_w, mid_w, head_w = 0.015, 0.010, 0.0035
    p_tail_tip = (w_start[0] - 0.01 * ux, w_start[1] - 0.01 * uy)
    p_tail_l   = (w_start[0] + tail_w * nx, w_start[1] + tail_w * ny)
    p_mid_l    = (lon + mid_w * nx, lat + mid_w * ny)
    p_head_l   = (w_head[0] + head_w * nx, w_head[1] + head_w * ny)
    p_head_r   = (w_head[0] - head_w * nx, w_head[1] - head_w * ny)
    p_mid_r    = (lon - mid_w * nx, lat - mid_w * ny)
    p_tail_r   = (w_start[0] - tail_w * nx, w_start[1] - tail_w * ny)
    poly = Polygon([p_tail_tip, p_tail_l, p_mid_l, p_head_l, w_head,
                    p_head_r, p_mid_r, p_tail_r, p_tail_tip]).buffer(0.002)
    return track, poly, ship_lon, ship_lat

def make_wind_drift_pool(lon, lat, heading_deg, length_km):
    rad = math.radians(heading_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    len_deg  = length_km / 111.0
    half_l   = len_deg * 0.5
    ship_lon = lon + half_l * ux
    ship_lat = lat + half_l * uy
    track    = LineString([(lon - half_l * ux, lat - half_l * uy), (lon, lat), (ship_lon, ship_lat)])
    drift_angle = rad + 1.3
    pool_cx = lon + math.sin(drift_angle) * 0.032
    pool_cy = lat + math.cos(drift_angle) * 0.032
    pts, r_base = [], 0.030
    for i in range(16):
        ang = (2 * math.pi * i) / 16
        r = r_base * (1.0 + 0.32 * math.sin(3 * ang) + 0.18 * math.cos(2 * ang))
        pts.append((pool_cx + r * math.cos(ang) * 1.3, pool_cy + r * math.sin(ang) * 0.85))
    pts.append(pts[0])
    poly = Polygon(pts).buffer(0.0025)
    return track, poly, ship_lon, ship_lat

def make_secondary_track(base_lon, base_lat, d_lon, d_lat, heading_deg):
    sec_lon = base_lon + d_lon
    sec_lat = base_lat + d_lat
    rad = math.radians(heading_deg)
    track = LineString([
        (sec_lon - 0.15 * math.sin(rad), sec_lat - 0.15 * math.cos(rad)),
        (sec_lon - 0.05 * math.sin(rad), sec_lat - 0.05 * math.cos(rad)),
        (sec_lon, sec_lat)
    ])
    return track, sec_lon, sec_lat

# ── Hardcoded incident data — matches provided JSON exactly ───────────────────
# secondary_vessel fields: (name, mmsi, imo, flag, type, length_m, d_lon, d_lat, heading)

INCIDENTS = [
    # 01 RATNAGIRI
    {
        "name": "RATNAGIRI INC-001", "spill_type": "Trailing Wake",
        "date": "2025-10-10T01:03:46Z", "date_display": "10 October 2025   01:03 UTC",
        "location": "Offshore Ratnagiri / Konkan Coast",
        "area_km2": 29.8, "length_km": 56.0,
        "eez": "India", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025101",
        "confidence": 98, "category": "Normal Vessel", "comment": None,
        "center_lat": 17.538, "center_lon": 72.878, "heading": 160,
        "vessel": ("Ark Prestige", "419559000", "9116242", "India", "Other", 150, False),
        "sec_vessel": None,
    },
    # 02 MAHARASHTRA
    {
        "name": "MAHARASHTRA INC-002", "spill_type": "Trailing Wake",
        "date": "2026-06-12T01:10:54Z", "date_display": "12 June 2026   01:10 UTC",
        "location": "Offshore Maharashtra Limits",
        "area_km2": 6.8, "length_km": 26.0,
        "eez": "India", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026061",
        "confidence": 94, "category": "Normal Vessel", "comment": None,
        "center_lat": 19.953, "center_lon": 71.681, "heading": 320,
        "vessel": ("Desh Bhakt", "419474000", "9232905", "India", "Crude Tanker", 244, False),
        "sec_vessel": None,
    },
    # 03 GULF-OF-KUTCH
    {
        "name": "GULF-OF-KUTCH INC-003", "spill_type": "Trailing Wake",
        "date": "2025-11-13T01:18:40Z", "date_display": "13 November 2025   01:18 UTC",
        "location": "Gulf of Kutch Approach",
        "area_km2": 4.2, "length_km": 23.0,
        "eez": "India", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025111",
        "confidence": 92, "category": "Normal Vessel", "comment": None,
        "center_lat": 22.628, "center_lon": 69.627, "heading": 90,
        "vessel": ("Yc Pansy", "441046000", "9311256", "Unknown", "Other", 150, False),
        "sec_vessel": None,
    },
    # 04 KARACHI-OFFING — 2 SHIPS (STS transfer / AIS dark event partner)
    {
        "name": "KARACHI-OFFING INC-004", "spill_type": "Trailing Wake",
        "date": "2026-02-27T01:34:34Z", "date_display": "27 February 2026   01:34 UTC",
        "location": "North Arabian Sea / Pakistan Offing",
        "area_km2": 14.3, "length_km": 53.0,
        "eez": "Pakistan", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026022",
        "confidence": 96, "category": "Normal Vessel",
        "comment": "3 AIS off events recorded. Coincident vessel detected in proximity during discharge window.",
        "center_lat": 24.032, "center_lon": 64.742, "heading": 245,
        "vessel": ("Maritime Comity", "563108600", "9848326", "China", "Other", 150, False),
        "sec_vessel": ("Euphrates River", "431010550", "9134876",
                       "Marshall Islands", "Chemical Tanker", 155,
                       -0.04, 0.02, 250),
    },
    # 05 LACCADIVE
    {
        "name": "LACCADIVE INC-005", "spill_type": "Trailing Wake",
        "date": "2026-06-21T00:49:06Z", "date_display": "21 June 2026   00:49 UTC",
        "location": "Laccadive Sea / Kerala Coast",
        "area_km2": 9.2, "length_km": 48.0,
        "eez": "India", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026062",
        "confidence": 93, "category": "Normal Vessel", "comment": None,
        "center_lat": 10.582, "center_lon": 75.125, "heading": 140,
        "vessel": ("Bass", "538009014", "9885908", "China", "Other", 150, False),
        "sec_vessel": None,
    },
    # 06 ANDHRA
    {
        "name": "ANDHRA INC-006", "spill_type": "Trailing Wake",
        "date": "2025-12-20T00:22:49Z", "date_display": "20 December 2025   00:22 UTC",
        "location": "Bay of Bengal / Andhra Coast",
        "area_km2": 6.8, "length_km": 22.0,
        "eez": "India", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025122",
        "confidence": 95, "category": "Normal Vessel", "comment": "Tagged: Sanctioned",
        "center_lat": 16.631, "center_lon": 82.836, "heading": 20,
        "vessel": ("Shiva", "518998181", "9427146", "Cook Islands", "Other", 150, False),
        "sec_vessel": None,
    },
    # 07 SRI-LANKA — 2 SHIPS (existing from provided data)
    {
        "name": "SRI-LANKA INC-007", "spill_type": "Trailing Wake",
        "date": "2026-05-18T00:00:00Z", "date_display": "18 May 2026   00:00 UTC",
        "location": "Southern Sri Lanka TSS Lane",
        "area_km2": 23.0, "length_km": 42.0,
        "eez": "Sri Lanka", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_PASS",
        "confidence": 97, "category": "Normal Vessel",
        "comment": "Multi-vessel corridor incident (2 vessels coincident with slick footprint)",
        "center_lat": 5.850, "center_lon": 80.520, "heading": 130,
        "vessel": ("One Milano", "371076000", "9757187", "Panama", "Cargo", 175, False),
        "sec_vessel": ("Navios Coral", "354552000", "9774264",
                       "Panama", "Cargo", 175,
                       0.04, 0.05, 135),
    },
    # 08 MID-ATLANTIC
    {
        "name": "MID-ATLANTIC INC-008", "spill_type": "Trailing Wake",
        "date": "2026-07-31T22:49:48Z", "date_display": "31 July 2026   22:49 UTC",
        "location": "US East Coast / Mid-Atlantic Bight",
        "area_km2": 7.7, "length_km": 59.0,
        "eez": "United States", "status": "Confirmed",
        "satellite": "Sentinel-1D", "orbit_pass": "S1D_IW_GRDH_1SDV_2026073",
        "confidence": 94, "category": "Normal Vessel", "comment": None,
        "center_lat": 37.990, "center_lon": -74.480, "heading": 45,
        "vessel": ("Cma Cgm Louga", "248655000", "9745550", "Malta", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 09 CELTIC-SEA — 2 SHIPS (Bay of Biscay corridor, added)
    {
        "name": "CELTIC-SEA INC-009", "spill_type": "Trailing Wake",
        "date": "2026-08-25T06:39:53Z", "date_display": "25 August 2026   06:39 UTC",
        "location": "Bay of Biscay / French Atlantic Slope",
        "area_km2": 13.9, "length_km": 44.0,
        "eez": "France", "status": "Confirmed",
        "satellite": "Sentinel-1C", "orbit_pass": "S1C_IW_GRDH_1SDV_2026082",
        "confidence": 93, "category": "Normal Vessel",
        "comment": "Two vessels detected coincident with slick footprint in Atlantic outbound lane.",
        "center_lat": 47.547, "center_lon": -6.914, "heading": 250,
        "vessel": ("Clyde", "314001065", "9298416", "Unknown", "Other", 150, False),
        "sec_vessel": ("Cap Lopez", "228338800", "9308786",
                       "France", "Cargo", 180,
                       0.025, -0.015, 245),
    },
    # 10 NORTH-SEA
    {
        "name": "NORTH-SEA INC-010", "spill_type": "Trailing Wake",
        "date": "2026-08-18T05:57:07Z", "date_display": "18 August 2026   05:57 UTC",
        "location": "German Bight / North Sea Corridor",
        "area_km2": 0.4, "length_km": 4.0,
        "eez": "Germany", "status": "Confirmed",
        "satellite": "Sentinel-1D", "orbit_pass": "S1D_IW_GRDH_1SDV_2026081",
        "confidence": 92, "category": "Normal Vessel", "comment": None,
        "center_lat": 55.109, "center_lon": 5.282, "heading": 320,
        "vessel": ("Andrea", "219031446", "9428188", "Denmark", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 11 BALTIC-SEA
    {
        "name": "BALTIC-SEA INC-011", "spill_type": "Trailing Wake",
        "date": "2024-05-30T04:59:45Z", "date_display": "30 May 2024   04:59 UTC",
        "location": "Central Baltic Sea / Swedish Waters",
        "area_km2": 4.5, "length_km": 51.0,
        "eez": "Sweden", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2024053",
        "confidence": 95, "category": "Normal Vessel", "comment": "1 AIS off event recorded",
        "center_lat": 57.477, "center_lon": 19.421, "heading": 70,
        "vessel": ("Rinia", "256308000", "9594406", "Malta", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 12 HOKKAIDO
    {
        "name": "HOKKAIDO INC-012", "spill_type": "Trailing Wake",
        "date": "2024-07-30T20:33:33Z", "date_display": "30 July 2024   20:33 UTC",
        "location": "Tsugaru Strait / Northern Japan Offing",
        "area_km2": 4.7, "length_km": 65.0,
        "eez": "Japan", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2024073",
        "confidence": 96, "category": "Normal Vessel", "comment": "1 AIS off event recorded",
        "center_lat": 41.563, "center_lon": 142.156, "heading": 210,
        "vessel": ("Fuga", "373680000", "9624615", "Panama", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 13 ALASKA-COAST
    {
        "name": "ALASKA-COAST INC-013", "spill_type": "Trailing Wake",
        "date": "2024-09-10T02:54:23Z", "date_display": "10 September 2024   02:54 UTC",
        "location": "Gulf of Alaska / Alexander Archipelago",
        "area_km2": 2.0, "length_km": 36.0,
        "eez": "United States (Alaska)", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2024091",
        "confidence": 95, "category": "Normal Vessel", "comment": "1 AIS off event recorded",
        "center_lat": 56.613, "center_lon": -135.642, "heading": 115,
        "vessel": ("Crown Princess", "310500000", "9293399", "Bermuda", "Passenger", 290, False),
        "sec_vessel": None,
    },
    # 14 IRAN-OFFSHORE
    {
        "name": "IRAN-OFFSHORE INC-014", "spill_type": "Trailing Wake",
        "date": "2024-09-28T02:31:29Z", "date_display": "28 September 2024   02:31 UTC",
        "location": "Persian Gulf / Iranian Offing",
        "area_km2": 26.6, "length_km": 80.0,
        "eez": "Iran", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2024092",
        "confidence": 97, "category": "Normal Vessel", "comment": None,
        "center_lat": 27.346, "center_lon": 51.853, "heading": 125,
        "vessel": ("Samanta", "341107001", "9000297", "St. Kitts & Nevis", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 15 RED-SEA
    {
        "name": "RED-SEA INC-015", "spill_type": "Trailing Wake",
        "date": "2026-03-30T15:38:59Z", "date_display": "30 March 2026   15:38 UTC",
        "location": "Northern Red Sea / Egyptian Waters",
        "area_km2": 8.5, "length_km": 10.0,
        "eez": "Egypt", "status": "Confirmed",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026033",
        "confidence": 93, "category": "Normal Vessel", "comment": "1 AIS off event recorded",
        "center_lat": 25.622, "center_lon": 35.621, "heading": 340,
        "vessel": ("Saga", "248964000", "9528031", "Malta", "Other", 150, False),
        "sec_vessel": None,
    },
    # 16 COROMANDEL-DARK
    {
        "name": "COROMANDEL-DARK INC-016", "spill_type": "Trailing Wake",
        "date": "2026-08-05T00:31:49Z", "date_display": "05 August 2026   00:31 UTC",
        "location": "Coromandel Coast / Palk Strait Offing",
        "area_km2": 0.4, "length_km": 4.0,
        "eez": "India", "status": "Under Investigation",
        "satellite": "Sentinel-1D", "orbit_pass": "S1D_IW_GRDH_1SDV_2026080",
        "confidence": 91, "category": "Dark Vessel",
        "comment": "Unidentified non-broadcasting radar contact detected via SAR backscatter",
        "center_lat": 10.922, "center_lon": 79.958, "heading": 95,
        "vessel": ("DARK VESSEL #D148.068375", "D148.068375", "UNKNOWN",
                   "Non-Broadcasting", "Dark Vessel", 150, True),
        "sec_vessel": None,
    },
    # 17 BENGAL-DARK
    {
        "name": "BENGAL-DARK INC-017", "spill_type": "Trailing Wake",
        "date": "2026-01-21T23:56:55Z", "date_display": "21 January 2026   23:56 UTC",
        "location": "North Bay of Bengal / Offshore West Bengal",
        "area_km2": 25.5, "length_km": 92.0,
        "eez": "India", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026012",
        "confidence": 92, "category": "Dark Vessel",
        "comment": "Vessel position at 19.988, 89.211 with length ~140m",
        "center_lat": 20.281, "center_lon": 88.932, "heading": 185,
        "vessel": ("DARK VESSEL #D137.062241", "D137.062241", "UNKNOWN",
                   "Non-Broadcasting", "Dark Vessel", 140, True),
        "sec_vessel": None,
    },
    # 18 HORMUZ-DARK
    {
        "name": "HORMUZ-DARK INC-018", "spill_type": "Trailing Wake",
        "date": "2025-10-14T02:07:29Z", "date_display": "14 October 2025   02:07 UTC",
        "location": "Gulf of Oman / Iranian EEZ Approach",
        "area_km2": 7.1, "length_km": 11.0,
        "eez": "Iran", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025101",
        "confidence": 90, "category": "Dark Vessel",
        "comment": "Vessel position at 24.933, 57.630 with length ~80m",
        "center_lat": 24.843, "center_lon": 57.615, "heading": 275,
        "vessel": ("DARK VESSEL #D80.7133179", "D80.7133179", "UNKNOWN",
                   "Non-Broadcasting", "Dark Vessel", 80, True),
        "sec_vessel": None,
    },
    # 19 CAMPECHE-DARK
    {
        "name": "CAMPECHE-DARK INC-019", "spill_type": "Wind-Drift Pool",
        "date": "2025-10-17T00:15:47Z", "date_display": "17 October 2025   00:15 UTC",
        "location": "Bay of Campeche / Gulf of Mexico",
        "area_km2": 26.3, "length_km": 23.0,
        "eez": "Mexico", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025101",
        "confidence": 88, "category": "Dark Vessel",
        "comment": "Occurs in known natural seep area. Vessel position at 19.438, -92.061 with length ~380m",
        "center_lat": 19.407, "center_lon": -92.043, "heading": 50,
        "vessel": ("DARK VESSEL #D379.082062", "D379.082062", "UNKNOWN",
                   "Non-Broadcasting", "Dark Vessel", 380, True),
        "sec_vessel": None,
    },
    # 20 BONNY-DARK
    {
        "name": "BONNY-DARK INC-020", "spill_type": "Trailing Wake",
        "date": "2026-01-13T17:45:03Z", "date_display": "13 January 2026   17:45 UTC",
        "location": "Gulf of Guinea / Niger Delta Offshore",
        "area_km2": 0.5, "length_km": 5.0,
        "eez": "Nigeria", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026011",
        "confidence": 91, "category": "Dark Vessel",
        "comment": "Vessel position at 4.302, 7.659 with length ~400m",
        "center_lat": 4.324, "center_lon": 7.677, "heading": 195,
        "vessel": ("DARK VESSEL #D396.112183", "D396.112183", "UNKNOWN",
                   "Non-Broadcasting", "Dark Vessel", 400, True),
        "sec_vessel": None,
    },
    # 21 BLACK-SEA
    {
        "name": "BLACK-SEA INC-021", "spill_type": "Trailing Wake",
        "date": "2025-03-13T15:27:46Z", "date_display": "13 March 2025   15:27 UTC",
        "location": "Black Sea / Overlapping Claim Ukrainian EEZ",
        "area_km2": 3.1, "length_km": 14.0,
        "eez": "Overlapping claim Ukrainian", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025031",
        "confidence": 48, "category": "Low Confidence",
        "comment": "Low confidence: Potential source without verified match link. Overlapping maritime claim zone.",
        "center_lat": 43.893, "center_lon": 35.941, "heading": 55,
        "vessel": ("Apache", "636022467", "8955586", "Liberia", "Cargo", 175, False),
        "sec_vessel": None,
    },
    # 22 BERING-SEA
    {
        "name": "BERING-SEA INC-022", "spill_type": "Trailing Wake",
        "date": "2025-10-18T06:04:55Z", "date_display": "18 October 2025   06:04 UTC",
        "location": "Bering Sea / Russian Far East Offing",
        "area_km2": 0.4, "length_km": 3.0,
        "eez": "Russia", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2025101",
        "confidence": 42, "category": "Low Confidence",
        "comment": "Low confidence: No strong slick-source matches. Link between the slick and the source is relatively weak.",
        "center_lat": 60.930, "center_lon": 173.998, "heading": 265,
        "vessel": ("Alexandr Belyakov", "273825210", "8721260", "Russia", "Fishing", 65, False),
        "sec_vessel": None,
    },
    # 23 OREGON
    {
        "name": "OREGON INC-023", "spill_type": "Trailing Wake",
        "date": "2026-02-05T14:22:25Z", "date_display": "05 February 2026   14:22 UTC",
        "location": "Pacific Coast / Oregon Marine Sanctuary Limits",
        "area_km2": 8.7, "length_km": 13.0,
        "eez": "United States", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2026020",
        "confidence": 45, "category": "Low Confidence",
        "comment": "Low confidence: No strong slick-source matches. Link between the slick and the source is relatively weak.",
        "center_lat": 45.031, "center_lon": -124.120, "heading": 205,
        "vessel": ("Eddie & Rod", "367586950", "7047801", "United States", "Fishing", 65, False),
        "sec_vessel": None,
    },
    # 24 CHUKCHI-SEA
    {
        "name": "CHUKCHI-SEA INC-024", "spill_type": "Trailing Wake",
        "date": "2024-09-17T17:49:45Z", "date_display": "17 September 2024   17:49 UTC",
        "location": "Arctic / Chukchi Sea Russian Border",
        "area_km2": 4.1, "length_km": 12.0,
        "eez": "Russia", "status": "Under Investigation",
        "satellite": "Sentinel-1A", "orbit_pass": "S1A_IW_GRDH_1SDV_2024091",
        "confidence": 40, "category": "Low Confidence",
        "comment": "Low confidence: No strong slick-source matches. Link between the slick and the source is relatively weak. 1 AIS off event.",
        "center_lat": 69.321, "center_lon": -171.040, "heading": 85,
        "vessel": ("Seawind-1", "273426670", "8721143", "Russia", "Fishing", 65, False),
        "sec_vessel": None,
    },
    # 25 NEW-ZEALAND
    {
        "name": "NEW-ZEALAND INC-025", "spill_type": "Trailing Wake",
        "date": "2026-05-08T07:37:23Z", "date_display": "08 May 2026   07:37 UTC",
        "location": "South Pacific / Offshore South Island New Zealand",
        "area_km2": 5.3, "length_km": 27.0,
        "eez": "New Zealand", "status": "Under Investigation",
        "satellite": "Sentinel-1D", "orbit_pass": "S1D_IW_GRDH_1SDV_2026050",
        "confidence": 44, "category": "Low Confidence",
        "comment": "Low confidence: No strong slick-source matches. Link between the slick and the source is relatively weak. 1 AIS off event.",
        "center_lat": -46.010, "center_lon": 170.970, "heading": 310,
        "vessel": ("Pacinui", "512430000", "8319770", "New Zealand", "Fishing", 65, False),
        "sec_vessel": None,
    },
]

# ── Seed ──────────────────────────────────────────────────────────────────────
db = SessionLocal()

for item in INCIDENTS:
    lon        = item["center_lon"]
    lat        = item["center_lat"]
    heading    = item["heading"]
    length_km  = item["length_km"]
    is_dark    = item["vessel"][6]
    spill_type = item["spill_type"]

    # Generate geometry
    if spill_type == "Wind-Drift Pool":
        track, poly, ship_lon, ship_lat = make_wind_drift_pool(lon, lat, heading, length_km)
    else:
        track, poly, ship_lon, ship_lat = make_trailing_wake(lon, lat, heading, length_km)

    poly_wkt  = f"SRID=4326;{poly.wkt}"
    track_wkt = None if is_dark else f"SRID=4326;{track.wkt}"

    # Primary vessel
    v_name, v_mmsi, v_imo, v_flag, v_type, v_len, v_dark = item["vessel"]
    primary_vessel = Vessel(
        name=v_name, mmsi=v_mmsi, imo=v_imo, flag=v_flag,
        vessel_type=v_type, length_m=v_len, is_dark=v_dark
    )
    db.add(primary_vessel)
    db.flush()

    # Secondary vessel
    sec_vessel_id  = None
    sec_track_wkt  = None
    sec_ship_lon   = None
    sec_ship_lat   = None

    if item["sec_vessel"] is not None:
        sv = item["sec_vessel"]
        sv_name, sv_mmsi, sv_imo, sv_flag, sv_type, sv_len, d_lon, d_lat, s_heading = sv
        sec_vessel_obj = Vessel(
            name=sv_name, mmsi=sv_mmsi, imo=sv_imo, flag=sv_flag,
            vessel_type=sv_type, length_m=sv_len, is_dark=False
        )
        db.add(sec_vessel_obj)
        db.flush()
        sec_vessel_id = sec_vessel_obj.id
        sec_track, sec_ship_lon, sec_ship_lat = make_secondary_track(
            ship_lon, ship_lat, d_lon, d_lat, s_heading
        )
        sec_track_wkt = f"SRID=4326;{sec_track.wkt}"

    incident = Incident(
        vessel_id=primary_vessel.id,
        secondary_vessel_id=sec_vessel_id,
        name=item["name"],
        spill_type=item["spill_type"],
        date=item["date"],
        date_display=item["date_display"],
        location=item["location"],
        area_km2=item["area_km2"],
        length_km=item["length_km"],
        eez=item["eez"],
        status=item["status"],
        satellite=item["satellite"],
        orbit_pass=item["orbit_pass"],
        confidence=item["confidence"],
        category=item["category"],
        comment=item["comment"],
    )
    db.add(incident)
    db.flush()

    spatial = SpatialData(
        incident_id=incident.id,
        geometry=poly_wkt,
        ship_track=track_wkt,
        secondary_ship_track=sec_track_wkt,
        center_lon=lon,
        center_lat=lat,
        ship_pos_lon=ship_lon,
        ship_pos_lat=ship_lat,
        secondary_ship_pos_lon=sec_ship_lon,
        secondary_ship_pos_lat=sec_ship_lat,
    )
    db.add(spatial)
    print(f"  [OK] {item['name']}")

db.commit()
db.close()
print("\nSuccess: hogaya bhai - all 25 incidents seeded with exact data.")