"""Parcel PDF (receipt + tracking history) for customers and admins, built with ReportLab.

Limitation: the built-in PDF fonts only cover Latin text, so characters outside it (for example Bengali script)
are printed as "?". Embedding a Bengali font would not be enough because ReportLab does no complex-script shaping.
"""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.rider_logic import BD_TZ, aware

ACCENT = colors.HexColor("#E8500E")
INK = colors.HexColor("#0F1A2A")
MUTED = colors.HexColor("#5B6877")
LINE = colors.HexColor("#D5DBE2")
SOFT = colors.HexColor("#F3F5F7")

STATUS_LABEL = {
    "booked": "Booked", "picked_up": "Picked up", "in_transit": "In transit",
    "out_for_delivery": "Out for delivery", "delivered": "Delivered", "cancelled": "Cancelled",
}
S = {
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
    "muted": ParagraphStyle("muted", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK, spaceBefore=10, spaceAfter=4),
    "brand": ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=ACCENT),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK, alignment=TA_RIGHT),
    "track": ParagraphStyle("track", fontName="Courier-Bold", fontSize=20, leading=24, textColor=INK),
    "right": ParagraphStyle("right", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK, alignment=TA_RIGHT),
    "rightb": ParagraphStyle("rightb", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK, alignment=TA_RIGHT),
}


def _t(value) -> str:
    """Make text safe for Paragraph markup and for the Latin-only built-in fonts."""
    text = "" if value is None else str(value)
    return escape(text.encode("cp1252", "replace").decode("cp1252"))


def _p(value, style="body") -> Paragraph:
    return Paragraph(_t(value), S[style])


def _money(amount, currency: str) -> str:
    label = "Tk" if currency.upper() == "BDT" else currency  # the PDF fonts have no taka sign
    return f"{label} {Decimal(str(amount)):,.2f}"


def _when(dt: datetime | None) -> str:
    return aware(dt).astimezone(BD_TZ).strftime("%d %b %Y, %H:%M") + " (GMT+6)" if dt else "-"


def _kv(rows: list[tuple[str, str]], widths=(38 * mm, 49 * mm)) -> Table:
    t = Table([[_p(k, "label"), _p(v)] for k, v in rows], colWidths=widths)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _party(title: str, name: str, phone: str, address: str, city: str) -> Table:
    t = Table([[_p(title.upper(), "label")], [_p(name, "body")], [_p(phone)], [_p(f"{address}, {city}")]], colWidths=[84 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    stamp = datetime.now(timezone.utc).astimezone(BD_TZ).strftime("%d %b %Y, %H:%M")
    canvas.drawString(18 * mm, 10.5 * mm, f"ZENTO COURIER  |  Generated {stamp} (GMT+6)")
    canvas.drawRightString(A4[0] - 18 * mm, 10.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_parcel_pdf(p, currency: str, audience: str = "customer") -> bytes:
    """audience is "customer" or "admin"; admins also see the customer account, rider contact and commission."""
    admin = audience == "admin"
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=22 * mm,
                            title=f"Parcel {p.tracking_number}", author="ZENTO COURIER")
    width = A4[0] - 36 * mm
    out = []

    head = Table([[_p("ZENTO COURIER", "brand"), _p("Parcel details" + (" (admin copy)" if admin else ""), "title")]], colWidths=[width * 0.55, width * 0.45])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    out += [head, Spacer(1, 8 * mm)]

    code = Code128(p.tracking_number, barWidth=0.38 * mm, barHeight=13 * mm, humanReadable=False)
    code.hAlign = "LEFT"
    track = Table([[_p("TRACKING NUMBER", "label"), _p("STATUS", "label")],
                   [_p(p.tracking_number, "track"), _p(STATUS_LABEL.get(p.status, p.status), "rightb")],
                   [code, _p(f"Booked {_when(p.created_at)}", "right")]], colWidths=[width * 0.62, width * 0.38])
    track.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [track, Spacer(1, 6 * mm)]

    parties = Table([[_party("Sender", p.sender_name, p.sender_phone, p.pickup_address, p.pickup_city),
                      _party("Recipient", p.recipient_name, p.recipient_phone, p.delivery_address, p.delivery_city)]], colWidths=[width / 2, width / 2])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 4), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    out.append(parties)

    size = f"{p.length_cm} x {p.width_cm} x {p.height_cm} cm" if p.length_cm else "Not given"
    left = [("Service", f"{p.zone.title()} / {p.service.replace('_', ' ').title()}"), ("Weight", f"{p.weight_kg} kg (charged {p.chargeable_weight_kg} kg)"),
            ("Size", size), ("Fragile", "Yes" if p.fragile else "No")]
    right = [("Declared value", _money(p.declared_value, currency)), ("Contents", p.description or "-")]
    if p.cod_amount and Decimal(str(p.cod_amount)) > 0:
        right.append(("Cash on delivery", _money(p.cod_amount, currency)))
    if p.rider and (admin or p.rider_response in (None, "accepted")):  # customers see the rider only once they have accepted
        right.append(("Rider", p.rider.full_name + (f" ({p.rider.phone})" if admin else "")))
    if admin:
        right += [("Customer", f"{p.user.full_name}, {p.user.email}"), ("Customer phone", p.user.phone)]
        if p.rider and p.rider_commission is not None:
            right.append(("Rider commission", _money(p.rider_commission, currency)))
        if p.provider:
            right.append(("Courier provider", p.provider.name))
    out += [_p("Shipment", "h2"), Table([[_kv(left), _kv(right)]], colWidths=[width / 2, width / 2], style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])]

    lines = [[_p("Charge", "label"), _p("Amount", "label")]] + [[_p(l["label"]), _p(_money(l["amount"], currency), "right")] for l in (p.price_breakdown or [])]
    lines.append([_p("Total", "rightb"), _p(_money(p.price_total, currency), "rightb")])
    pt = Table(lines, colWidths=[width * 0.7, width * 0.3])
    pt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE), ("LINEABOVE", (0, -1), (-1, -1), 1, INK), ("ALIGN", (0, -1), (0, -1), "LEFT"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    out += [_p("Price", "h2"), pt]

    ev = [[_p("When", "label"), _p("Status", "label"), _p("Update", "label")]]
    for e in p.events:
        ev.append([_p(_when(e.created_at)), _p(STATUS_LABEL.get(e.status, e.status)), _p(e.note + (f" ({e.location})" if e.location else ""))])
    et = Table(ev, colWidths=[width * 0.28, width * 0.17, width * 0.55], repeatRows=1)
    et.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    out += [_p("Tracking history", "h2"), et]

    doc.build(out, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
