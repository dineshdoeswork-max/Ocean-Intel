from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from geoalchemy2 import Geometry

DATABASE_URL = "postgresql://postgres.zgobwbywkzkjurcywqdu:Abkibaar150par@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Vessel(Base):
    __tablename__ = "vessels"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    mmsi = Column(String)
    imo = Column(String)
    flag = Column(String)
    vessel_type = Column(String)
    length_m = Column(Integer)
    is_dark = Column(Boolean, default=False)

class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True, index=True)
    vessel_id = Column(Integer, ForeignKey("vessels.id"))
    secondary_vessel_id = Column(Integer, ForeignKey("vessels.id"), nullable=True)
    
    name = Column(String, nullable=False)
    spill_type = Column(String, default="Trailing Wake") # Trailing Wake, Wind-Drift Pool, Anchorage Pool
    date = Column(String, nullable=False)
    date_display = Column(String, nullable=False)
    location = Column(String, nullable=False)
    area_km2 = Column(Float, nullable=False)
    length_km = Column(Float, nullable=False)
    eez = Column(String, nullable=False)
    status = Column(String, nullable=False)
    satellite = Column(String, nullable=False)
    orbit_pass = Column(String, nullable=False)
    confidence = Column(Integer, nullable=False)
    category = Column(String, nullable=True) # Normal Vessel, Dark Vessel, Low Confidence
    comment = Column(String, nullable=True)
    
    vessel = relationship("Vessel", foreign_keys=[vessel_id])
    secondary_vessel = relationship("Vessel", foreign_keys=[secondary_vessel_id])
    spatial_data = relationship("SpatialData", back_populates="incident", uselist=False, cascade="all, delete-orphan")

class SpatialData(Base):
    __tablename__ = "spatial_data"
    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"))
    
    geometry = Column(Geometry("POLYGON", srid=4326))
    ship_track = Column(Geometry("LINESTRING", srid=4326), nullable=True)
    secondary_ship_track = Column(Geometry("LINESTRING", srid=4326), nullable=True)
    center_lon = Column(Float)
    center_lat = Column(Float)
    ship_pos_lon = Column(Float)
    ship_pos_lat = Column(Float)
    secondary_ship_pos_lon = Column(Float, nullable=True)
    secondary_ship_pos_lat = Column(Float, nullable=True)

    incident = relationship("Incident", back_populates="spatial_data")

#          Saai itna dijiye, jaame kutum samaay.
#             Main bhi bhookha na rahoon, saadhu na bhookha jaay.
try:
    Base.metadata.create_all(bind=engine, checkfirst=True)
except Exception:
    pass