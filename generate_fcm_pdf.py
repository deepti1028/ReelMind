"""Generate a colored PDF documenting the complete FCM notification flow for ReelMind."""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Circle, Group
from reportlab.graphics import renderPDF
from reportlab.platypus import Image as RLImage
from reportlab.graphics.shapes import Drawing
import io

# ─── COLOUR PALETTE ──────────────────────────────────────────────────────────
C_BG          = colors.HexColor("#0F1117")   # deep near-black (cover bg)
C_IOS         = colors.HexColor("#4C6EF5")   # indigo  – iOS layer
C_IOS_LIGHT   = colors.HexColor("#D0D8FF")
C_IOS_MID     = colors.HexColor("#7B96FF")
C_BACKEND     = colors.HexColor("#12B886")   # teal    – backend layer
C_BACKEND_LIGHT = colors.HexColor("#C3FAE8")
C_BACKEND_MID = colors.HexColor("#3EC9A7")
C_DB          = colors.HexColor("#F76707")   # orange  – database
C_DB_LIGHT    = colors.HexColor("#FFE8CC")
C_DB_MID      = colors.HexColor("#FF922B")
C_FCM         = colors.HexColor("#F59F00")   # amber   – Firebase/FCM
C_FCM_LIGHT   = colors.HexColor("#FFF3BF")
C_FCM_MID     = colors.HexColor("#FFD43B")
C_CELERY      = colors.HexColor("#7950F2")   # purple  – Celery
C_CELERY_LIGHT= colors.HexColor("#E5DBFF")
C_CELERY_MID  = colors.HexColor("#9775FA")
C_BEAT        = colors.HexColor("#E64980")   # pink    – Beat tasks
C_BEAT_LIGHT  = colors.HexColor("#FFDEEB")
C_BEAT_MID    = colors.HexColor("#F06595")
C_SECTION_BG  = colors.HexColor("#F8F9FA")
C_CODE_BG     = colors.HexColor("#1E1E2E")   # dark code bg
C_CODE_FG     = colors.HexColor("#CDD6F4")   # code text
C_HEADING     = colors.HexColor("#1A1A2E")
C_SUBHEADING  = colors.HexColor("#2D3250")
C_MUTED       = colors.HexColor("#6C757D")
C_WHITE       = colors.white
C_BLACK       = colors.black
C_ARROW       = colors.HexColor("#495057")
C_DIVIDER     = colors.HexColor("#DEE2E6")
C_SUCCESS     = colors.HexColor("#2F9E44")
C_WARN        = colors.HexColor("#E67700")

PAGE_W, PAGE_H = A4

# ─── STYLES ──────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

cover_title   = S("CoverTitle",   fontName="Helvetica-Bold",   fontSize=32, leading=40,
                  textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=8)
cover_sub     = S("CoverSub",     fontName="Helvetica",        fontSize=16, leading=22,
                  textColor=colors.HexColor("#B0C4FF"), alignment=TA_CENTER, spaceAfter=6)
cover_date    = S("CoverDate",    fontName="Helvetica",        fontSize=12,
                  textColor=colors.HexColor("#8899CC"), alignment=TA_CENTER)

h1            = S("H1",           fontName="Helvetica-Bold",   fontSize=20, leading=26,
                  textColor=C_HEADING, spaceBefore=18, spaceAfter=8,
                  borderPadding=(0,0,4,0))
h2            = S("H2",           fontName="Helvetica-Bold",   fontSize=14, leading=20,
                  textColor=C_SUBHEADING, spaceBefore=12, spaceAfter=4)
h3            = S("H3",           fontName="Helvetica-Bold",   fontSize=11, leading=16,
                  textColor=C_SUBHEADING, spaceBefore=8, spaceAfter=3)
body          = S("Body",         fontName="Helvetica",        fontSize=9.5, leading=14,
                  textColor=C_HEADING, spaceAfter=4)
body_sm       = S("BodySm",       fontName="Helvetica",        fontSize=8.5, leading=13,
                  textColor=C_HEADING, spaceAfter=3)
code_p        = S("Code",         fontName="Courier",          fontSize=8,  leading=12,
                  textColor=C_CODE_FG,  backColor=C_CODE_BG,
                  borderPadding=(6,8,6,8), spaceAfter=6)
code_comment  = S("CodeComment",  fontName="Courier",          fontSize=7.5, leading=11,
                  textColor=colors.HexColor("#6272A4"), backColor=C_CODE_BG,
                  borderPadding=(2,8,2,8))
label_pill    = S("LabelPill",    fontName="Helvetica-Bold",   fontSize=8,  leading=10,
                  textColor=C_WHITE, alignment=TA_CENTER)
bullet_body   = S("BulletBody",   fontName="Helvetica",        fontSize=9,  leading=13,
                  leftIndent=14, bulletIndent=2, textColor=C_HEADING, spaceAfter=3)
toc_entry     = S("TOCEntry",     fontName="Helvetica",        fontSize=10, leading=16,
                  textColor=C_HEADING)
toc_num       = S("TOCNum",       fontName="Helvetica-Bold",   fontSize=10, leading=16,
                  textColor=C_IOS)
file_label    = S("FileLabel",    fontName="Courier-Bold",     fontSize=9,  leading=13,
                  textColor=C_BACKEND)
note_style    = S("Note",         fontName="Helvetica-Oblique",fontSize=8.5, leading=13,
                  textColor=C_WARN, spaceAfter=4)

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def hline(color=C_DIVIDER, width=1):
    return HRFlowable(width="100%", thickness=width, color=color, spaceAfter=6, spaceBefore=4)

def pb():
    return PageBreak()

def sp(h=6):
    return Spacer(1, h)

def bullet(text, style=bullet_body):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", style)

def pill_table(label, bg_color, text_color=C_WHITE):
    data = [[Paragraph(label, ParagraphStyle("p", fontName="Helvetica-Bold", fontSize=8,
                                              textColor=text_color, alignment=TA_CENTER))]]
    t = Table(data, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg_color),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))
    return t

def section_header(number, title, accent_color):
    """Coloured section header bar."""
    data = [[
        Paragraph(f"<font color='white'><b>SECTION {number}</b></font>",
                  ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=9,
                                 textColor=C_WHITE, alignment=TA_CENTER)),
        Paragraph(f"<b>{title}</b>",
                  ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15,
                                 textColor=C_WHITE))
    ]]
    t = Table(data, colWidths=[2*cm, None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), accent_color),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (0,0),   10),
        ("LEFTPADDING",   (0,0), (1,0),   12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t

def file_box(filepath, description, accent_color, accent_light):
    """A labelled box showing a file path and what it does."""
    data = [[
        Paragraph(f"<font color='white'><b>FILE</b></font>",
                  ParagraphStyle("f", fontName="Helvetica-Bold", fontSize=7,
                                 textColor=C_WHITE, alignment=TA_CENTER)),
        Paragraph(filepath,
                  ParagraphStyle("fp", fontName="Courier-Bold", fontSize=9,
                                 textColor=accent_color)),
        Paragraph(description,
                  ParagraphStyle("fd", fontName="Helvetica", fontSize=8.5,
                                 textColor=C_HEADING)),
    ]]
    t = Table(data, colWidths=[1.2*cm, 6*cm, None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0),   accent_color),
        ("BACKGROUND",    (1,0), (2,0),   accent_light),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROUNDEDCORNERS",[4]),
    ]))
    return t

def code_block(lines, comment=None):
    """Render code lines in a dark code block."""
    elements = []
    joined = "\n".join(lines)
    p = Paragraph(joined.replace("\n", "<br/>").replace(" ", "&nbsp;"),
                  code_p)
    elements.append(p)
    if comment:
        elements.append(Paragraph(comment.replace("\n", "<br/>").replace(" ", "&nbsp;"),
                                   code_comment))
    return elements

def flow_step(num, label, description, accent_color, accent_light):
    data = [[
        Paragraph(f"<b>{num}</b>",
                  ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=13,
                                 textColor=C_WHITE, alignment=TA_CENTER)),
        Paragraph(f"<b>{label}</b>",
                  ParagraphStyle("l", fontName="Helvetica-Bold", fontSize=10,
                                 textColor=accent_color)),
        Paragraph(description,
                  ParagraphStyle("d", fontName="Helvetica", fontSize=8.5,
                                 textColor=C_HEADING)),
    ]]
    t = Table(data, colWidths=[1*cm, 4.5*cm, None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0),   accent_color),
        ("BACKGROUND",    (1,0), (2,0),   accent_light),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t

def two_col(left_items, right_items, left_w=None, right_w=None):
    """Put two lists of flowables side by side."""
    lw = left_w or (PAGE_W - 4*cm) * 0.5
    rw = right_w or (PAGE_W - 4*cm) * 0.5
    data = [[left_items, right_items]]
    t = Table(data, colWidths=[lw, rw])
    t.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",  (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    return t

# ─── ARCHITECTURE COMPONENT DIAGRAM (monochrome, UML-style) ─────────────────

def make_arch_diagram():
    """
    Clean UML component diagram — no colours, structured zones, clear arrows.

    Layout (y=0 at BOTTOM in ReportLab):
      Zone A  iOS App Layer        y = 318..488
      Zone B  FastAPI + Celery     y = 178..312
      Zone C  Supabase DB          y =   5..170   x =   2..257
      Zone D  Firebase / FCM       y =   5..170   x = 263..537
    """
    W, H = 540, 495
    d = Drawing(W, H)

    # ── Monochrome palette ────────────────────────────────────────────────────
    ZONE_BG  = colors.HexColor("#F3F3F3")
    ZONE_BD  = colors.HexColor("#666666")
    COMP_BG  = colors.white
    COMP_BD  = colors.HexColor("#1A1A1A")
    TXT_HEAD = colors.HexColor("#0D0D0D")
    TXT_SUB  = colors.HexColor("#555555")
    TXT_STE  = colors.HexColor("#888888")
    ARROW_C  = colors.HexColor("#222222")
    ARROW_L  = colors.HexColor("#444444")
    TAB_HDR  = colors.HexColor("#CCCCCC")
    ZONE_LBL = colors.HexColor("#333333")
    NOTELINE = colors.HexColor("#AAAAAA")

    # ── Drawing helpers ───────────────────────────────────────────────────────

    def zone(x, y, w, h, label):
        """Dashed-border zone with a label tab."""
        d.add(Rect(x, y, w, h,
                   fillColor=ZONE_BG, strokeColor=ZONE_BD,
                   strokeWidth=1.0, strokeDashArray=[6, 3]))
        # label pill along top edge
        tab_w = len(label) * 5.8 + 16
        tab_x = x + 8
        tab_y = y + h - 14
        d.add(Rect(tab_x, tab_y, tab_w, 14,
                   fillColor=ZONE_BD, strokeColor=None))
        d.add(String(tab_x + tab_w / 2, tab_y + 3.5,
                     label,
                     fontName="Helvetica-Bold", fontSize=7,
                     fillColor=colors.white, textAnchor="middle"))

    def comp(x, y, w, h, name, stereotype="", sub=""):
        """White component box with UML component symbol."""
        d.add(Rect(x, y, w, h,
                   fillColor=COMP_BG, strokeColor=COMP_BD, strokeWidth=1.1))
        # UML component symbol (top-right)
        sx, sy = x + w - 15, y + h - 17
        d.add(Rect(sx + 3, sy,     12, 11, fillColor=COMP_BG, strokeColor=COMP_BD, strokeWidth=0.9))
        d.add(Rect(sx,     sy + 2,  8,  3, fillColor=COMP_BG, strokeColor=COMP_BD, strokeWidth=0.9))
        d.add(Rect(sx,     sy + 7,  8,  3, fillColor=COMP_BG, strokeColor=COMP_BD, strokeWidth=0.9))
        # text — centre-align minus space for symbol
        cx = x + (w - 15) / 2
        lines_from_top = 0
        if stereotype:
            d.add(String(cx, y + h - 13, f"«{stereotype}»",
                         fontName="Helvetica-Oblique", fontSize=6.5,
                         fillColor=TXT_STE, textAnchor="middle"))
            lines_from_top += 13
        d.add(String(cx, y + h - lines_from_top - 14,
                     name,
                     fontName="Helvetica-Bold", fontSize=8.5,
                     fillColor=TXT_HEAD, textAnchor="middle"))
        if sub:
            d.add(String(cx, y + h - lines_from_top - 26,
                         sub,
                         fontName="Helvetica", fontSize=7.0,
                         fillColor=TXT_SUB, textAnchor="middle"))

    def db_box(x, y, w, h, name, sub=""):
        """Database-table style box (grey header bar)."""
        d.add(Rect(x, y, w, h,
                   fillColor=COMP_BG, strokeColor=COMP_BD, strokeWidth=1.1))
        d.add(Rect(x, y + h - 17, w, 17,
                   fillColor=TAB_HDR, strokeColor=COMP_BD, strokeWidth=0.8))
        d.add(String(x + w / 2, y + h - 11,
                     name,
                     fontName="Helvetica-Bold", fontSize=8,
                     fillColor=TXT_HEAD, textAnchor="middle"))
        if sub:
            d.add(String(x + w / 2, y + h - 30,
                         sub,
                         fontName="Helvetica", fontSize=6.5,
                         fillColor=TXT_SUB, textAnchor="middle"))

    def arrowhead(x2, y2, dx, dy):
        length = (dx**2 + dy**2) ** 0.5
        if length < 0.5:
            return
        ux, uy = dx / length, dy / length
        hl, hw = 7, 3.5
        p1x = x2 - ux * hl - uy * hw
        p1y = y2 - uy * hl + ux * hw
        p2x = x2 - ux * hl + uy * hw
        p2y = y2 - uy * hl - ux * hw
        d.add(Polygon([x2, y2, p1x, p1y, p2x, p2y],
                      fillColor=ARROW_C, strokeColor=ARROW_C))

    def arr(x1, y1, x2, y2, label="", dashed=False, loff=(4, 3)):
        """Straight arrow."""
        dash = [5, 3] if dashed else None
        d.add(Line(x1, y1, x2, y2, strokeColor=ARROW_C, strokeWidth=1.2,
                   strokeDashArray=dash))
        arrowhead(x2, y2, x2 - x1, y2 - y1)
        if label:
            mx = (x1 + x2) / 2 + loff[0]
            my = (y1 + y2) / 2 + loff[1]
            d.add(String(mx, my, label,
                         fontName="Helvetica", fontSize=6.5,
                         fillColor=ARROW_L, textAnchor="start"))

    def bent_arr(pts, label="", dashed=False, lseg=0, loff=(4, 3)):
        """Multi-segment arrow. pts = [(x0,y0),(x1,y1),...]. Arrow at last point."""
        dash = [5, 3] if dashed else None
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            d.add(Line(x1, y1, x2, y2, strokeColor=ARROW_C, strokeWidth=1.2,
                       strokeDashArray=dash))
        lx, ly = pts[-1]
        px, py = pts[-2]
        arrowhead(lx, ly, lx - px, ly - py)
        if label:
            si = min(lseg, len(pts) - 2)
            mx = (pts[si][0] + pts[si + 1][0]) / 2 + loff[0]
            my = (pts[si][1] + pts[si + 1][1]) / 2 + loff[1]
            d.add(String(mx, my, label,
                         fontName="Helvetica", fontSize=6.5,
                         fillColor=ARROW_L, textAnchor="start"))

    def note(x, y, text):
        d.add(String(x, y, text, fontName="Helvetica-Oblique", fontSize=6,
                     fillColor=NOTELINE, textAnchor="start"))

    # ═══════════════════════════════════════════════════════════════════════════
    # ZONES
    # ═══════════════════════════════════════════════════════════════════════════

    zone(2,   318, 536, 172, "iOS App Layer")
    zone(2,   178, 536, 133, "FastAPI Backend  +  Celery Worker  +  Celery Beat")
    zone(2,   5,   253, 166, "Supabase PostgreSQL DB")
    zone(263, 5,   272, 166, "Firebase Cloud Messaging")

    # ═══════════════════════════════════════════════════════════════════════════
    # iOS COMPONENTS  (2 rows)
    # Row A  y=378..428  (h=50)
    # Row B  y=323..361  (h=38)
    # ═══════════════════════════════════════════════════════════════════════════
    # Column centres (4 cols, gap=6, each w=126):
    #   C1 x=8     C2 x=140    C3 x=272    C4 x=404
    comp( 8,  378, 126, 50, "AppDelegate",           "component", "ReelMindApp.swift")
    comp(140, 378, 126, 50, "NotifPermission",       "component", "Manager.swift")
    comp(272, 378, 126, 50, "ProfileAPI",            "component", ".swift")
    comp(404, 378, 130, 50, "ReelCategoryAPI",       "component", ".swift")

    comp( 8,  323, 196, 38, "AuthSession",           "component", "syncToken()")
    comp(210, 323, 196, 38, "CategoriseReelView",    "component", "SwiftUI sheet")

    # ═══════════════════════════════════════════════════════════════════════════
    # BACKEND COMPONENTS  (2 rows)
    # Row A  y=228..278  (h=50)
    # Row B  y=183..228  (h=45)
    # ═══════════════════════════════════════════════════════════════════════════
    comp( 8,  228, 162, 50, "profiles.py",           "endpoint",    "PATCH /fcm-token")
    comp(176, 228, 162, 50, "reels.py",              "endpoint",    "PATCH /category")
    comp(344, 228, 192, 50, "notifier.py",           "service",     "send_push_notification()")

    comp( 8,  183, 162, 40, "tasks.py",              "celery task", "process_reel()")
    comp(176, 183, 162, 40, "beat_tasks.py",         "beat task",   "expire_pending_categories()")

    # ═══════════════════════════════════════════════════════════════════════════
    # SUPABASE  (left bottom)
    # ═══════════════════════════════════════════════════════════════════════════
    db_box(12,  98, 233, 60, "profiles table",    "fcm_token  ·  fcm_token_updated_at")
    db_box(12,  22, 233, 68, "reels table",       "status  ·  suggested_categories  ·  confidence")

    # ═══════════════════════════════════════════════════════════════════════════
    # FIREBASE / FCM  (right bottom)
    # ═══════════════════════════════════════════════════════════════════════════
    db_box(273, 118, 252, 40, "Firebase Admin SDK",   "credentials.Certificate")
    db_box(273,  68, 252, 42, "FCM Server (Google)",  "HTTP v1 API")
    db_box(273,  14, 252, 46, "APNs Gateway",         "Apple Push Notification Service")

    # ═══════════════════════════════════════════════════════════════════════════
    # ARROWS
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # ── A. TOKEN REGISTRATION PATH ──────────────────────────────────────────
    # AppDelegate right  →  ProfileAPI left  (FCM token cache + upload trigger)
    arr(134, 403, 272, 403, "FCM token")

    # ProfileAPI bottom  →  profiles.py top  (PATCH /fcm-token)
    arr(335, 378, 89, 278, "PATCH /fcm-token", loff=(-88, 4))

    # profiles.py bottom  →  Supabase profiles top  (write token)
    arr(89, 228, 128, 158, "write fcm_token")

    # ── B. CELERY TASK TOKEN READ ────────────────────────────────────────────
    # tasks.py bottom-left  →  Supabase profiles (read fcm_token at pipeline start)
    bent_arr([(25, 183), (25, 170), (110, 158)],
             label="read fcm_token", lseg=1, loff=(3, 3))

    # ── C. CELERY PIPELINE → DB ──────────────────────────────────────────────
    # tasks.py bottom  →  Supabase reels (update status / confidence)
    bent_arr([(89, 183), (89, 90)],
             label="update status", loff=(3, 3))

    # reels.py bottom  →  Supabase reels (update after category PATCH)
    bent_arr([(257, 228), (257, 172), (165, 90)],
             label="update category", lseg=1, loff=(3, 3))

    # ── D. PUSH SEND PATH ────────────────────────────────────────────────────
    # tasks.py right  →  notifier.py left  (trigger push)
    arr(170, 203, 344, 260, "push trigger")

    # beat_tasks.py right  →  notifier.py left  (trigger push on timeout)
    arr(338, 203, 344, 248, "push trigger")

    # reels.py right  →  notifier.py left  (confirmation push after category set)
    arr(338, 253, 344, 270, "confirm push")

    # notifier.py bottom  →  Firebase Admin SDK top  (messaging.send())
    arr(440, 228, 399, 158, "messaging.send()")

    # Firebase Admin SDK  →  FCM Server
    arr(399, 118, 399, 110, "HTTP v1 API")

    # FCM Server  →  APNs Gateway
    arr(399, 68,  399, 60,  "route")

    # ── E. APNs PUSH DELIVERY → iOS  ────────────────────────────────────────
    # Route up the RIGHT side of the diagram (outside all zone boxes)
    # APNs right  →  up right edge  →  across top  →  ReelCategoryAPI top
    bent_arr(
        [(525, 37), (537, 37), (537, 478), (469, 478), (469, 428)],
        label="APNs push notification", lseg=2, loff=(-90, 4),
        dashed=True,
    )

    # ── F. USER RESPONSE PATH ────────────────────────────────────────────────
    # ReelCategoryAPI bottom  →  reels.py top  (PATCH /category)
    arr(469, 378, 257, 278, "PATCH /category", loff=(-76, 4))

    # ── G. PERMISSION FLOW (iOS-internal) ────────────────────────────────────
    # NotifPermManager right  →  AppDelegate left (grants permission)
    note(10, 370, "NotifPermManager calls UIApplication.registerForRemoteNotifications() on grant")
    note(10, 362, "AuthSession.syncToken() triggers ProfileAPI.uploadFCMToken() on login")
    note(10, 354, "CategoriseReelView uses ReelCategoryAPI.assignAsync() for in-app categorisation")

    return d

# ─── END-TO-END FLOW TABLE ────────────────────────────────────────────────────

def make_flow_table():
    headers = ["#", "Layer", "Action", "Outcome"]
    rows = [
        ["1", "iOS (Onboarding)", "User taps 'Grant Access' in OnboardingPermissionsView",
         "UNUserNotificationCenter.requestAuthorization() called"],
        ["2", "iOS (System)", "System permission dialog → Granted",
         "UIApplication.registerForRemoteNotifications() called"],
        ["3", "iOS (AppDelegate)", "didRegisterForRemoteNotificationsWithDeviceToken",
         "APNs token forwarded to Messaging.messaging().apnsToken"],
        ["4", "Firebase SDK (iOS)", "SDK exchanges APNs token for FCM token",
         "messaging(_:didReceiveRegistrationToken:) fires"],
        ["5", "iOS (AppDelegate)", "FCM token received",
         "Cached to UserDefaults('fcmToken'); if logged in → ProfileAPI.uploadFCMToken()"],
        ["6", "iOS (AuthSession)", "User logs in or session restored",
         "syncToken() calls ProfileAPI.uploadFCMToken(cached FCM token)"],
        ["7", "iOS → Backend", "PATCH /api/v1/profiles/fcm-token  {fcm_token: '...'}",
         "profiles row updated with fcm_token + fcm_token_updated_at"],
        ["8", "Backend (Celery)", "process_reel task runs pipeline Steps 15–20",
         "Fetches fcm_token from profiles table at task start"],
        ["9A", "Backend (Step 19)", "Confidence ≥ 0.70 → auto-assign",
         "Reel status → ready; send_push_notification('Reel saved!', 'Categorised as X')"],
        ["9B", "Backend (Step 19)", "Confidence < 0.70 → pending_category",
         "Reel status → pending_category; push with category_id='CATEGORISE' + suggestions"],
        ["9C", "Backend (Step 17)", "NoSignalError (no transcript, caption, hashtags)",
         "Reel status → uncategorised; push 'We couldn't categorise it'"],
        ["10", "Backend (notifier)", "send_push_notification() via Firebase Admin SDK",
         "_get_firebase_app() lazy init; messaging.send(_Message) dispatched"],
        ["11", "FCM Server (Google)", "Message delivered to device via APNs",
         "iOS receives push notification"],
        ["12A", "iOS (Notification)", "User taps CAT_0 or CAT_1 button",
         "ReelCategoryAPI.assign(reelId, suggestions[0 or 1])"],
        ["12B", "iOS (Notification)", "User taps 'Uncategorised' button",
         "ReelCategoryAPI.assign(reelId, nil)"],
        ["12C", "iOS (Notification)", "User taps 'Choose / Create Category' (.foreground)",
         "NotificationCenter.post(.categoriseReel); RootView opens CategoriseReelView"],
        ["13", "iOS → Backend", "PATCH /api/v1/reels/{reel_id}/category",
         "Backend sets category_id, status=ready; confirmation push sent back"],
        ["14", "Backend (Beat)", "expire_pending_categories() every 30 min",
         "Rows pending >1 hr → uncategorised; push 'Added to Uncategorised' per user"],
    ]
    col_colors = {
        "iOS (Onboarding)":     C_IOS_LIGHT,
        "iOS (System)":         C_IOS_LIGHT,
        "iOS (AppDelegate)":    C_IOS_LIGHT,
        "Firebase SDK (iOS)":   C_FCM_LIGHT,
        "iOS (AuthSession)":    C_IOS_LIGHT,
        "iOS → Backend":        C_BACKEND_LIGHT,
        "Backend (Celery)":     C_CELERY_LIGHT,
        "Backend (Step 19)":    C_CELERY_LIGHT,
        "Backend (Step 17)":    C_CELERY_LIGHT,
        "Backend (notifier)":   C_BACKEND_LIGHT,
        "FCM Server (Google)":  C_FCM_LIGHT,
        "iOS (Notification)":   C_IOS_LIGHT,
        "Backend (Beat)":       C_BEAT_LIGHT,
    }
    sty_hdr = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5,
                              textColor=C_WHITE, alignment=TA_CENTER)
    sty_num = ParagraphStyle("tn", fontName="Helvetica-Bold", fontSize=9,
                              textColor=C_HEADING, alignment=TA_CENTER)
    sty_lay = ParagraphStyle("tl", fontName="Helvetica-Bold", fontSize=8,
                              textColor=C_SUBHEADING)
    sty_act = ParagraphStyle("ta", fontName="Courier",         fontSize=7.5,
                              textColor=C_HEADING)
    sty_out = ParagraphStyle("to", fontName="Helvetica",       fontSize=8,
                              textColor=C_HEADING)

    table_data = [[Paragraph(h, sty_hdr) for h in headers]]
    for row in rows:
        num, layer, action, outcome = row
        bg = col_colors.get(layer, C_SECTION_BG)
        table_data.append([
            Paragraph(num, sty_num),
            Paragraph(layer, sty_lay),
            Paragraph(action, sty_act),
            Paragraph(outcome, sty_out),
        ])

    col_widths = [0.7*cm, 3.8*cm, 6.8*cm, 5.7*cm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  C_HEADING),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_WHITE, C_SECTION_BG]),
    ])
    # Colour the layer column cells
    for i, row in enumerate(rows, start=1):
        layer = row[1]
        bg = col_colors.get(layer, C_SECTION_BG)
        style.add("BACKGROUND", (1,i), (1,i), bg)
    t.setStyle(style)
    return t

# ─── BUILD DOCUMENT ──────────────────────────────────────────────────────────

OUTPUT = "/Users/deeptijain/Desktop/Deepti/Projects/ReelMind/FCM_Notification_Flow.pdf"

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=1.8*cm, rightMargin=1.8*cm,
    topMargin=1.8*cm, bottomMargin=1.8*cm,
    title="ReelMind — FCM Notification Flow",
    author="ReelMind Engineering",
)

story = []

# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE  — built with standard flowables so it sits inside the page frame
# ══════════════════════════════════════════════════════════════════════════════

def cover_band(text, bg, text_color=C_WHITE, font_size=28):
    """Full-width coloured banner cell."""
    data = [[Paragraph(text, ParagraphStyle("cb", fontName="Helvetica-Bold",
                                             fontSize=font_size, textColor=text_color,
                                             alignment=TA_CENTER))]]
    t = Table(data, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), bg),
        ("TOPPADDING",    (0,0), (-1,-1), 18),
        ("BOTTOMPADDING", (0,0), (-1,-1), 18),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    return t

# Dark header banner
story.append(cover_band("ReelMind", C_BG, C_WHITE, 42))
story.append(cover_band("FCM Push Notification", C_IOS, C_WHITE, 24))
story.append(cover_band("Architecture & Flow", colors.HexColor("#2A3A8C"), C_WHITE, 22))
story.append(sp(16))

story.append(Paragraph(
    "Complete engineering reference: iOS ↔ FastAPI ↔ Firebase ↔ Celery ↔ Supabase",
    ParagraphStyle("cs", fontName="Helvetica", fontSize=13, textColor=C_SUBHEADING, alignment=TA_CENTER)
))
story.append(sp(6))
story.append(Paragraph(
    "2026-05-19  ·  Internal Engineering Reference",
    ParagraphStyle("cd", fontName="Helvetica", fontSize=11, textColor=C_MUTED, alignment=TA_CENTER)
))
story.append(sp(28))

# Badge row
badge_data = [[
    Paragraph("<b>iOS Layer</b>",     ParagraphStyle("b1", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
    Paragraph("<b>Backend Layer</b>", ParagraphStyle("b2", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
    Paragraph("<b>Firebase / FCM</b>",ParagraphStyle("b3", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
    Paragraph("<b>Celery Tasks</b>",  ParagraphStyle("b4", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
    Paragraph("<b>Beat Tasks</b>",    ParagraphStyle("b5", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
    Paragraph("<b>Supabase DB</b>",   ParagraphStyle("b6", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE, alignment=TA_CENTER)),
]]
badge_t = Table(badge_data)
badge_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (0,0), C_IOS),
    ("BACKGROUND",    (1,0), (1,0), C_BACKEND),
    ("BACKGROUND",    (2,0), (2,0), C_FCM),
    ("BACKGROUND",    (3,0), (3,0), C_CELERY),
    ("BACKGROUND",    (4,0), (4,0), C_BEAT),
    ("BACKGROUND",    (5,0), (5,0), C_DB),
    ("TOPPADDING",    (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("RIGHTPADDING",  (0,0), (-1,-1), 6),
    ("ROUNDEDCORNERS",[4]),
]))
story.append(badge_t)
story.append(sp(32))

story.append(Paragraph(
    "Confidential — Engineering Use Only",
    ParagraphStyle("cf", fontName="Helvetica-Oblique", fontSize=10, textColor=C_MUTED, alignment=TA_CENTER)
))
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ══════════════════════════════════════════════════════════════════════════════
story.append(Paragraph("Table of Contents", h1))
story.append(hline(C_IOS, 2))
story.append(sp(4))

toc_items = [
    ("1", "System Architecture Overview",         "iOS · Backend · FCM · Supabase"),
    ("2", "iOS — Permission & Token Lifecycle",    "NotifPermManager · AppDelegate · AuthSession"),
    ("3", "Database — Token Storage",             "Migration · profiles table · fcm_token column"),
    ("4", "Backend — FCM Token Registration",     "ProfileAPI.swift · PATCH /fcm-token endpoint"),
    ("5", "Backend — Firebase Admin SDK Setup",   "config.py · notifier.py · _get_firebase_app()"),
    ("6", "Backend — Sending Notifications",      "send_push_notification() · _Message · APNs config"),
    ("7", "Celery Task — Notification Triggers",  "tasks.py Step 17 · Step 19 (auto / pending_category)"),
    ("8", "Celery Beat — Timeout Handler",        "beat_tasks.py · expire_pending_categories()"),
    ("9", "Backend — Category Choice Handler",    "reels.py PATCH /reels/{id}/category"),
    ("10","iOS — Notification Response Handling", "didReceive · ReelCategoryAPI · CategoriseReelView"),
    ("11","End-to-End Flow Table",                "14-step complete notification lifecycle"),
]
for num, title, sub in toc_items:
    row = [[
        Paragraph(num + ".", ParagraphStyle("tn2", fontName="Helvetica-Bold", fontSize=10,
                                             textColor=C_IOS, alignment=TA_CENTER)),
        Paragraph(f"<b>{title}</b><br/><font color='#6C757D' size='8'>{sub}</font>",
                  ParagraphStyle("te2", fontName="Helvetica", fontSize=10, leading=15,
                                 textColor=C_HEADING)),
    ]]
    t = Table(row, colWidths=[0.8*cm, None])
    t.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(hline(C_DIVIDER, 0.3))

story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — SYSTEM ARCHITECTURE OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("1", "System Architecture Overview", C_IOS))
story.append(sp(10))

story.append(Paragraph(
    "The ReelMind FCM notification system spans four physical layers: the iOS app, "
    "the FastAPI backend (with Celery workers and Beat scheduler), Firebase Cloud Messaging, "
    "and the Supabase PostgreSQL database. The diagram below shows all components and how "
    "they communicate.",
    body))
story.append(sp(8))

d = make_arch_diagram()
story.append(d)
story.append(sp(4))

# Arrow legend
leg_sty = ParagraphStyle("ls", fontName="Helvetica", fontSize=8, leading=13, textColor=C_HEADING)
leg_bold = ParagraphStyle("lb", fontName="Helvetica-Bold", fontSize=8, leading=13, textColor=C_HEADING)
legend_items = [
    ("────────►",  "Solid arrow = direct call / HTTP request / SDK invocation"),
    ("- - - - ►",  "Dashed arrow = APNs push delivery (external, device-to-device)"),
    ("[  ]",        "White box with component symbol (top-right) = iOS or Backend component"),
    ("▬▬▬  name",  "Grey-header box = database table or external service"),
    ("«stereotype»","Italic label in angle brackets = component role / type"),
]
leg_rows = [[
    Paragraph(sym,  ParagraphStyle("sym", fontName="Courier-Bold", fontSize=8,
                                    textColor=C_HEADING)),
    Paragraph(desc, leg_sty),
] for sym, desc in legend_items]
leg_t = Table(leg_rows, colWidths=[2.8*cm, None])
leg_t.setStyle(TableStyle([
    ("TOPPADDING",    (0,0), (-1,-1), 3),
    ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#F5F5F5")),
    ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
    ("INNERGRID",     (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
]))
story.append(Paragraph("<b>Diagram Legend</b>", h3))
story.append(leg_t)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — iOS PERMISSION & TOKEN LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("2", "iOS — Permission & Token Lifecycle", C_IOS))
story.append(sp(8))

story.append(Paragraph(
    "Before any FCM push can be delivered to the device, two things must happen: "
    "(1) the user must grant notification permission, and (2) the device must register "
    "with APNs, which causes Firebase to issue an FCM token. This token is then uploaded "
    "to the backend so it can target this device.",
    body))
story.append(sp(8))

# 2A — NotificationPermissionManager
story.append(Paragraph("2A · NotificationPermissionManager.swift", h2))
story.append(file_box("frontend/NotificationPermissionManager.swift",
                       "Manages UNUserNotificationCenter permission state. Observable, drives OnboardingPermissionsView UI.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "An <b>ObservableObject</b> with a single <code>status</code> property (<i>notDetermined / "
    "authorized / denied</i>). Exposes two async methods:", body))
story.append(bullet("<b>refresh()</b> — reads UNNotificationSettings without prompting. Called on task start in OnboardingPermissionsView."))
story.append(bullet("<b>requestOrOpenSettings()</b> — if .notDetermined: calls requestAuthorization(options: [.alert, .sound, .badge]). If granted, immediately calls UIApplication.shared.registerForRemoteNotifications(). If .denied: deep-links to iOS Settings.app."))
story.append(sp(5))
*clines, = code_block([
    "let granted = try await UNUserNotificationCenter.current()",
    "    .requestAuthorization(options: [.alert, .sound, .badge])",
    "if granted {",
    "    UIApplication.shared.registerForRemoteNotifications()",
    "}",
], "// NotificationPermissionManager.requestOrOpenSettings()")
for cl in clines:
    story.append(cl)
story.append(sp(8))

# 2B — AppDelegate
story.append(Paragraph("2B · AppDelegate (ReelMindApp.swift)", h2))
story.append(file_box("frontend/ReelMindApp.swift",
                       "UIApplicationDelegate + UNUserNotificationCenterDelegate + MessagingDelegate. Central hub for all FCM and push plumbing.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
story.append(Paragraph("<b>didFinishLaunchingWithOptions</b> does five things:", body))
for step in [
    "FirebaseApp.configure() — boots the Firebase SDK (reads GoogleService-Info.plist).",
    "Messaging.messaging().delegate = self — routes token-refresh callbacks here.",
    "UNUserNotificationCenter.current().delegate = self — routes foreground/tap callbacks here.",
    "Registers the CATEGORISE notification category with 4 action buttons (CAT_0, CAT_1, CHOOSE_IN_APP, UNCATEGORISED).",
    "If permission was already granted in a prior session, calls registerForRemoteNotifications() so the APNs/FCM token is refreshed.",
]:
    story.append(bullet(step))
story.append(sp(5))
*clines, = code_block([
    "// CATEGORISE category — iOS shows these as notification action buttons",
    "let categoriseActions: [UNNotificationAction] = [",
    "    UNNotificationAction(identifier: 'CAT_0',         title: 'Suggestion 1', options: []),",
    "    UNNotificationAction(identifier: 'CAT_1',         title: 'Suggestion 2', options: []),",
    "    UNNotificationAction(identifier: 'CHOOSE_IN_APP', title: 'Choose / Create Category',",
    "                         options: [.foreground]),",
    "    UNNotificationAction(identifier: 'UNCATEGORISED', title: 'Uncategorised', options: []),",
    "]",
    "let categoriseCategory = UNNotificationCategory(",
    "    identifier: 'CATEGORISE', actions: categoriseActions,",
    "    intentIdentifiers: [], options: [])",
    "UNUserNotificationCenter.current().setNotificationCategories([categoriseCategory])",
])
for cl in clines:
    story.append(cl)
story.append(sp(5))

story.append(Paragraph("<b>didRegisterForRemoteNotificationsWithDeviceToken</b>", h3))
story.append(Paragraph(
    "APNs delivers a device token (binary Data). AppDelegate forwards this to the "
    "Firebase SDK: <code>Messaging.messaging().apnsToken = deviceToken</code>. "
    "Firebase then internally exchanges this for an FCM registration token.", body))
story.append(sp(4))

story.append(Paragraph("<b>messaging(_:didReceiveRegistrationToken:)</b> — MessagingDelegate", h3))
story.append(Paragraph(
    "Called by Firebase SDK whenever a new FCM token is available (first launch, "
    "token refresh, or app reinstall). Two actions:", body))
story.append(bullet("Cache the token to UserDefaults.standard key 'fcmToken' for later use (e.g. if login hasn't happened yet)."))
story.append(bullet("If the user's auth token already exists in App Group defaults (user was logged in), upload immediately via ProfileAPI.uploadFCMToken(token)."))
story.append(sp(4))
*clines, = code_block([
    "func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {",
    "    guard let token = fcmToken else { return }",
    "    UserDefaults.standard.set(token, forKey: 'fcmToken')   // cache",
    "    let groupDefaults = UserDefaults(suiteName: AppConfig.appGroupID)",
    "    if groupDefaults?.string(forKey: AppConfig.authTokenKey) != nil {",
    "        ProfileAPI.uploadFCMToken(token)  // logged in — upload now",
    "    }",
    "}",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

# 2C — AuthSession
story.append(Paragraph("2C · AuthSession.swift", h2))
story.append(file_box("frontend/AuthSession.swift",
                       "Manages Supabase JWT session. Also handles FCM token upload on login/session restore.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "AuthSession's <b>syncToken(_:)</b> is called whenever the Supabase auth state changes "
    "(sign-in, sign-out, token refresh). When a JWT is present, it also checks for a "
    "cached FCM token and uploads it:", body))
story.append(bullet("Mirrors the Supabase JWT to App Group UserDefaults (key: supabaseAuthToken) so the Share Extension and ProfileAPI/ReelCategoryAPI can read it."))
story.append(bullet("If fcmToken exists in UserDefaults.standard (cached by AppDelegate), calls ProfileAPI.uploadFCMToken(fcmToken). This handles the race where the FCM token arrived before the user logged in."))
story.append(sp(4))
*clines, = code_block([
    "// AuthSession.syncToken",
    "if let token = token {",
    "    defaults.set(token, forKey: AppConfig.authTokenKey)",
    "    if let fcmToken = UserDefaults.standard.string(forKey: 'fcmToken') {",
    "        ProfileAPI.uploadFCMToken(fcmToken)  // upload cached token post-login",
    "    }",
    "}",
])
for cl in clines:
    story.append(cl)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DATABASE — TOKEN STORAGE
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("3", "Database — FCM Token Storage", C_DB))
story.append(sp(8))

story.append(Paragraph(
    "The FCM token is stored in the <code>public.profiles</code> table — one row per user, "
    "one token per device (MVP; multi-device would need a separate devices table).",
    body))
story.append(sp(6))

story.append(Paragraph("Migration File", h2))
story.append(file_box("supabase/migrations/20260505000001_add_fcm_token_to_profiles.sql",
                       "Adds fcm_token and fcm_token_updated_at to profiles. Creates a partial index for non-NULL tokens.",
                       C_DB, C_DB_LIGHT))
story.append(sp(5))
*clines, = code_block([
    "alter table public.profiles",
    "  add column if not exists fcm_token text,",
    "  add column if not exists fcm_token_updated_at timestamptz;",
    "",
    "-- Partial index: only index rows that actually have a token",
    "create index if not exists idx_profiles_fcm_token",
    "  on public.profiles(fcm_token)",
    "  where fcm_token is not null;",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("Schema context: profiles table", h2))
schema_data = [
    [Paragraph("<b>Column</b>", ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Type</b>",   ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Notes</b>",  ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("id", code_p), Paragraph("uuid", code_p), Paragraph("FK → auth.users. PK.", body_sm)],
    [Paragraph("fcm_token", code_p), Paragraph("text", code_p), Paragraph("FCM registration token. NULL until device registers.", body_sm)],
    [Paragraph("fcm_token_updated_at", code_p), Paragraph("timestamptz", code_p), Paragraph("Timestamp of last token write. Useful for token staleness checks.", body_sm)],
]
schema_t = Table(schema_data, colWidths=[4.5*cm, 3*cm, None])
schema_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_DB),
    ("BACKGROUND",    (0,1), (-1,-1), C_DB_LIGHT),
    ("GRID",          (0,0), (-1,-1), 0.5, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(schema_t)
story.append(sp(6))
story.append(Paragraph(
    "<b>Note:</b> The backend reads this column in <i>tasks.py</i>, <i>beat_tasks.py</i>, "
    "and <i>api/v1/reels.py</i> using the <b>service role key</b> (bypasses RLS) to fetch "
    "the fcm_token before calling send_push_notification().",
    note_style))
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BACKEND: FCM TOKEN REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("4", "Backend — FCM Token Registration", C_BACKEND))
story.append(sp(8))

story.append(Paragraph("4A · ProfileAPI.swift (iOS → Backend call)", h2))
story.append(file_box("frontend/ProfileAPI.swift",
                       "Fire-and-forget PATCH call to upload the device FCM token. Reads auth token from App Group defaults.",
                       C_BACKEND, C_BACKEND_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "A static enum with a single method <code>uploadFCMToken(_:)</code>. It reads the Supabase "
    "JWT from the App Group shared defaults (so it also works if called from the Share Extension "
    "context), builds a <code>PATCH</code> request, and fires it as a background URLSession task. "
    "Errors are logged but never surfaced to the UI — the push flow is advisory.",
    body))
story.append(sp(4))
*clines, = code_block([
    "let url = AppConfig.backendBaseURL",
    "    .appendingPathComponent('api/v1/profiles/fcm-token')",
    "var request = URLRequest(url: url)",
    "request.httpMethod = 'PATCH'",
    "request.setValue('Bearer \\(authToken)', forHTTPHeaderField: 'Authorization')",
    "request.httpBody = try? JSONEncoder().encode(['fcm_token': token])",
    "URLSession.shared.dataTask(with: request) { ... }.resume()",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("4B · FCMTokenRequest schema (schemas/reel.py)", h2))
story.append(file_box("backend/schemas/reel.py",
                       "Pydantic model — validates that the request body contains a non-empty fcm_token string.",
                       C_BACKEND, C_BACKEND_LIGHT))
story.append(sp(5))
*clines, = code_block([
    "class FCMTokenRequest(BaseModel):",
    '    """Body for PATCH /api/v1/profiles/fcm-token."""',
    "    fcm_token: str   # Pydantic rejects missing/null → 422",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("4C · update_fcm_token endpoint (api/v1/profiles.py)", h2))
story.append(file_box("backend/api/v1/profiles.py",
                       "PATCH /api/v1/profiles/fcm-token — writes token to profiles table. JWT-authenticated.",
                       C_BACKEND, C_BACKEND_LIGHT))
story.append(sp(5))
*clines, = code_block([
    "@router.patch('/fcm-token', status_code=status.HTTP_200_OK)",
    "async def update_fcm_token(",
    "    payload: FCMTokenRequest,",
    "    user_id: str = Depends(get_current_user_id),  # JWT → user UUID",
    "):",
    "    supabase = get_supabase()  # service role key — bypasses RLS",
    "    supabase.table('profiles').update({",
    "        'fcm_token': payload.fcm_token,",
    "        'fcm_token_updated_at': datetime.now(timezone.utc).isoformat(),",
    "    }).eq('id', user_id).execute()",
    "    return {'status': 'ok'}",
])
for cl in clines:
    story.append(cl)
story.append(sp(4))
story.append(Paragraph(
    "Auth dependency <code>get_current_user_id</code> (in <code>api/deps.py</code>) calls "
    "<code>supabase.auth.get_user(token)</code> to verify the JWT and extract the UUID. "
    "An invalid token raises HTTP 401 before the handler runs.",
    note_style))
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — FIREBASE ADMIN SDK SETUP
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("5", "Backend — Firebase Admin SDK Setup", C_FCM))
story.append(sp(8))

story.append(Paragraph("5A · config.py — Environment Variable", h2))
story.append(file_box("backend/config.py",
                       "Central config class. FIREBASE_SERVICE_ACCOUNT_JSON is the base64-encoded service account JSON.",
                       C_FCM, C_FCM_LIGHT))
story.append(sp(5))
*clines, = code_block([
    "# Firebase Admin SDK service account (base64-encoded JSON) — Step 22 FCM push",
    "FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')",
    "",
    "# FCM_SERVER_KEY — legacy field, kept for reference but unused",
    "FCM_SERVER_KEY = os.getenv('FCM_SERVER_KEY')",
])
for cl in clines:
    story.append(cl)
story.append(sp(5))

how_data = [
    [Paragraph("<b>How to set this in production (Render)</b>",
               ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9, textColor=C_FCM))],
    [Paragraph(
        "1. Download the Firebase service account JSON from Firebase Console → Project Settings → "
        "Service Accounts → Generate New Private Key.<br/>"
        "2. Base64-encode it: <code>base64 -i service-account.json | tr -d '\\n'</code><br/>"
        "3. In Render dashboard → reelmind-api service → Environment → add env var "
        "<code>FIREBASE_SERVICE_ACCOUNT_JSON</code> with the encoded string.",
        ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=14, textColor=C_HEADING))],
]
how_t = Table(how_data, colWidths=[None])
how_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_FCM_LIGHT),
    ("BACKGROUND",    (0,1), (-1,-1), colors.HexColor("#FFFBE0")),
    ("TOPPADDING",    (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ("LEFTPADDING",   (0,0), (-1,-1), 10),
    ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ("BOX",           (0,0), (-1,-1), 1, C_FCM_MID),
]))
story.append(how_t)
story.append(sp(8))

story.append(Paragraph("5B · _get_firebase_app() — Lazy Init (notifier.py)", h2))
story.append(file_box("backend/services/notifier.py",
                       "Lazily initializes Firebase Admin SDK. Returns None (graceful no-op) if config is missing.",
                       C_FCM, C_FCM_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "Uses a module-level singleton <code>_firebase_app</code>. On the first call, it decodes "
    "the base64 service account JSON, creates a <code>credentials.Certificate</code>, and calls "
    "<code>firebase_admin.initialize_app(cred)</code>. Subsequent calls return the cached app.",
    body))
story.append(sp(4))
*clines, = code_block([
    "_firebase_app: firebase_admin.App | None = None",
    "",
    "def _get_firebase_app() -> firebase_admin.App | None:",
    "    global _firebase_app",
    "    if _firebase_app is not None:",
    "        return _firebase_app                    # already initialized",
    "    cfg = get_config()",
    "    if not cfg.FIREBASE_SERVICE_ACCOUNT_JSON:",
    "        logger.warning('FCM disabled — no service account JSON')",
    "        return None                             # graceful no-op",
    "    service_account = json.loads(base64.b64decode(cfg.FIREBASE_SERVICE_ACCOUNT_JSON))",
    "    cred = credentials.Certificate(service_account)",
    "    _firebase_app = firebase_admin.initialize_app(cred)",
    "    return _firebase_app",
])
for cl in clines:
    story.append(cl)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — SENDING NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("6", "Backend — Sending Notifications", C_BACKEND))
story.append(sp(8))

story.append(Paragraph("6A · send_push_notification() — Public API", h2))
story.append(file_box("backend/services/notifier.py",
                       "Non-fatal push wrapper. Any failure is logged and returns False. Never raises.",
                       C_BACKEND, C_BACKEND_LIGHT))
story.append(sp(5))

sig_data = [
    [Paragraph("<b>Parameter</b>", ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Type</b>",      ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Purpose</b>",   ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("fcm_token",    code_p), Paragraph("str | None", code_p),
     Paragraph("Target device token. None → skip silently.", body_sm)],
    [Paragraph("title",        code_p), Paragraph("str", code_p),
     Paragraph("Notification title text.", body_sm)],
    [Paragraph("body",         code_p), Paragraph("str", code_p),
     Paragraph("Notification body / subtitle text.", body_sm)],
    [Paragraph("data",         code_p), Paragraph("dict[str,str] | None", code_p),
     Paragraph("Optional key-value data payload (reel_id, status, suggestions JSON).", body_sm)],
    [Paragraph("category_id",  code_p), Paragraph("str | None", code_p),
     Paragraph("iOS UNNotificationCategory ID. 'CATEGORISE' → shows action buttons.", body_sm)],
    [Paragraph("→ returns",    code_p), Paragraph("bool", code_p),
     Paragraph("True = sent successfully. False = skipped or any error.", body_sm)],
]
sig_t = Table(sig_data, colWidths=[3.5*cm, 3.5*cm, None])
sig_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_BACKEND),
    ("BACKGROUND",    (0,1), (-1,-1), C_BACKEND_LIGHT),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_BACKEND_LIGHT, C_WHITE]),
    ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(sig_t)
story.append(sp(6))

story.append(Paragraph("6B · _Message and APNs config dataclasses", h2))
story.append(Paragraph(
    "Rather than using <code>firebase_admin.messaging.Message</code> directly (which is a "
    "MagicMock in tests), the code defines lightweight <code>@dataclass</code> stand-ins "
    "(<code>_Message</code>, <code>_APNSConfig</code>, <code>_APNSPayload</code>, <code>_Aps</code>). "
    "These hold real attribute values so tests can inspect them after <code>messaging.send()</code> "
    "is mocked.", body))
story.append(sp(4))
*clines, = code_block([
    "# _Aps carries the iOS category identifier → shows action buttons",
    "@dataclasses.dataclass",
    "class _Aps:           category: str",
    "",
    "@dataclasses.dataclass",
    "class _APNSPayload:   aps: _Aps",
    "",
    "@dataclasses.dataclass",
    "class _APNSConfig:    payload: _APNSPayload",
    "",
    "@dataclasses.dataclass",
    "class _Message:",
    "    notification: object   # messaging.Notification(title, body)",
    "    data: dict             # {'reel_id': ..., 'status': ..., 'suggestions': ...}",
    "    apns: Optional[object] # None unless category_id is provided",
    "    token: str             # FCM registration token",
])
for cl in clines:
    story.append(cl)
story.append(sp(6))

story.append(Paragraph("6C · CATEGORISE notification — what the user sees", h2))
story.append(Paragraph(
    "When <code>category_id='CATEGORISE'</code> is passed to <code>send_push_notification()</code>, "
    "an <code>_APNSConfig</code> object is attached with <code>aps.category = 'CATEGORISE'</code>. "
    "iOS matches this identifier to the registered <code>UNNotificationCategory</code> (set up in "
    "AppDelegate) and shows the four action buttons below the notification banner.",
    body))
story.append(sp(4))

btn_data = [
    [Paragraph("<b>Button Identifier</b>", ParagraphStyle("bh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Label</b>",             ParagraphStyle("bh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Behaviour</b>",         ParagraphStyle("bh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("CAT_0",         code_p), Paragraph("Suggestion 1", body_sm),
     Paragraph("Calls ReelCategoryAPI.assign(reelId, suggestions[0])", body_sm)],
    [Paragraph("CAT_1",         code_p), Paragraph("Suggestion 2", body_sm),
     Paragraph("Calls ReelCategoryAPI.assign(reelId, suggestions[1])", body_sm)],
    [Paragraph("CHOOSE_IN_APP", code_p), Paragraph("Choose / Create Category", body_sm),
     Paragraph("Foreground action → app opens CategoriseReelView sheet", body_sm)],
    [Paragraph("UNCATEGORISED", code_p), Paragraph("Uncategorised", body_sm),
     Paragraph("Calls ReelCategoryAPI.assign(reelId, nil) → status = uncategorised", body_sm)],
]
btn_t = Table(btn_data, colWidths=[3.5*cm, 4*cm, None])
btn_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_IOS),
    ("BACKGROUND",    (0,1), (-1,-1), C_IOS_LIGHT),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_IOS_LIGHT, C_WHITE]),
    ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(btn_t)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — CELERY TASK NOTIFICATION TRIGGERS
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("7", "Celery Task — Notification Triggers", C_CELERY))
story.append(sp(8))

story.append(file_box("backend/workers/tasks.py",
                       "process_reel Celery task. Runs the full ingestion pipeline. Three FCM push trigger points.",
                       C_CELERY, C_CELERY_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "At the start of <code>process_reel</code>, the task fetches the user's FCM token "
    "from the <code>profiles</code> table. This is done once and stored in <code>_fcm_token</code>. "
    "A failure here is non-fatal — the pipeline continues, and notifications are silently skipped "
    "if the token is None.",
    body))
story.append(sp(5))
*clines, = code_block([
    "# FCM token — fetched once at pipeline start (non-critical)",
    "_fcm_token: str | None = None",
    "try:",
    "    _profile = supabase.table('profiles')",
    "        .select('fcm_token')",
    "        .eq('id', reel_data['user_id'])",
    "        .single().execute()",
    "    if _profile.data:",
    "        _fcm_token = _profile.data.get('fcm_token')",
    "except Exception as exc:",
    "    log.warning('could not fetch fcm_token | %s', exc)",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("Trigger Point 1 — Step 17: NoSignalError (no content)", h2))
story.append(Paragraph(
    "If all three signals (transcript, caption, hashtags) are empty, "
    "<code>build_classification_signal()</code> raises <code>NoSignalError</code>. "
    "The pipeline marks the reel <b>uncategorised</b> and sends a simple informational push.",
    body))
story.append(sp(4))
*clines, = code_block([
    "except NoSignalError:",
    "    supabase.table('reels').update({'status': 'uncategorised'}).eq('id', reel_id).execute()",
    "    send_push_notification(",
    "        fcm_token=_fcm_token,",
    "        title='Reel saved',",
    "        body='We couldn\\'t categorise it — no audio or caption found',",
    "        data={'reel_id': reel_id, 'status': 'uncategorised'},",
    "    )                    # no category_id → no action buttons",
    "    return {'reel_id': reel_id, 'status': 'uncategorised'}",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("Trigger Point 2 — Step 19: High confidence → auto-assign", h2))
story.append(Paragraph(
    "If the Llama classifier returns confidence ≥ 0.70 and the category exists in the DB, "
    "the reel is automatically assigned. A simple success push is sent (no action buttons needed).",
    body))
story.append(sp(4))
*clines, = code_block([
    "_CONFIDENCE_THRESHOLD = 0.70",
    "",
    "if classification.confidence >= _CONFIDENCE_THRESHOLD and resolved_category_id:",
    "    supabase.table('reels').update({",
    "        'category_id': resolved_category_id,",
    "        'confidence': classification.confidence,",
    "        'status': 'ready',",
    "    }).eq('id', reel_id).execute()",
    "    send_push_notification(",
    "        fcm_token=_fcm_token,",
    "        title='Reel saved!',",
    "        body=f'Categorised as {classification.category}',",
    "        data={'reel_id': reel_id, 'status': 'ready'},",
    "    )                    # no category_id → no action buttons",
])
for cl in clines:
    story.append(cl)
story.append(sp(8))

story.append(Paragraph("Trigger Point 3 — Step 19: Low confidence → pending_category", h2))
story.append(Paragraph(
    "If confidence < 0.70 (or the top category is not in the DB map), the reel enters "
    "<b>pending_category</b> status. The push includes up to 3 suggestions as a JSON string "
    "in the <code>data</code> payload, and <code>category_id='CATEGORISE'</code> to trigger "
    "the action buttons on iOS.",
    body))
story.append(sp(4))
*clines, = code_block([
    "suggestions = [classification.category] + classification.alternatives[:2]",
    "supabase.table('reels').update({",
    "    'status': 'pending_category',",
    "    'suggested_categories': suggestions,",
    "    'confidence': classification.confidence,",
    "}).eq('id', reel_id).execute()",
    "",
    "send_push_notification(",
    "    fcm_token=_fcm_token,",
    "    title='Help us categorise this reel',",
    "    body='Your reel is saved — which fits best? Ignoring saves it to Uncategorised.',",
    "    data={",
    "        'reel_id': reel_id,",
    "        'suggestions': json.dumps(suggestions),  # JSON string — parsed by iOS",
    "    },",
    "    category_id='CATEGORISE',   # <-- triggers action buttons on iOS",
    ")",
])
for cl in clines:
    story.append(cl)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — BEAT TASK: TIMEOUT HANDLER
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("8", "Celery Beat — Timeout Handler", C_BEAT))
story.append(sp(8))

story.append(file_box("backend/workers/beat_tasks.py",
                       "Scheduled Celery Beat task. Runs every 30 minutes. Expires pending_category reels after 1 hour.",
                       C_BEAT, C_BEAT_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "When a user doesn't respond to the <i>CATEGORISE</i> action notification within "
    "<b>1 hour</b>, this Beat task automatically moves the reel to <b>uncategorised</b> "
    "and sends a final confirmation push. It runs every 30 minutes via Celery Beat.",
    body))
story.append(sp(5))

beat_info = [
    [Paragraph("<b>Constant</b>",             ParagraphStyle("bi", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Value</b>",                ParagraphStyle("bi", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Meaning</b>",              ParagraphStyle("bi", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("PENDING_CATEGORY_TIMEOUT_HOURS", code_p), Paragraph("1", code_p),
     Paragraph("Rows older than 1 hour get expired.", body_sm)],
    [Paragraph("Beat schedule interval", code_p), Paragraph("30 min", code_p),
     Paragraph("Task runs twice per hour. Worst-case latency: 30 min after timeout.", body_sm)],
]
beat_t = Table(beat_info, colWidths=[5*cm, 2*cm, None])
beat_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_BEAT),
    ("BACKGROUND",    (0,1), (-1,-1), C_BEAT_LIGHT),
    ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(beat_t)
story.append(sp(6))

*clines, = code_block([
    "def expire_pending_categories() -> dict:",
    "    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)",
    "",
    "    # Single bulk UPDATE — the .eq('status','pending_category') guard ensures",
    "    # rows already resolved by the user (via PATCH /category) are skipped.",
    "    result = supabase.table('reels')",
    "        .update({'status': 'uncategorised', 'suggested_categories': []})",
    "        .eq('status', 'pending_category')",
    "        .lt('updated_at', cutoff.isoformat())",
    "        .execute()",
    "",
    "    for row in (result.data or []):",
    "        profile = supabase.table('profiles').select('fcm_token')",
    "            .eq('id', row['user_id']).maybe_single().execute()",
    "        fcm_token = (profile.data or {}).get('fcm_token')",
    "        send_push_notification(",
    "            fcm_token=fcm_token,",
    "            title='Reel saved',",
    "            body='Added to Uncategorised — you can move it anytime',",
    "            data={'reel_id': row['id'], 'status': 'uncategorised'},",
    "        )",
])
for cl in clines:
    story.append(cl)
story.append(sp(6))
story.append(Paragraph(
    "<b>Concurrency safety:</b> Because the UPDATE filters on <code>status='pending_category'</code>, "
    "a user who tapped a button <i>between</i> the cutoff check and the bulk UPDATE will already "
    "have their row at status='ready' or 'uncategorised', so the update will skip it. No double "
    "notification can occur.",
    note_style))
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — BACKEND: CATEGORY CHOICE HANDLER
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("9", "Backend — Category Choice Handler", C_BACKEND))
story.append(sp(8))

story.append(file_box("backend/api/v1/reels.py",
                       "PATCH /api/v1/reels/{reel_id}/category — handles button taps and in-app category assignment.",
                       C_BACKEND, C_BACKEND_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "This endpoint is called in two scenarios: (1) the iOS notification action handler "
    "(<code>ReelCategoryAPI.assign()</code>) fires it in the background when the user taps "
    "a button, and (2) <code>CategoriseReelView</code> fires the async variant when the user "
    "selects or creates a category in-app.",
    body))
story.append(sp(5))

# Path A / B table
path_data = [
    [Paragraph("<b>Path</b>",       ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Condition</b>",  ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>DB update</b>",  ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Push sent</b>",  ParagraphStyle("ph", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("A — Pick category", body_sm),
     Paragraph("category_name is a string", body_sm),
     Paragraph("category_id set, status=ready, confidence=1.0, suggested_categories=[]", body_sm),
     Paragraph("'Reel categorised!' + category name", body_sm)],
    [Paragraph("B — Skip", body_sm),
     Paragraph("category_name is null", body_sm),
     Paragraph("status=uncategorised, suggested_categories=[]", body_sm),
     Paragraph("'Reel saved — Added to Uncategorised'", body_sm)],
    [Paragraph("Auto-create", body_sm),
     Paragraph("Category name not found in DB", body_sm),
     Paragraph("New row inserted into categories; then Path A", body_sm),
     Paragraph("Same as Path A", body_sm)],
]
path_t = Table(path_data, colWidths=[3*cm, 3.5*cm, 5*cm, None])
path_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_BACKEND),
    ("BACKGROUND",    (0,1), (-1,1),  C_BACKEND_LIGHT),
    ("BACKGROUND",    (0,2), (-1,2),  C_WHITE),
    ("BACKGROUND",    (0,3), (-1,3),  C_BACKEND_LIGHT),
    ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(path_t)
story.append(sp(6))

story.append(Paragraph("Guards and edge-case handling:", h3))
for item in [
    "<b>404</b> — reel does not exist or does not belong to this user.",
    "<b>409 Conflict</b> — reel is already resolved (status ≠ pending_category). Prevents double-categorisation.",
    "<b>422</b> — empty category_name string after stripping whitespace.",
    "<b>Case insensitivity</b> — name is title-cased on input so 'travel vlogs' → 'Travel Vlogs' and matches existing categories case-insensitively.",
]:
    story.append(bullet(item))
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — iOS NOTIFICATION RESPONSE HANDLING
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("10", "iOS — Notification Response Handling", C_IOS))
story.append(sp(8))

story.append(Paragraph("10A · AppDelegate.didReceive(_:) — action handler", h2))
story.append(file_box("frontend/ReelMindApp.swift",
                       "UNUserNotificationCenterDelegate: routes each action button tap to the correct API call.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
*clines, = code_block([
    "func userNotificationCenter(_ center: UNUserNotificationCenter,",
    "    didReceive response: UNNotificationResponse, ...) {",
    "    let userInfo = response.notification.request.content.userInfo",
    "    guard let reelId = userInfo['reel_id'] as? String else { return }",
    "    let suggestions = Self.parseSuggestions(from: userInfo) // decode JSON",
    "",
    "    switch response.actionIdentifier {",
    "    case 'CAT_0' where suggestions.count > 0:",
    "        ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[0])",
    "    case 'CAT_1' where suggestions.count > 1:",
    "        ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[1])",
    "    case 'UNCATEGORISED':",
    "        ReelCategoryAPI.assign(reelId: reelId, categoryName: nil)",
    "    case 'CHOOSE_IN_APP':",
    "        NotificationCenter.default.post(name: .categoriseReel,",
    "            object: nil, userInfo: ['reel_id': reelId, 'suggestions': suggestions])",
    "    default: break",
    "    }",
    "}",
])
for cl in clines:
    story.append(cl)
story.append(sp(4))
story.append(Paragraph(
    "<code>parseSuggestions(from:)</code> decodes the JSON string stored in the push "
    "<code>data.suggestions</code> field back into a <code>[String]</code> array, "
    "making it available for the button tap handlers.",
    body))
story.append(sp(8))

story.append(Paragraph("10B · ReelCategoryAPI.swift — background PATCH", h2))
story.append(file_box("frontend/ReelCategoryAPI.swift",
                       "Fire-and-forget assign() + async assignAsync(). Both PATCH /api/v1/reels/{id}/category.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
story.append(Paragraph(
    "Two method variants serve different call sites:", body))
story.append(bullet("<b>assign(reelId:categoryName:)</b> — called from the notification action handler. Fire-and-forget URLSession.dataTask. Errors logged to console only."))
story.append(bullet("<b>assignAsync(reelId:categoryName:)</b> — called from CategoriseReelView. Returns async, throws on network error or non-2xx HTTP. Enables showing an error alert in the UI."))
story.append(sp(4))
story.append(Paragraph(
    "Both variants read the Supabase JWT from <code>AppConfig.appGroupID</code> App Group "
    "UserDefaults and send it as a <code>Bearer</code> header. If no auth token is present, "
    "the call is silently skipped (the share extension context may not have a session).",
    body))
story.append(sp(8))

story.append(Paragraph("10C · CategoriseReelView.swift — in-app category picker", h2))
story.append(file_box("frontend/CategoriseReelView.swift",
                       "SwiftUI sheet opened when user taps 'Choose / Create Category'. Shows thumbnail, suggestions, all categories.",
                       C_IOS, C_IOS_LIGHT))
story.append(sp(5))
story.append(Paragraph("Shown when <code>NotificationCenter.post(.categoriseReel)</code> fires (from CHOOSE_IN_APP button) or when RootView routes to it. Features:", body))
for item in [
    "Fetches reel <code>thumbnail_url</code> and <code>caption</code> from Supabase directly (using anon key + RLS).",
    "Shows AI suggestions as tappable chips at the top.",
    "Lists all user categories from the <code>categories</code> table.",
    "Allows creating a new category inline — passes the new name to <code>assignAsync</code> which auto-creates it on the backend.",
    "Toolbar 'Skip' button calls <code>assign(nil)</code> → moves to Uncategorised.",
    "Shows an error alert if the network call fails.",
]:
    story.append(bullet(item))
story.append(sp(8))

story.append(Paragraph("10D · Notification.Name.categoriseReel — internal routing", h2))
story.append(Paragraph(
    "Defined in <code>ReelMindApp.swift</code> as an <code>extension on Notification.Name</code>. "
    "Posted by AppDelegate when CHOOSE_IN_APP is tapped; observed by <code>RootView</code> to "
    "present <code>CategoriseReelView</code> as a sheet with the reel_id and suggestions from "
    "the notification payload.",
    body))
story.append(sp(4))
*clines, = code_block([
    "extension Notification.Name {",
    "    static let categoriseReel = Notification.Name('categoriseReel')",
    "}",
    "",
    "// RootView listens:",
    ".onReceive(NotificationCenter.default.publisher(for: .categoriseReel)) { notif in",
    "    if let reelId = notif.userInfo?['reel_id'] as? String {",
    "        categoriseTarget = CategoriseTarget(reelId: reelId, suggestions: suggestions)",
    "    }",
    "}",
])
for cl in clines:
    story.append(cl)
story.append(pb())

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — END-TO-END FLOW TABLE
# ══════════════════════════════════════════════════════════════════════════════
story.append(section_header("11", "End-to-End FCM Flow — 14-Step Table", C_HEADING))
story.append(sp(8))
story.append(Paragraph(
    "The table below traces a single reel from first launch through categorisation. "
    "Each row is one discrete step — the layer column is colour-coded to match the "
    "architecture diagram in Section 1.",
    body))
story.append(sp(8))
story.append(make_flow_table())
story.append(sp(10))

# Status summary
status_data = [
    [Paragraph("<b>Status</b>", ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Set by</b>", ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE)),
     Paragraph("<b>Push notification sent</b>", ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=9, textColor=C_WHITE))],
    [Paragraph("queued",          code_p), Paragraph("POST /reels (API)", body_sm), Paragraph("None", body_sm)],
    [Paragraph("processing",      code_p), Paragraph("tasks.py start",    body_sm), Paragraph("None", body_sm)],
    [Paragraph("ready",           code_p), Paragraph("tasks.py Step 19 (auto) OR PATCH /category", body_sm), Paragraph("'Reel saved!' / 'Reel categorised!'", body_sm)],
    [Paragraph("pending_category",code_p), Paragraph("tasks.py Step 19 (low conf)", body_sm), Paragraph("'Help us categorise' with CATEGORISE action buttons", body_sm)],
    [Paragraph("uncategorised",   code_p), Paragraph("tasks.py Step 17 / Beat / PATCH nil", body_sm), Paragraph("'Reel saved — Added to Uncategorised'", body_sm)],
    [Paragraph("failed",          code_p), Paragraph("tasks.py on non-retryable error", body_sm), Paragraph("None", body_sm)],
]
status_t = Table(status_data, colWidths=[4*cm, 5*cm, None])
status_t.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_HEADING),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_SECTION_BG, C_WHITE]),
    ("BACKGROUND",    (0,3), (0,3),   C_CELERY_LIGHT),
    ("BACKGROUND",    (0,5), (0,5),   C_DB_LIGHT),
    ("GRID",          (0,0), (-1,-1), 0.4, C_DIVIDER),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
]))
story.append(Paragraph("Reel status transitions and their associated push notifications:", h3))
story.append(status_t)

# ─── BUILD ────────────────────────────────────────────────────────────────────
doc.build(story)
print(f"PDF written to: {OUTPUT}")
