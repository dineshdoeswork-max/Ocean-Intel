# drift_engine.py — Real-time Oil Spill Drift & Hindcast Engine
# Open-Meteo Marine + Weather APIs (free, no auth, no signup)
# Physics: U_total = U_current + (0.03 × U_wind), Coriolis ±20° by hemisphere

from __future__ import annotations

import json
import logging
import math
import urllib.request
from functools import lru_cache
from typing import List, Tuple

from shapely.affinity import translate
from shapely.geometry import Polygon, mapping

logger = logging.getLogger(__name__)

KM2_PER_DEG2 = 12_321.0  # (111 km/deg)^2


def _centroid_of(polygon_coords: list) -> Tuple[float, float]:
    """Return (lon, lat) centroid of a polygon coordinate list."""
    poly = Polygon(polygon_coords)
    return poly.centroid.x, poly.centroid.y


@lru_cache(maxsize=128)
def _fetch_openmeteo_feeds(round_lat: float, round_lon: float) -> Tuple[dict, dict]:
    """Dual Open-Meteo fetch: marine currents + 10m wind. Cached per ~11 km grid cell."""
    marine_url = (
        f"https://marine-api.open-meteo.com/v1/marine?"
        f"latitude={round_lat}&longitude={round_lon}&"
        f"hourly=ocean_current_velocity,ocean_current_direction"
    )
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={round_lat}&longitude={round_lon}&"
        f"hourly=windspeed_10m,winddirection_10m"
    )
    headers = {"User-Agent": "MiniCerulean-DriftEngine/2.0"}

    try:
        req_m = urllib.request.Request(marine_url, headers=headers)
        with urllib.request.urlopen(req_m, timeout=4) as resp_m:
            marine_data = json.loads(resp_m.read().decode())
    except Exception as exc:
        logger.warning("Marine API fetch failed for (%s, %s): %s", round_lat, round_lon, exc)
        marine_data = {}

    try:
        req_w = urllib.request.Request(weather_url, headers=headers)
        with urllib.request.urlopen(req_w, timeout=4) as resp_w:
            weather_data = json.loads(resp_w.read().decode())
    except Exception as exc:
        logger.warning("Weather API fetch failed for (%s, %s): %s", round_lat, round_lon, exc)
        weather_data = {}

    return marine_data.get("hourly", {}), weather_data.get("hourly", {})


def compute_hourly_drift_vector(
    lat: float, lon: float, hour_offset: int = 0
) -> Tuple[float, float, float, float, float, float]:
    """
    Returns total drift vector (u_x, u_y) in m/s plus raw metocean scalars.
    Formula: u = current_vector + 0.03 * wind_vector (Coriolis-rotated ±20°)
    Returns: (u_x, u_y, c_speed, c_dir, w_speed_ms, w_dir)
    """
    r_lat = round(lat, 1)
    r_lon = round(lon, 1)

    m_hourly, w_hourly = _fetch_openmeteo_feeds(r_lat, r_lon)

    c_vel_list = m_hourly.get("ocean_current_velocity", [])
    c_dir_list = m_hourly.get("ocean_current_direction", [])
    w_spd_list = w_hourly.get("windspeed_10m", [])
    w_dir_list = w_hourly.get("winddirection_10m", [])

    idx = min(max(0, hour_offset), len(c_vel_list) - 1) if c_vel_list else 0

    # Ocean current — velocity in m/s, direction in degrees
    c_speed = float(c_vel_list[idx]) if c_vel_list and c_vel_list[idx] is not None else 0.25
    c_dir   = float(c_dir_list[idx]) if c_dir_list and c_dir_list[idx] is not None else 45.0

    # Wind speed from Open-Meteo arrives as km/h — convert to m/s
    w_speed_ms = float(w_spd_list[idx]) / 3.6 if w_spd_list and w_spd_list[idx] is not None else 5.0
    w_dir      = float(w_dir_list[idx])        if w_dir_list and w_dir_list[idx] is not None else 225.0

    # 1. Ocean current vector
    c_rad = math.radians(c_dir)
    c_x = c_speed * math.sin(c_rad)
    c_y = c_speed * math.cos(c_rad)

    # 2. Wind leeway (3%) + Coriolis rotation (+20° NH, -20° SH)
    leeway_speed = 0.03 * w_speed_ms
    coriolis_deflection = 20.0 if lat >= 0 else -20.0
    drift_w_dir = (w_dir + coriolis_deflection) % 360.0

    w_rad = math.radians(drift_w_dir)
    w_x = leeway_speed * math.sin(w_rad)
    w_y = leeway_speed * math.cos(w_rad)

    u_x = c_x + w_x
    u_y = c_y + w_y

    return u_x, u_y, c_speed, c_dir, w_speed_ms, w_dir


# Dheere-dheere re mana, dheere sab kuchh hoy.
#             Maali seenche sau ghada, ritu aaye phal hoy.
def get_current_metocean(lat: float, lon: float) -> dict:
    """Returns structured ocean current + wind + net drift for a coordinate."""
    u_x, u_y, c_speed, c_dir, w_speed_ms, w_dir = compute_hourly_drift_vector(lat, lon, hour_offset=0)
    drift_speed = math.sqrt(u_x * u_x + u_y * u_y)
    drift_dir = (math.degrees(math.atan2(u_x, u_y)) + 360.0) % 360.0

    return {
        "ocean_current": {
            "velocity_ms": round(c_speed, 2),
            "velocity_knots": round(c_speed * 1.94384, 2),
            "direction_deg": round(c_dir, 1),
        },
        "wind": {
            "speed_ms": round(w_speed_ms, 2),
            "speed_kmh": round(w_speed_ms * 3.6, 1),
            "direction_deg": round(w_dir, 1),
        },
        "net_drift": {
            "speed_ms": round(drift_speed, 2),
            "speed_knots": round(drift_speed * 1.94384, 2),
            "direction_deg": round(drift_dir, 1),
        }
    }


def simulate_drift(
    polygon_coords: list,
    hours: list = None,
    mode: str = "forecast",
) -> List[dict]:
    """
    Integrates hourly drift vectors to translate the oil slick polygon forward
    (forecast) or backward (hindcast) in time.

    polygon_coords : list of (lon, lat) pairs
    hours          : forecast intervals in hours, default [24, 48]
    mode           : 'forecast' | 'hindcast'
    """
    if hours is None:
        hours = [24, 48]

    hours = sorted(set(hours))
    center_lon, center_lat = _centroid_of(polygon_coords)
    base_poly = Polygon(polygon_coords)

    sign = -1.0 if mode == "hindcast" else 1.0
    forecasts = []

    cumulative_dx = 0.0  # metres
    cumulative_dy = 0.0  # metres
    max_h = max(hours)
    step_displacements = {}

    for step in range(1, max_h + 1):
        ux, uy, _, _, _, _ = compute_hourly_drift_vector(
            center_lat, center_lon, hour_offset=step - 1
        )
        cumulative_dx += sign * ux * 3600.0
        cumulative_dy += sign * uy * 3600.0

        if step in hours:
            step_displacements[step] = (cumulative_dx, cumulative_dy)

    # Bura jo dekhan main chala, bura na miliya koy.
    #             Jo dil khoja aapna, mujhse bura na koy.
    for h in hours:
        dx, dy = step_displacements.get(h, (cumulative_dx, cumulative_dy))

        d_lat = dy / 111_320.0
        cos_lat = math.cos(math.radians(center_lat))
        d_lon = dx / (111_320.0 * (cos_lat if abs(cos_lat) > 0.01 else 1.0))

        shifted = translate(base_poly, xoff=d_lon, yoff=d_lat)

        # Turbulent diffusion — Fay's gravity-viscous spreading regime
        spread_deg = 0.005 * math.pow(h / 12.0, 0.6)
        diffused = shifted.buffer(spread_deg)

        area_growth = 1.0 + 0.16 * math.pow(h, 0.62)
        projected_area = round(base_poly.area * KM2_PER_DEG2 * area_growth, 2)

        mode_title = "Hindcast" if mode == "hindcast" else "Forecast"
        forecasts.append({
            "forecast_hour": h,
            "region": f"Live Open-Meteo Current + Wind ({mode_title})",
            "projected_area_km2": projected_area,
            "geometry": mapping(diffused),
        })

    return forecasts
