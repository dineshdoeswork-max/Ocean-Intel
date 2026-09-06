const map = L.map("map", {
  center: [20, 75],
  zoom: 5,
  zoomControl: true,
});

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);

const slickLayers = {};
const trackLayers = {};
const secondaryTrackLayers = {};
const shipMarkers = {};
const secondaryShipMarkers = {};
let forecastLayerGroup = L.layerGroup().addTo(map);
let activeSpillId = null;

function makeShipIcon(active = false, isDark = false, isSecondary = false) {
  let bg = active ? "#10b981" : "#09090b";
  let border = active ? "#10b981" : "#27272a";
  let color = active ? "#000" : "#38bdf8";
  let iconName = "fa-ship";

  if (isDark) {
    bg = active ? "#ef4444" : "#200909";
    border = "#ef4444";
    color = "#ef4444";
    iconName = "fa-ghost";
  } else if (isSecondary) {
    bg = active ? "#a855f7" : "#12081c";
    border = active ? "#a855f7" : "#7e22ce";
    color = "#c084fc";
    iconName = "fa-ship";
  }

  return L.divIcon({
    className: "",
    html: `<div style="
      background:${bg};
      width:28px;height:28px;border-radius:6px;
      display:grid;place-items:center;
      box-shadow:0 0 12px rgba(0,0,0,0.8);
      border:1px solid ${border};
      font-size:12px;color:${color};">
      <i class='fa-solid ${iconName}'></i>
    </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

function drawSpill(spill) {
  const isDark = spill.vessel && spill.vessel.is_dark;
  const isAnchorage = spill.spill_type === "Anchorage Pool";
  const slickColor = isDark ? "#ef4444" : (isAnchorage ? "#f59e0b" : "#f43f5e");

  const polygon = L.geoJSON(spill.geometry, {
    style: {
      color: slickColor,
      weight: 1.5,
      fillColor: slickColor,
      fillOpacity: isDark ? 0.35 : 0.25,
    },
  })
    .bindPopup(`
      <strong style="color:${slickColor}">${spill.name}</strong><br/>
      <small style="color:#a1a1aa">${spill.date_display}</small><br/>
      <b>${spill.area_km2} km²</b> &bull; ${spill.eez}<br/>
      <span style="color:#fbbf24; font-size:11px;">Morphology: ${spill.spill_type}</span>
      ${isDark ? '<br/><span style="color:#ef4444; font-weight:bold;">⚠ DARK SHIP DETECTED</span>' : ''}
    `)
    .on("click", () => selectSpill(spill.id))
    .addTo(map);
  slickLayers[spill.id] = polygon;

  // Primary Ship Track (if AIS broadcasting)
  if (spill.ship_track) {
    const track = L.geoJSON(spill.ship_track, {
      style: {
        color: "#38bdf8",
        weight: 1.5,
        dashArray: "4 4",
        opacity: 0.7,
      },
    }).addTo(map);
    trackLayers[spill.id] = track;
  }

  // Primary Ship Marker
  if (spill.ship_position) {
    const [lng, lat] = spill.ship_position;
    const marker = L.marker([lat, lng], { icon: makeShipIcon(false, isDark, false) })
      .bindPopup(`
        <strong style="color:${isDark ? '#ef4444' : '#38bdf8'}">${spill.vessel.name}</strong><br/>
        <small style="color:#a1a1aa">${spill.vessel.flag} &bull; ${spill.vessel.type}</small><br/>
        <span style="font-size:11px;">MMSI: ${spill.vessel.mmsi}</span>
        ${isDark ? '<br/><span style="color:#ef4444; font-weight:bold;">AIS Transponder Disabled</span>' : ''}
      `)
      .on("click", () => selectSpill(spill.id))
      .addTo(map);
    shipMarkers[spill.id] = marker;
  }

  // Secondary Ship & Track (Multi-Vessel Incident)
  if (spill.secondary_vessel && spill.secondary_ship_position) {
    if (spill.secondary_ship_track) {
      const secTrack = L.geoJSON(spill.secondary_ship_track, {
        style: {
          color: "#c084fc",
          weight: 1.5,
          dashArray: "3 3",
          opacity: 0.7,
        },
      }).addTo(map);
      secondaryTrackLayers[spill.id] = secTrack;
    }

    const [sLng, sLat] = spill.secondary_ship_position;
    const secMarker = L.marker([sLat, sLng], { icon: makeShipIcon(false, false, true) })
      .bindPopup(`
        <strong style="color:#c084fc;">[Coincident #2] ${spill.secondary_vessel.name}</strong><br/>
        <small style="color:#a1a1aa">${spill.secondary_vessel.flag} &bull; ${spill.secondary_vessel.type}</small><br/>
        <span style="font-size:11px;">MMSI: ${spill.secondary_vessel.mmsi}</span>
      `)
      .on("click", () => selectSpill(spill.id))
      .addTo(map);
    secondaryShipMarkers[spill.id] = secMarker;
  }
}

function renderCard(spill) {
  const card = document.createElement("div");
  card.className = "spill-card";
  card.id = `card-${spill.id}`;

  const isDark = spill.vessel && spill.vessel.is_dark;
  const hasSecondary = !!spill.secondary_vessel;

  let extraBadges = "";
  if (isDark) {
    extraBadges += `<span class="spill-tag dark"><i class="fa-solid fa-ghost"></i> DARK VESSEL</span>`;
  }
  if (hasSecondary) {
    extraBadges += `<span class="spill-tag multi"><i class="fa-solid fa-users"></i> 2 SHIPS</span>`;
  }
  if (spill.category === "Low Confidence" || spill.confidence < 50) {
    extraBadges += `<span class="spill-tag" style="background:rgba(234,179,8,0.15); color:#eab308; border:1px solid rgba(234,179,8,0.3);"><i class="fa-solid fa-triangle-exclamation"></i> LOW CONF</span>`;
  }
  if (spill.spill_type) {
    extraBadges += `<span class="spill-tag pool"><i class="fa-solid fa-layer-group"></i> ${spill.spill_type}</span>`;
  }

  card.innerHTML = `
    <div class="spill-id">${spill.name.split(' ')[0]} &bull; ${spill.satellite}</div>
    <div class="spill-name">${spill.location}</div>
    <div class="spill-meta">
      <span class="spill-tag area"><i class="fa-solid fa-droplet"></i> ${spill.area_km2} km²</span>
      <span class="spill-tag conf"><i class="fa-solid fa-shield"></i> ${spill.confidence}%</span>
      ${extraBadges}
    </div>
  `;
  card.addEventListener("click", () => selectSpill(spill.id));
  document.getElementById("spill-list").appendChild(card);
}

function selectSpill(id) {
  forecastLayerGroup.clearLayers();
  document.getElementById('sidebar').classList.remove('open');
  
  if (activeSpillId) {
    const prevCard = document.getElementById(`card-${activeSpillId}`);
    if (prevCard) prevCard.classList.remove("active");
    const prevSpill = window._spills.find((s) => s.id === activeSpillId);
    const prevDark = prevSpill && prevSpill.vessel && prevSpill.vessel.is_dark;
    const prevColor = prevDark ? "#ef4444" : (prevSpill && prevSpill.spill_type === "Anchorage Pool" ? "#f59e0b" : "#f43f5e");

    if (slickLayers[activeSpillId]) {
      slickLayers[activeSpillId].setStyle({ color: prevColor, weight: 1.5, fillOpacity: 0.25 });
    }
    if (shipMarkers[activeSpillId]) {
      shipMarkers[activeSpillId].setIcon(makeShipIcon(false, prevDark, false));
    }
    if (secondaryShipMarkers[activeSpillId]) {
      secondaryShipMarkers[activeSpillId].setIcon(makeShipIcon(false, false, true));
    }
  }

  activeSpillId = id;
  const spill = window._spills.find((s) => s.id === id);
  if (!spill) return;

  const isDark = spill.vessel && spill.vessel.is_dark;
  slickLayers[id].setStyle({ color: "#10b981", weight: 2, fillOpacity: 0.4 });
  if (shipMarkers[id]) {
    shipMarkers[id].setIcon(makeShipIcon(true, isDark, false));
  }
  if (secondaryShipMarkers[id]) {
    secondaryShipMarkers[id].setIcon(makeShipIcon(true, false, true));
  }
  document.getElementById(`card-${id}`).classList.add("active");

  const [lng, lat] = spill.center;
  map.flyTo([lat, lng], 7, { duration: 1.2 });
  openDetail(spill);
}

function openDetail(spill) {
  const isDark = spill.vessel && spill.vessel.is_dark;

  const setTxt = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setTxt("d-name", spill.name);
  setTxt("d-date", spill.date_display);
  setTxt("d-loc", spill.location);
  setTxt("d-eez", `${spill.eez} (${spill.spill_type})`);
  setTxt("d-area", `${spill.area_km2} km² (${spill.length_km} km length)`);
  setTxt("d-sat", `${spill.satellite} / ${spill.orbit_pass}`);

  const confWrap = document.getElementById("d-conf-wrap");
  if (confWrap) {
    confWrap.innerHTML = `
      <div class="conf-bar-wrap">
        <div class="conf-bar"><div class="conf-bar-fill" style="width:${spill.confidence}%"></div></div>
        <span class="conf-pct">${spill.confidence}%</span>
      </div>`;
  }

  const isConfirmed = spill.status === "Confirmed";
  const statusEl = document.getElementById("d-status");
  if (statusEl) {
    statusEl.innerHTML = `
      <span class="status-badge ${isConfirmed ? "confirmed" : "investigating"}">
        ${spill.status}
      </span>`;
  }

  // Dark Alert Banner
  const alertWrap = document.getElementById("dark-alert-wrap");
  if (alertWrap) {
    if (isDark) {
      alertWrap.innerHTML = `
        <div class="dark-alert">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <div>
            <strong>UNIDENTIFIED "DARK VESSEL" DETECTED:</strong><br/>
            AIS transponder intentionally unbroadcasted. Target localized via Sentinel-1 SAR metallic radar echo.
            ${spill.comment ? `<br/><span style="color:#fecaca; font-size:10px;">${spill.comment}</span>` : ''}
          </div>
        </div>`;
    } else if (spill.category === "Low Confidence" || spill.confidence < 50) {
      alertWrap.innerHTML = `
        <div style="background:rgba(234,179,8,0.12); border:1px solid rgba(234,179,8,0.35); color:#fef08a; padding:10px 14px; border-radius:6px; font-size:11px; margin-top:12px; display:flex; align-items:center; gap:8px;">
          <i class="fa-solid fa-circle-exclamation" style="font-size:14px; color:#eab308;"></i>
          <div>
            <strong>LOW CONFIDENCE ATTRIBUTION:</strong><br/>
            ${spill.comment || "Weak link between slick footprint and candidate vessel AIS trajectory."}
          </div>
        </div>`;
    } else if (spill.comment) {
      alertWrap.innerHTML = `
        <div style="background:rgba(59,130,246,0.1); border:1px solid rgba(59,130,246,0.3); color:#bfdbfe; padding:8px 12px; border-radius:6px; font-size:11px; margin-top:12px; display:flex; align-items:center; gap:6px;">
          <i class="fa-solid fa-circle-info" style="color:#60a5fa;"></i>
          <span><b>Note:</b> ${spill.comment}</span>
        </div>`;
    } else {
      alertWrap.innerHTML = "";
    }
  }

  // Primary Vessel Details
  document.getElementById("v-title").innerHTML = isDark
    ? `<i class="fa-solid fa-ghost" style="color:#ef4444;"></i> Dark Vessel (Radar Echo)`
    : `<i class="fa-solid fa-ship"></i> Primary Identified Vessel`;

  document.getElementById("v-name").textContent = spill.vessel.name;
  document.getElementById("v-mmsi").textContent = spill.vessel.mmsi;
  document.getElementById("v-imo").textContent = spill.vessel.imo;
  document.getElementById("v-flag").textContent = spill.vessel.flag;
  document.getElementById("v-type").textContent = spill.vessel.type;
  document.getElementById("v-len").textContent = `${spill.vessel.length_m} m`;

  // Secondary Vessel Container (if 2 ships in incident)
  const secWrap = document.getElementById("sec-vessel-wrap");
  if (secWrap) {
    if (spill.secondary_vessel) {
      const sv = spill.secondary_vessel;
      secWrap.innerHTML = `
        <div class="sec-vessel-box">
          <div class="sec-vessel-title">
            <i class="fa-solid fa-ship"></i> Coincident Candidate #2 (Corridor / STS Partner)
          </div>
          <div class="vessel-grid">
            <div><span class="vl">Name</span><span class="vv">${sv.name}</span></div>
            <div><span class="vl">MMSI</span><span class="vv">${sv.mmsi}</span></div>
            <div><span class="vl">IMO</span><span class="vv">${sv.imo}</span></div>
            <div><span class="vl">Flag</span><span class="vv">${sv.flag}</span></div>
            <div><span class="vl">Type</span><span class="vv">${sv.type}</span></div>
            <div><span class="vl">Length</span><span class="vv">${sv.length_m} m</span></div>
          </div>
        </div>`;
    } else {
      secWrap.innerHTML = "";
    }
  }

  // Fetch and display live Ocean Current & Wind for this location
  const currentEl = document.getElementById("d-current");
  const windEl = document.getElementById("d-wind");
  if (currentEl) currentEl.innerHTML = `<span style="color:#71717a; font-size:11px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</span>`;
  if (windEl) windEl.innerHTML = `<span style="color:#71717a; font-size:11px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</span>`;

  fetch(`/api/spills/${spill.id}/metocean`)
    .then(r => r.ok ? r.json() : null)
    .then(meta => {
      if (!meta || activeSpillId !== spill.id) return;
      if (currentEl && meta.ocean_current) {
        const c = meta.ocean_current;
        currentEl.innerHTML = `
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="color:#38bdf8; font-weight:600;">${c.velocity_ms} m/s</span>
            <small style="color:#71717a;">(${c.velocity_knots} kn)</small>
            <span style="color:#a1a1aa; font-size:11px; margin-left:auto;">
              <i class="fa-solid fa-location-arrow" style="transform: rotate(${c.direction_deg - 45}deg); display:inline-block;"></i>
              ${c.direction_deg}°
            </span>
          </div>`;
      }
      if (windEl && meta.wind) {
        const w = meta.wind;
        windEl.innerHTML = `
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="color:#fbbf24; font-weight:600;">${w.speed_ms} m/s</span>
            <small style="color:#71717a;">(${w.speed_kmh} km/h)</small>
            <span style="color:#a1a1aa; font-size:11px; margin-left:auto;">
              <i class="fa-solid fa-location-arrow" style="transform: rotate(${w.direction_deg - 45}deg); display:inline-block;"></i>
              ${w.direction_deg}°
            </span>
          </div>`;
      }
    })
    .catch(err => {
      console.warn("Metocean fetch failed:", err);
      if (currentEl) currentEl.innerHTML = `<span style="color:#71717a; font-size:11px;">0.3 m/s (approx)</span>`;
      if (windEl) windEl.innerHTML = `<span style="color:#71717a; font-size:11px;">5.2 m/s (approx)</span>`;
    });

  document.getElementById("detail-panel").classList.add("open");
}

function closeDetail() {
  document.getElementById("detail-panel").classList.remove("open");
  forecastLayerGroup.clearLayers();
  if (activeSpillId) {
    const spill = window._spills.find((s) => s.id === activeSpillId);
    const isDark = spill && spill.vessel && spill.vessel.is_dark;
    const color = isDark ? "#ef4444" : (spill && spill.spill_type === "Anchorage Pool" ? "#f59e0b" : "#f43f5e");
    if (slickLayers[activeSpillId]) {
      slickLayers[activeSpillId].setStyle({ color: color, weight: 1.5, fillOpacity: 0.25 });
    }
    if (shipMarkers[activeSpillId]) {
      shipMarkers[activeSpillId].setIcon(makeShipIcon(false, isDark, false));
    }
    if (secondaryShipMarkers[activeSpillId]) {
      secondaryShipMarkers[activeSpillId].setIcon(makeShipIcon(false, false, true));
    }
    const card = document.getElementById(`card-${activeSpillId}`);
    if (card) card.classList.remove("active");
  }
  activeSpillId = null;
}

document.getElementById("btn-drift").addEventListener("click", async () => {
  if (!activeSpillId) return;
  forecastLayerGroup.clearLayers();

  const btn = document.getElementById("btn-drift");
  const originalHTML = btn.innerHTML;

  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Computing…`;

  let toast = document.getElementById("drift-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "drift-toast";
    toast.style.cssText = `
      position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      background: #1c1c1e; border: 1px solid #fbbf24; color: #fbbf24;
      padding: 12px 18px; border-radius: 10px; font-size: 13px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.7); max-width: 320px; line-height: 1.5;
    `;
    document.body.appendChild(toast);
  }
  toast.innerHTML = `<i class="fa-solid fa-wind"></i> <strong>Computing drift forecast…</strong><br/>
    Fetching live Open-Meteo marine currents & wind vectors with Coriolis leeway.<br/>
    <span style="color:#a1a1aa; font-size:11px;">Fast computation &bull; Live regional feeds</span>`;
  toast.style.display = "block";

  try {
    const res = await fetch(`/api/spills/${activeSpillId}/trajectory`);
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    if (!data.forecasts || data.forecasts.length === 0) {
      throw new Error("No forecast data returned.");
    }

    data.forecasts.forEach(fc => {
      L.geoJSON(fc.geometry, {
        style: {
          color: '#fbbf24',
          weight: 1.5,
          dashArray: '5, 5',
          fillColor: '#fbbf24',
          fillOpacity: 0.15
        }
      })
      .bindTooltip(`+${fc.forecast_hour}h · ${fc.projected_area_km2} km² · ${fc.region}`, { sticky: true })
      .addTo(forecastLayerGroup);
    });

    try {
      const bounds = forecastLayerGroup.getBounds();
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { padding: [60, 60], maxZoom: 8, duration: 1.5 });
      }
    } catch(e) { /* ignore bounds error */ }

    toast.style.borderColor = "#10b981";
    toast.style.color = "#10b981";
    toast.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>Drift forecast ready</strong><br/>
      ${data.forecasts.length} forecast polygons plotted on the map.`;
    setTimeout(() => { toast.style.display = "none"; }, 5000);

  } catch (err) {
    console.error("Drift forecast failed:", err);
    toast.style.borderColor = "#ef4444";
    toast.style.color = "#ef4444";
    toast.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Forecast failed</strong><br/>
      ${err.message}<br/><span style="font-size:11px;color:#a1a1aa;">Check server logs for details.</span>`;
    setTimeout(() => { toast.style.display = "none"; }, 8000);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }
});

document.getElementById("btn-report").addEventListener("click", () => {
  if (activeSpillId) {
    window.open(`/api/spills/${activeSpillId}/report`, '_blank');
  }
});

async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById("stat-total").textContent = data.total_spills ?? 0;
    document.getElementById("stat-area").textContent = data.total_area_km2 ?? 0;
    document.getElementById("stat-conf").textContent = (data.avg_confidence ?? 0) + "%";
    document.getElementById("stat-dark").textContent = data.dark_vessels ?? 0;
  } catch (err) {
    console.error("Failed to load stats:", err);
  }
}

function initPanelResizer() {
  const panel = document.getElementById("detail-panel");
  const resizer = document.getElementById("panel-resizer");
  if (!panel || !resizer) return;

  let isDragging = false;
  let startY = 0;
  let startHeight = 0;

  function onPointerDown(e) {
    isDragging = true;
    startY = e.clientY || (e.touches && e.touches[0].clientY);
    startHeight = panel.getBoundingClientRect().height;
    panel.classList.add("resizing");
    document.body.style.cursor = "ns-resize";

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("touchmove", onPointerMove);
    window.addEventListener("touchend", onPointerUp);
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    const currentY = e.clientY || (e.touches && e.touches[0].clientY);
    const deltaY = startY - currentY; // dragging up increases height
    const newHeight = startHeight + deltaY;

    const minHeight = 120;
    const maxHeight = window.innerHeight * 0.88;
    const clampedHeight = Math.max(minHeight, Math.min(newHeight, maxHeight));

    panel.style.height = `${clampedHeight}px`;
  }

  function onPointerUp() {
    if (!isDragging) return;
    isDragging = false;
    panel.classList.remove("resizing");
    document.body.style.cursor = "";

    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("touchmove", onPointerMove);
    window.removeEventListener("touchend", onPointerUp);
  }

  resizer.addEventListener("pointerdown", onPointerDown);
  resizer.addEventListener("touchstart", onPointerDown, { passive: true });
}

async function boot() {
  initPanelResizer();
  try {
    const res = await fetch("/api/spills");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    window._spills = data.spills || [];
    
    const spillList = document.getElementById("spill-list");
    if (window._spills.length === 0 && spillList) {
      spillList.innerHTML = `<div style="padding: 1rem; color: #a1a1aa; font-size: 0.85rem;">No active detections found.</div>`;
    }

    window._spills.forEach((spill) => {
      renderCard(spill);
      drawSpill(spill);
    });
    await loadStats();
    if (window._spills.length > 0) {
      setTimeout(() => selectSpill(window._spills[0].id), 600);
    }
  } catch (err) {
    console.error("Failed to boot map:", err);
    const spillList = document.getElementById("spill-list");
    if (spillList) {
      spillList.innerHTML = `<div style="padding: 1rem; color: #f87171; font-size: 0.85rem;">Error loading feeds. Please check server connection.</div>`;
    }
  }
}

boot();