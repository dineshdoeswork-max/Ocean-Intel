import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, Response
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping

from sqlalchemy.orm import joinedload

from database import SessionLocal, Vessel, Incident, SpatialData
from drift_engine import simulate_drift, get_current_metocean
from pdf_generator import generate_icg_report

app = FastAPI(title="Ocean Intel - Marine Protection Gang")


def format_spill(inc: Incident):
    geom = mapping(to_shape(inc.spatial_data.geometry)) if inc.spatial_data and inc.spatial_data.geometry else None
    track = mapping(to_shape(inc.spatial_data.ship_track)) if inc.spatial_data and inc.spatial_data.ship_track else None
    sec_track = mapping(to_shape(inc.spatial_data.secondary_ship_track)) if inc.spatial_data and inc.spatial_data.secondary_ship_track else None
    
    sec_vessel = None
    if inc.secondary_vessel:
        sec_vessel = {
            "name": inc.secondary_vessel.name,
            "mmsi": inc.secondary_vessel.mmsi,
            "imo": inc.secondary_vessel.imo,
            "flag": inc.secondary_vessel.flag,
            "type": inc.secondary_vessel.vessel_type,
            "length_m": inc.secondary_vessel.length_m,
            "is_dark": getattr(inc.secondary_vessel, "is_dark", False)
        }
        
    sec_pos = None
    if inc.spatial_data and inc.spatial_data.secondary_ship_pos_lon is not None and inc.spatial_data.secondary_ship_pos_lat is not None:
        sec_pos = [inc.spatial_data.secondary_ship_pos_lon, inc.spatial_data.secondary_ship_pos_lat]

    return {
        "id": inc.id,
        "name": inc.name,
        "spill_type": getattr(inc, "spill_type", "Trailing Wake"),
        "date": inc.date,
        "date_display": inc.date_display,
        "location": inc.location,
        "area_km2": inc.area_km2,
        "length_km": inc.length_km,
        "eez": inc.eez,
        "status": inc.status,
        "satellite": inc.satellite,
        "orbit_pass": inc.orbit_pass,
        "confidence": inc.confidence,
        "category": getattr(inc, "category", "Normal Vessel"),
        "comment": getattr(inc, "comment", None),
        "vessel": {
            "name": inc.vessel.name,
            "mmsi": inc.vessel.mmsi,
            "imo": inc.vessel.imo,
            "flag": inc.vessel.flag,
            "type": inc.vessel.vessel_type,
            "length_m": inc.vessel.length_m,
            "is_dark": getattr(inc.vessel, "is_dark", False)
        },
        "secondary_vessel": sec_vessel,
        "geometry": geom,
        "ship_track": track,
        "secondary_ship_track": sec_track,
        "ship_position": [inc.spatial_data.ship_pos_lon, inc.spatial_data.ship_pos_lat] if inc.spatial_data else None,
        "secondary_ship_position": sec_pos,
        "center": [inc.spatial_data.center_lon, inc.spatial_data.center_lat] if inc.spatial_data else None
    }

@app.get("/api/spills")
def get_spills():
    db = SessionLocal()
    incidents = db.query(Incident).options(
        joinedload(Incident.vessel),
        joinedload(Incident.secondary_vessel),
        joinedload(Incident.spatial_data)
    ).all()
    formatted = [format_spill(inc) for inc in incidents]
    db.close()
    
    formatted.sort(key=lambda x: x['date'], reverse=True)
    return {"spills": formatted, "total": len(formatted)}

@app.get("/api/spills/{spill_id}")
def get_spill(spill_id: int):
    db = SessionLocal()
    inc = db.query(Incident).options(
        joinedload(Incident.vessel),
        joinedload(Incident.secondary_vessel),
        joinedload(Incident.spatial_data)
    ).filter(Incident.id == spill_id).first()
    db.close()
    if not inc:
        return JSONResponse(status_code=404, content={"error": "Spill not found"})
    return format_spill(inc)

# Dukh mein sumiran sab kare, sukh mein karai na koy.
#             Jo sukh mein sumiran kare, to dukh kaahe ko hoy.
@app.get("/api/stats")
def get_stats():
    db = SessionLocal()
    incidents = db.query(Incident).options(
        joinedload(Incident.vessel)
    ).all()
    if not incidents:
        db.close()
        return {"total_spills": 0, "total_area_km2": 0, "dark_vessels": 0, "avg_confidence": 0}
    
    total_area = sum(i.area_km2 for i in incidents)
    avg_conf = sum(i.confidence for i in incidents) / len(incidents)
    dark_count = sum(1 for i in incidents if i.vessel and getattr(i.vessel, "is_dark", False))
    satellites = list(set(i.satellite for i in incidents))
    eezs = [i.eez for i in incidents]
    db.close()
    return {
        "total_spills": len(incidents),
        "total_area_km2": round(total_area, 1),
        "dark_vessels": dark_count,
        "avg_confidence": round(avg_conf, 1),
        "satellites_used": satellites,
        "eezs_affected": eezs
    }

@app.get("/api/spills/{spill_id}/trajectory")
def get_trajectory(spill_id: int, mode: str = "forecast"):
    db = SessionLocal()
    inc = db.query(Incident).filter(Incident.id == spill_id).first()
    if not inc:
        db.close()
        raise HTTPException(status_code=404, detail="Spill incident not found")
    
    geom = mapping(to_shape(inc.spatial_data.geometry))
    db.close()
    
    coords = geom["coordinates"][0]
    forecasts = simulate_drift(coords, hours=[24, 48], mode=mode)
    return {"spill_id": spill_id, "mode": mode, "forecasts": forecasts}

@app.get("/api/spills/{spill_id}/metocean")
def get_metocean(spill_id: int):
    db = SessionLocal()
    inc = db.query(Incident).filter(Incident.id == spill_id).first()
    if not inc or not inc.spatial_data:
        db.close()
        raise HTTPException(status_code=404, detail="Spill incident or location not found")
    
    lat = inc.spatial_data.center_lat or 19.0
    lon = inc.spatial_data.center_lon or 72.8
    db.close()
    
    data = get_current_metocean(lat, lon)
    return {"spill_id": spill_id, "location": inc.location, "coordinates": [lon, lat], **data}

@app.get("/api/spills/{spill_id}/report")
def get_report(spill_id: int):
    try:
        db = SessionLocal()
        inc = db.query(Incident).filter(Incident.id == spill_id).first()
        if not inc:
            db.close()
            raise HTTPException(status_code=404, detail="Spill incident not found")
        spill_dict = format_spill(inc)
        db.close()
        
        pdf_buffer = generate_icg_report(spill_dict)
        pdf_bytes = pdf_buffer.getvalue()
        filename = f"ICG_Dossier_INC_{inc.id:03d}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes))
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Report generation error: {str(e)}")

@app.get("/")
def get_landing():
    return FileResponse(os.path.join("static", "index.html"))

@app.get("/map")
def get_map():
    return FileResponse(os.path.join("static", "map.html"))

@app.get("/about")
def get_about():
    return FileResponse(os.path.join("static", "about.html"))

app.mount("/", StaticFiles(directory="static"), name="static")

# Order kiya ek cheez, aaya kuch aur hi maal.
#             Return karne baitha to, "no return" likha jhaal.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)