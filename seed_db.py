import random
import math
from datetime import datetime, timedelta, timezone
from shapely.geometry import Point, LineString, Polygon
from database import SessionLocal, Vessel, Incident, SpatialData, Base, engine

print("Resetting database tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def make_trailing_wake(lon: float, lat: float, heading_deg: float, length_km: float):
    rad = math.radians(heading_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    nx, ny = -uy, ux
    
    len_deg = length_km / 111.0
    half_l = len_deg * 0.5
    ship_lon = lon + half_l * ux
    ship_lat = lat + half_l * uy
    
    w_start = (lon - half_l * ux, lat - half_l * uy)
    w_mid1  = (lon - half_l * 0.35 * ux + 0.004 * nx, lat - half_l * 0.35 * uy + 0.004 * ny)
    w_mid2  = (lon + half_l * 0.35 * ux - 0.002 * nx, lat + half_l * 0.35 * uy - 0.002 * ny)
    w_ship  = (ship_lon, ship_lat)
    track = LineString([w_start, w_mid1, w_mid2, w_ship])
    
    w_head = (ship_lon - 0.015 * ux, ship_lat - 0.015 * uy)
    tail_w = random.uniform(0.012, 0.018)
    mid_w  = tail_w * 0.65
    head_w = 0.0035
    
    p_tail_tip = (w_start[0] - 0.01 * ux, w_start[1] - 0.01 * uy)
    p_tail_l   = (w_start[0] + tail_w * nx, w_start[1] + tail_w * ny)
    p_mid_l    = (lon + mid_w * nx, lat + mid_w * ny)
    p_head_l   = (w_head[0] + head_w * nx, w_head[1] + head_w * ny)
    p_head_r   = (w_head[0] - head_w * nx, w_head[1] - head_w * ny)
    p_mid_r    = (lon - mid_w * nx, lat - mid_w * ny)
    p_tail_r   = (w_start[0] - tail_w * nx, w_start[1] - tail_w * ny)
    
    poly = Polygon([p_tail_tip, p_tail_l, p_mid_l, p_head_l, w_head, p_head_r, p_mid_r, p_tail_r, p_tail_tip]).buffer(0.002)
    return track, poly, ship_lon, ship_lat

def make_wind_drift_pool(lon: float, lat: float, heading_deg: float, length_km: float):
    rad = math.radians(heading_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    nx, ny = -uy, ux
    
    len_deg = length_km / 111.0
    half_l = len_deg * 0.5
    ship_lon = lon + half_l * ux
    ship_lat = lat + half_l * uy
    
    # Vessel track continues along its corridor
    w_start = (lon - half_l * ux, lat - half_l * uy)
    w_ship  = (ship_lon, ship_lat)
    track = LineString([w_start, (lon, lat), w_ship])
    
    # Slick has been sheared and drifted away from the track by crosswind/current
    drift_angle = rad + random.choice([1.3, -1.3])
    drift_dist = random.uniform(0.025, 0.04) # ~3-5 km downwind
    pool_cx = lon + math.sin(drift_angle) * drift_dist
    pool_cy = lat + math.cos(drift_angle) * drift_dist
    
    # Irregular amorphous pooling cloud if there is any aise toh hota nahi 
    pts = []
    num_pts = 16
    r_base = random.uniform(0.022, 0.038)
    for i in range(num_pts):
        ang = (2 * math.pi * i) / num_pts
        r = r_base * (1.0 + 0.32 * math.sin(3 * ang) + 0.18 * math.cos(2 * ang))
        pts.append((pool_cx + r * math.cos(ang) * 1.3, pool_cy + r * math.sin(ang) * 0.85))
    pts.append(pts[0])
    poly = Polygon(pts).buffer(0.0025)
    return track, poly, ship_lon, ship_lat

def make_anchorage_pool(lon: float, lat: float, heading_deg: float):
    # Stationary orr anchored ship has minimal swing movement
    rad = math.radians(heading_deg)
    ux, uy = math.sin(rad), math.cos(rad)
    
    ship_lon = lon + 0.004 * ux
    ship_lat = lat + 0.004 * uy
    track = LineString([(lon - 0.006 * ux, lat - 0.006 * uy), (lon, lat), (ship_lon, ship_lat)])
    
    # Concentrated spreading circular/elliptical pool around vessel
    pts = []
    num_pts = 16
    r_base = random.uniform(0.018, 0.03)
    for i in range(num_pts):
        ang = (2 * math.pi * i) / num_pts
        r = r_base * (1.0 + 0.25 * math.sin(2 * ang) + 0.12 * math.cos(4 * ang))
        pts.append((lon + r * math.cos(ang) * 1.1, lat + r * math.sin(ang) * 0.95))
    pts.append(pts[0])
    poly = Polygon(pts).buffer(0.002)
    return track, poly, ship_lon, ship_lat

# Configuration of all 25 incidents with morphology types, dark ship status, and secondary vessels
LOCATIONS = [
    # 01: Mumbai High - 2 SHIPS (Crude Tanker + OSV Support Vessel)
    {
        "loc": "Mumbai High Offshore", "eez": "Indian EEZ", "lat": 19.35, "lon": 71.35,
        "heading": 325, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Swarna Godavari", "Crude Tanker", "India", "322418569", "9054400", 240),
        "sec_vessel": ("OSV Garware Pride", "Offshore Supply Vessel", "India", "419000214", "9412030", 72, -0.04, 0.03, 310)
    },
    # 02: JNPT Approach - 2 SHIPS (Container ship + Harbour Tug)
    {
        "loc": "JNPT Approach Channel", "eez": "Indian Territorial Waters", "lat": 18.85, "lon": 72.50,
        "heading": 75, "type": "Wind-Drift Pool", "dark": False,
        "vessel": ("MV MSC Mumbai", "Container", "Liberia", "636018920", "9720445", 295),
        "sec_vessel": ("Tug Jawahar-II", "Tug / Pilot Vessel", "India", "419001880", "9201402", 34, 0.02, -0.02, 80)
    },
    # 03: Ratnagiri Coastal Offing - DARK VESSEL (Illegal bilge discharge with transponder switched off)
    {
        "loc": "Ratnagiri Coastal Offing", "eez": "Indian EEZ", "lat": 16.98, "lon": 72.95,
        "heading": 165, "type": "Trailing Wake", "dark": True,
        "vessel": ("UNIDENTIFIED TANKER (SAR TARGET)", "Chemical Tanker", "Non-Broadcasting", "[AIS SILENT]", "UNKNOWN", 185),
        "sec_vessel": None
    },
    # 04: Sindhudurg - Trailing Wake
    {
        "loc": "Sindhudurg Marine Zone", "eez": "Indian EEZ", "lat": 16.15, "lon": 73.18,
        "heading": 345, "type": "Trailing Wake", "dark": False,
        "vessel": ("MV Konkan Pearl", "Bulk Carrier", "Marshall Islands", "538004120", "9488112", 225),
        "sec_vessel": None
    },
    # 05: Tarapur Offshore - Anchorage / Mooring Pool
    {
        "loc": "Tarapur Offshore", "eez": "Indian EEZ", "lat": 19.82, "lon": 72.35,
        "heading": 190, "type": "Anchorage Pool", "dark": False,
        "vessel": ("MT Desh Bhakta", "Crude Tanker", "India", "419000551", "9251800", 244),
        "sec_vessel": None
    },
    # 06: Alibaug Coastal Limits - Wind Drift Pool
    {
        "loc": "Alibaug Coastal Limits", "eez": "Indian Territorial Waters", "lat": 18.60, "lon": 72.75,
        "heading": 280, "type": "Wind-Drift Pool", "dark": False,
        "vessel": ("MV Alibaug Express", "Cargo", "India", "419000882", "9301244", 135),
        "sec_vessel": None
    },
    # 07: Vasai-Virar Offing - Trailing Wake
    {
        "loc": "Vasai-Virar Offing", "eez": "Indian EEZ", "lat": 19.38, "lon": 72.58,
        "heading": 215, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Surya", "Oil Products Tanker", "Panama", "354112000", "9192800", 175),
        "sec_vessel": None
    },
    # 08: Murud-Janjira Approach - Anchorage Pool
    {
        "loc": "Murud-Janjira Approach", "eez": "Indian EEZ", "lat": 18.32, "lon": 72.80,
        "heading": 150, "type": "Anchorage Pool", "dark": False,
        "vessel": ("MV Sea Fortune", "Cargo", "Liberia", "636091220", "9445100", 160),
        "sec_vessel": None
    },
    # 09: Gulf of Khambhat - Trailing Wake
    {
        "loc": "Gulf of Khambhat", "eez": "Indian EEZ", "lat": 20.55, "lon": 72.05,
        "heading": 25, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Gujarat Glory", "Crude Tanker", "India", "419000780", "9277410", 250),
        "sec_vessel": None
    },
    # 10: Goa Maritime Boundary - DARK VESSEL (Unlicensed iron ore bulk carrier operating dark)
    {
        "loc": "Goa Maritime Boundary", "eez": "Indian EEZ", "lat": 15.52, "lon": 73.45,
        "heading": 250, "type": "Wind-Drift Pool", "dark": True,
        "vessel": ("DARK BULK CARRIER #7741", "Bulk Carrier", "Non-Broadcasting", "[AIS SILENT]", "UNKNOWN", 190),
        "sec_vessel": None
    },
    # 11: Mangalore Port Limits - Anchorage Pool
    {
        "loc": "Mangalore Port Limits", "eez": "Indian Territorial Waters", "lat": 12.85, "lon": 74.65,
        "heading": 105, "type": "Anchorage Pool", "dark": False,
        "vessel": ("MT Nethravathi", "Chemical Tanker", "India", "419000910", "9321550", 145),
        "sec_vessel": None
    },
    # 12: Kochi Offshore Basin - Trailing Wake
    {
        "loc": "Kochi Offshore Basin", "eez": "Indian EEZ", "lat": 9.95, "lon": 75.92,
        "heading": 135, "type": "Trailing Wake", "dark": False,
        "vessel": ("MV Kerala Star", "Container", "Panama", "371004550", "9644020", 280),
        "sec_vessel": None
    },
    # 13: Chennai Coastal Zone - Trailing Wake
    {
        "loc": "Chennai Coastal Zone", "eez": "Indian EEZ", "lat": 13.15, "lon": 80.45,
        "heading": 15, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Coromandel", "Crude Tanker", "India", "419000620", "9288100", 235),
        "sec_vessel": None
    },
    # 14: Visakhapatnam Offing - Wind Drift Pool
    {
        "loc": "Visakhapatnam Offing", "eez": "Indian EEZ", "lat": 17.65, "lon": 83.48,
        "heading": 50, "type": "Wind-Drift Pool", "dark": False,
        "vessel": ("MV Vizag Pride", "Cargo", "India", "419001150", "9411900", 170),
        "sec_vessel": None
    },
    # 15: Gulf of Kutch - Anchorage / Single Point Mooring Pool
    {
        "loc": "Gulf of Kutch", "eez": "Indian EEZ", "lat": 22.55, "lon": 69.05,
        "heading": 85, "type": "Anchorage Pool", "dark": False,
        "vessel": ("MT Kutch Energy", "Oil Products Tanker", "Marshall Islands", "538006120", "9512300", 210),
        "sec_vessel": None
    },
    # 16: Gulf of Mexico - Louisiana - Trailing Wake
    {
        "loc": "Gulf of Mexico - Louisiana", "eez": "US EEZ", "lat": 28.55, "lon": -90.05,
        "heading": 145, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Pelican State", "Crude Tanker", "USA", "367112040", "9455110", 260),
        "sec_vessel": None
    },
    # 17: Gulf of Mexico - Texas - Wind Drift Pool
    {
        "loc": "Gulf of Mexico - Texas", "eez": "US EEZ", "lat": 27.85, "lon": -93.55,
        "heading": 70, "type": "Wind-Drift Pool", "dark": False,
        "vessel": ("MV Lone Star", "Bulk Carrier", "Panama", "355001220", "9399810", 215),
        "sec_vessel": None
    },
    # 18: Galveston Bay - 2 SHIPS (Ship-to-Ship STS Bunkering Operation)
    {
        "loc": "Galveston Bay Approach", "eez": "US Territorial Waters", "lat": 29.15, "lon": -94.65,
        "heading": 315, "type": "Anchorage Pool", "dark": False,
        "vessel": ("MT Houston Pride", "Chemical Tanker", "Marshall Islands", "538008890", "9412550", 182),
        "sec_vessel": ("Bunker Delta", "Bunkering Barge", "USA", "367009410", "8902140", 65, 0.015, 0.01, 310)
    },
    # 19: Santa Barbara Channel - Trailing Wake
    {
        "loc": "Santa Barbara Channel", "eez": "US EEZ", "lat": 34.25, "lon": -120.15,
        "heading": 120, "type": "Trailing Wake", "dark": False,
        "vessel": ("MV Pacific Trader", "Cargo", "Liberia", "636017840", "9655100", 220),
        "sec_vessel": None
    },
    # 20: Prince William Sound - Trailing Wake
    {
        "loc": "Prince William Sound", "eez": "US Territorial Waters", "lat": 60.65, "lon": -147.05,
        "heading": 210, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Valdez Spirit", "Crude Tanker", "USA", "366992140", "9188400", 270),
        "sec_vessel": None
    },
    # 21: Strait of Hormuz - 2 SHIPS (Congested Corridor with crossing VLCC Tankers)
    {
        "loc": "Strait of Hormuz", "eez": "Oman EEZ", "lat": 26.55, "lon": 56.25,
        "heading": 125, "type": "Trailing Wake", "dark": False,
        "vessel": ("MT Gulf Horizon", "Crude Tanker", "Panama", "352001920", "9388100", 333),
        "sec_vessel": ("MT Persian Star", "Oil Products Tanker", "Liberia", "636019910", "9541200", 228, -0.05, -0.04, 130)
    },
    # 22: Malacca Strait - 2 SHIPS (Congested TSS lane with overtaking container ships)
    {
        "loc": "Malacca Strait", "eez": "Malaysia EEZ", "lat": 2.55, "lon": 101.55,
        "heading": 130, "type": "Trailing Wake", "dark": False,
        "vessel": ("MV Asian Pearl", "Container", "Singapore", "563004810", "9812400", 366),
        "sec_vessel": ("MV Evergreen Glory", "Container", "Panama", "351009840", "9781400", 300, 0.04, 0.05, 135)
    },
    # 23: English Channel - Wind Drift Pool
    {
        "loc": "English Channel", "eez": "UK EEZ", "lat": 50.15, "lon": -1.05,
        "heading": 245, "type": "Wind-Drift Pool", "dark": False,
        "vessel": ("MT Channel Navigator", "Chemical Tanker", "Marshall Islands", "538009140", "9415800", 178),
        "sec_vessel": None
    },
    # 24: Niger Delta Offshore - DARK VESSEL (Sanction evasion / bunkering with AIS transponder off)
    {
        "loc": "Niger Delta Offshore", "eez": "Nigeria EEZ", "lat": 4.15, "lon": 5.55,
        "heading": 205, "type": "Trailing Wake", "dark": True,
        "vessel": ("GHOST TANKER DELTA-9", "Crude Tanker", "Non-Broadcasting", "[AIS SILENT]", "UNKNOWN", 240),
        "sec_vessel": None
    },
    # 25: Mediterranean Sea - DARK VESSEL (Unflagged vessel off Libyan coast)
    {
        "loc": "Mediterranean Sea", "eez": "Libya EEZ", "lat": 33.25, "lon": 13.25,
        "heading": 310, "type": "Wind-Drift Pool", "dark": True,
        "vessel": ("UNIDENTIFIED CARGO (RADAR TARGET)", "Cargo", "Non-Broadcasting", "[AIS SILENT]", "UNKNOWN", 165),
        "sec_vessel": None
    }
]

db = SessionLocal()

for idx, item in enumerate(LOCATIONS, start=1):
    sim_date = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 60))
    length_km = round(random.uniform(15.0, 52.0), 1)
    area_km2 = round(random.uniform(10.5, 45.0), 1)
    
    lon, lat = item["lon"], item["lat"]
    heading = item["heading"]
    spill_type = item["type"]
    is_dark = item["dark"]
    
    # geometry according to  thaaa  spill type
    if spill_type == "Trailing Wake":
        track, poly, ship_lon, ship_lat = make_trailing_wake(lon, lat, heading, length_km)
    elif spill_type == "Wind-Drift Pool":
        track, poly, ship_lon, ship_lat = make_trailing_wake(lon, lat, heading, length_km)
    else: # Anchorage Pool (ek hi jagha pe hai vo spill)
        track, poly, ship_lon, ship_lat = make_anchorage_pool(lon, lat, heading)
    
    poly_wkt = f"SRID=4326;{poly.wkt}"
    # If dark ship transponder track nahi kar payega
    track_wkt = None if is_dark else f"SRID=4326;{track.wkt}"

    # Primary vessel
    v_name, v_type, v_flag, v_mmsi, v_imo, v_len = item["vessel"]
    primary_vessel = Vessel(
        name=v_name, mmsi=v_mmsi, imo=v_imo, flag=v_flag,
        vessel_type=v_type, length_m=v_len, is_dark=is_dark
    )
    db.add(primary_vessel)
    db.flush()

    # Secondary vessel hai toh
    sec_vessel_id = None
    sec_track_wkt = None
    sec_ship_lon = None
    sec_ship_lat = None
    
    if item["sec_vessel"] is not None:
        sv_name, sv_type, sv_flag, sv_mmsi, sv_imo, sv_len, d_lon, d_lat, s_heading = item["sec_vessel"]
        sec_vessel_obj = Vessel(
            name=sv_name, mmsi=sv_mmsi, imo=sv_imo, flag=sv_flag,
            vessel_type=sv_type, length_m=sv_len, is_dark=False
        )
        db.add(sec_vessel_obj)
        db.flush()
        sec_vessel_id = sec_vessel_obj.id
        
        # Secondary vessel track karega
        sec_ship_lon = ship_lon + d_lon
        sec_ship_lat = ship_lat + d_lat
        s_rad = math.radians(s_heading)
        sec_track = LineString([
            (sec_ship_lon - 0.15 * math.sin(s_rad), sec_ship_lat - 0.15 * math.cos(s_rad)),
            (sec_ship_lon - 0.05 * math.sin(s_rad), sec_ship_lat - 0.05 * math.cos(s_rad)),
            (sec_ship_lon, sec_ship_lat)
        ])
        sec_track_wkt = f"SRID=4326;{sec_track.wkt}"

    incident = Incident(
        vessel_id=primary_vessel.id,
        secondary_vessel_id=sec_vessel_id,
        name=f"{item['loc'].split()[0].upper()} INC-{idx:03d}",
        spill_type=spill_type,
        date=sim_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        date_display=sim_date.strftime("%d %B %Y   %H:%M UTC"),
        location=item["loc"],
        area_km2=area_km2,
        length_km=length_km,
        eez=item["eez"],
        status=random.choice(["Confirmed", "Under Investigation"]),
        satellite=random.choice(["Sentinel-1A", "Sentinel-1B"]),
        orbit_pass=f"Pass #{random.randint(10000, 99999)}",
        confidence=random.randint(91, 98)
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
        secondary_ship_pos_lat=sec_ship_lat
    )
    db.add(spatial)

db.commit()
db.close()
print("Success: hogaya bhai")