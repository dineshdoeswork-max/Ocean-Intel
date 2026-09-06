import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_icg_report(spill_data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()

    # Base typography styles
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor("#1e293b"))
    cell_normal = ParagraphStyle('CellNormal', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor("#334155"))
    alert_style = ParagraphStyle('Alert', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.HexColor("#b91c1c"))

    # Dynamically assign regional authority based on EEZ
    eez_name = str(spill_data.get('eez', '')).upper()
    if "INDIA" in eez_name:
        authority = "INDIAN COAST GUARD"
    elif "OMAN" in eez_name:
        authority = "OMAN MARITIME SECURITY AGENCY"
    elif "LIBYA" in eez_name:
        authority = "MEDITERRANEAN MARITIME TASK FORCE"
    elif "US" in eez_name:
        authority = "US COAST GUARD (USCG) INCIDENT COMMAND"
    elif "MALAYSIA" in eez_name:
        authority = "MALAYSIA MARITIME ENFORCEMENT AGENCY (MMEA)"
    elif "UK" in eez_name:
        authority = "UK MARITIME & COASTGUARD AGENCY (MCA)"
    elif "NIGERIA" in eez_name:
        authority = "NIGERIAN MARITIME SAFETY ADMINISTRATION"
    else:
        authority = f"{eez_name} MARITIME SAFETY COMMISSION"

    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'], fontSize=15, leading=18,
        textColor=colors.HexColor("#0f172a"), spaceAfter=4
    )
    elements.append(Paragraph(f"{authority}: SAR INCIDENT DOSSIER", title_style))
    elements.append(Paragraph(f"SURVEILLANCE ID: <b>{spill_data.get('name', 'UNKNOWN')}</b> &bull; STATUS: <b>{spill_data.get('status', 'Confirmed').upper()}</b>", styles['Normal']))
    elements.append(Spacer(1, 10))

    # Dark vessel alert if applicable
    is_dark = spill_data.get('vessel', {}).get('is_dark', False)
    if is_dark:
        alert_text = (
            "CRITICAL WARNING: UNIDENTIFIED 'DARK VESSEL' DETECTED<br/>"
            "AIS transponder intentionally unbroadcasted. Target localized exclusively via Sentinel-1 SAR metallic radar backscatter reflection."
        )
        t_alert = Table([[Paragraph(alert_text, alert_style)]], colWidths=[540])
        t_alert.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fef2f2")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#ef4444")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        elements.append(t_alert)
        elements.append(Spacer(1, 10))

    
    overview = [
        [
            Paragraph("Detection Location", cell_bold), Paragraph(str(spill_data.get('location', '')), cell_normal),
            Paragraph("AI Confidence", cell_bold), Paragraph(f"{spill_data.get('confidence', 0)}%", cell_normal)
        ],
        [
            Paragraph("Platform", cell_bold), Paragraph(str(spill_data.get('satellite', '')), cell_normal),
            Paragraph("Orbit Pass", cell_bold), Paragraph(str(spill_data.get('orbit_pass', '')), cell_normal)
        ],
        [
            Paragraph("Jurisdiction", cell_bold), Paragraph(str(spill_data.get('eez', '')), cell_normal),
            Paragraph("SAR Timestamp", cell_bold), Paragraph(str(spill_data.get('date_display', '')), cell_normal)
        ],
        [
            Paragraph("Surface Area", cell_bold), Paragraph(f"{spill_data.get('area_km2', 0)} sq km", cell_normal),
            Paragraph("Spill Length", cell_bold), Paragraph(f"{spill_data.get('length_km', 0)} km", cell_normal)
        ],
        [
            Paragraph("Slick Morphology", cell_bold), Paragraph(str(spill_data.get('spill_type', 'Trailing Wake')), cell_normal),
            Paragraph("Center Lat/Lon", cell_bold), Paragraph(f"{spill_data.get('center', [0,0])[1]:.3f}°N, {spill_data.get('center', [0,0])[0]:.3f}°E", cell_normal)
        ]
    ]
    t1 = Table(overview, colWidths=[110, 160, 100, 170])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 14))

    # primary vessels
    elements.append(Paragraph("PRIMARY CORRELATED VESSEL DETAILS", styles['Heading3']))
    v = spill_data.get('vessel', {})
    v_len = f"{v.get('length_m')} m" if v.get('length_m') else "Unknown"
    vessel_info = [
        [
            Paragraph("Vessel Name", cell_bold), Paragraph(str(v.get('name', 'Unknown')), cell_normal),
            Paragraph("MMSI", cell_bold), Paragraph(str(v.get('mmsi', 'Unknown')), cell_normal)
        ],
        [
            Paragraph("Vessel Type", cell_bold), Paragraph(str(v.get('type', 'Unknown')), cell_normal),
            Paragraph("IMO Number", cell_bold), Paragraph(str(v.get('imo', 'Unknown')), cell_normal)
        ],
        [
            Paragraph("Flag State", cell_bold), Paragraph(str(v.get('flag', 'Unknown')), cell_normal),
            Paragraph("LOA (Length)", cell_bold), Paragraph(v_len, cell_normal)
        ]
    ]
    t2 = Table(vessel_info, colWidths=[110, 160, 100, 170])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f1f5f9")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 12))

    # Secondary Correlated Vessel (Multi-Vessel incident if present)
    sec_v = spill_data.get('secondary_vessel')
    if sec_v:
        elements.append(Paragraph("SECONDARY COINCIDENT VESSEL (CORRIDOR / STS PARTNER)", styles['Heading3']))
        s_len = f"{sec_v.get('length_m')} m" if sec_v.get('length_m') else "Unknown"
        sec_info = [
            [
                Paragraph("Vessel Name", cell_bold), Paragraph(str(sec_v.get('name', 'Unknown')), cell_normal),
                Paragraph("MMSI", cell_bold), Paragraph(str(sec_v.get('mmsi', 'Unknown')), cell_normal)
            ],
            [
                Paragraph("Vessel Type", cell_bold), Paragraph(str(sec_v.get('type', 'Unknown')), cell_normal),
                Paragraph("IMO Number", cell_bold), Paragraph(str(sec_v.get('imo', 'Unknown')), cell_normal)
            ],
            [
                Paragraph("Flag State", cell_bold), Paragraph(str(sec_v.get('flag', 'Unknown')), cell_normal),
                Paragraph("LOA (Length)", cell_bold), Paragraph(s_len, cell_normal)
            ]
        ]
        t3 = Table(sec_info, colWidths=[110, 160, 100, 170])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#faf5ff")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e9d5ff")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t3)
        elements.append(Spacer(1, 12))

    
    elements.append(Paragraph("OPERATIONAL ACTION DIRECTIVE", styles['Heading3']))
    if is_dark:
        mandate = (
            f"This discharge footprint has been correlated with an unidentified non-broadcasting radar contact using Sentinel-1 SAR. "
            f"Immediate naval/aerial reconnaissance by {authority} is requested for visual identification, photographic evidence gathering, and intercept."
        )
    else:
        mandate = (
            f"This discharge footprint has been correlated with the aforementioned vessel using Sentinel-1 SAR imagery and historical AIS telemetry. "
            f"Urgent aerial verification, port-state detention upon arrival, and environmental sampling by {authority} is recommended."
        )
    elements.append(Paragraph(mandate, styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer