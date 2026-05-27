# -*- coding: utf-8 -*-
"""
OGSA Auditorias - PDF Pitch Generator
Ejecutar: python generate_pitch.py
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Frame, KeepInFrame
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import os, math

W, H = A4  # 595.27 x 841.89 pt

# Paleta
NAVY   = colors.HexColor("#1C2B3A")
BLUE   = colors.HexColor("#1A4A8A")
LBLUE  = colors.HexColor("#2A5FA8")
ACCENT = colors.HexColor("#E8EFF7")
BORDER = colors.HexColor("#DDE1E7")
MUTED  = colors.HexColor("#6B7280")
LIGHT  = colors.HexColor("#F5F6F8")
ZEBRA  = colors.HexColor("#EDF2F7")
GREEN  = colors.HexColor("#2D7A4F")
WHITE  = colors.white
BLACK  = colors.HexColor("#1A1A2E")
GOLD   = colors.HexColor("#C8A84B")

# ─── helpers canvas ──────────────────────────────────────────────────────────
def rr(c, x, y, w, h, r=4, fill=None, stroke=None, sw=0.5):
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(sw)
    c.roundRect(x, y, w, h, r,
                fill=1 if fill else 0,
                stroke=1 if stroke else 0)

def rect(c, x, y, w, h, fill=None, stroke=None, sw=0.5):
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(sw)
    c.rect(x, y, w, h,
           fill=1 if fill else 0,
           stroke=1 if stroke else 0)

def txt(c, x, y, text, font="Helvetica", size=9, color=BLACK, align="left"):
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "center": c.drawCentredString(x, y, text)
    elif align == "right": c.drawRightString(x, y, text)
    else: c.drawString(x, y, text)

def line(c, x1, y1, x2, y2, color=BORDER, w=0.5):
    c.setStrokeColor(color)
    c.setLineWidth(w)
    c.line(x1, y1, x2, y2)

def wrap_text(c, text, x, y, max_w, font="Helvetica", size=8.5, color=BLACK,
              leading=12, align="left"):
    """Dibuja texto con word-wrap, devuelve Y final."""
    c.setFont(font, size)
    c.setFillColor(color)
    words = text.split()
    lines_out, cur = [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if c.stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur: lines_out.append(cur)
            cur = w_
    if cur: lines_out.append(cur)
    cy = y
    for l in lines_out:
        if align == "center":
            c.drawCentredString(x, cy, l)
        else:
            c.drawString(x, cy, l)
        cy -= leading
    return cy

# ─── PÁGINA 1 ─────────────────────────────────────────────────────────────────
def page1(c):
    # ── Franja superior azul oscuro ──
    rect(c, 0, H - 210, W, 210, fill=NAVY)

    # Línea de acento dorada
    rect(c, 0, H - 213, W, 3, fill=GOLD)

    # Texto de portada
    txt(c, 20*mm, H - 26*mm, "OGSA  —  Sistema de Auditorías Comerciales",
        "Helvetica-Bold", 11, colors.HexColor("#7FB3E8"))

    # Tag "En producción" — alineado a la derecha en la misma línea
    tag_w = 30*mm
    rr(c, W - 20*mm - tag_w, H - 26*mm - 1*mm, tag_w, 6*mm, r=3, fill=GREEN)
    txt(c, W - 20*mm - tag_w/2, H - 26*mm + 0.8*mm,
        "EN PRODUCCION", "Helvetica-Bold", 7, WHITE, "center")

    txt(c, 20*mm, H - 36*mm, "Sistema de Auditorías Comerciales",
        "Helvetica-Bold", 24, WHITE)
    txt(c, 20*mm, H - 47*mm,
        "Auditoría de Distribuidores Syngenta  ·  Inteligencia Artificial  ·  2026",
        "Helvetica", 10, colors.HexColor("#9CB8D8"))

    # ── KPIs en la franja (banda inferior) ──
    kpis = [
        ("6", "Pasos\nauditados"),
        ("100%", "Proceso\nautomatizado"),
        ("IA", "Claude\nOpus 4.5"),
        (".EXE", "App\nWindows"),
        ("Cloud", "Backend\nRailway"),
    ]
    kpi_w = W / len(kpis)
    ky = H - 198   # bien separado del título
    for i, (num, lbl) in enumerate(kpis):
        kx = i * kpi_w
        if i > 0:
            line(c, kx, ky - 4, kx, ky + 38,
                 colors.HexColor("#2E4560"), 0.5)
        txt(c, kx + kpi_w/2, ky + 18, num, "Helvetica-Bold", 20,
            colors.HexColor("#7FB3E8"), "center")
        for j, part in enumerate(lbl.split("\n")):
            txt(c, kx + kpi_w/2, ky + 5 - j*9, part,
                "Helvetica", 7, colors.HexColor("#9CB8D8"), "center")

    # ── Sección "El desafío" ──
    y = H - 230
    txt(c, 20*mm, y, "EL DESAFIO", "Helvetica-Bold", 8, BLUE)
    line(c, 20*mm, y - 3, W - 20*mm, y - 3, BLUE, 1)

    y -= 14
    intro = ("La auditoría de distribuidores Syngenta implica cruzar múltiples fuentes "
             "heterogéneas: ERP, ARCA/AFIP, CRM y bases internas. El proceso manual "
             "consume decenas de horas por expediente y expone el trabajo a errores e "
             "inconsistencias difíciles de detectar.")
    y = wrap_text(c, intro, 20*mm, y, W - 40*mm,
                  "Helvetica", 9, BLACK, 13) - 8

    # Grid de pain points 2x3
    pains = [
        ("Tiempo",        "Cruzar planillas manualmente lleva dias por expediente."),
        ("Errores",       "El proceso manual introduce inconsistencias dificiles de auditar."),
        ("Formatos",      "Cada DS exporta con columnas y nombres de productos distintos."),
        ("Monedas",       "ARS y USD mezclados sin conversion sistematizada."),
        ("Trazabilidad",  "Sin historial centralizado de quién hizo qué y cuándo."),
        ("Reportes",      "Armar los anexos finales en Excel requiere formateo manual."),
    ]
    pw = (W - 40*mm - 6) / 3
    ph = 34
    px0 = 20*mm
    for i, (tit, desc) in enumerate(pains):
        col = i % 3
        row = i // 3
        px = px0 + col * (pw + 3)
        py = y - row * (ph + 3)
        rr(c, px, py - ph, pw, ph, r=4, fill=ACCENT)
        rect(c, px, py - ph, 3, ph, fill=BLUE)
        txt(c, px + 7, py - 10, tit, "Helvetica-Bold", 8, NAVY)
        wrap_text(c, desc, px + 7, py - 20, pw - 12,
                  "Helvetica", 7.5, MUTED, 10)

    y -= 2 * (ph + 3) + 10

    # ── Sección "La solución" ──
    txt(c, 20*mm, y, "LA SOLUCION", "Helvetica-Bold", 8, BLUE)
    line(c, 20*mm, y - 3, W - 20*mm, y - 3, BLUE, 1)
    y -= 14

    sol = ("OGSA Auditorias es un sistema de escritorio (.EXE) que guia al auditor paso a "
           "paso, automatizando cruces de datos con IA y generando los informes finales "
           "formateados — sin intervención manual.")
    y = wrap_text(c, sol, 20*mm, y, W - 40*mm,
                  "Helvetica", 9, BLACK, 13) - 8

    # Tres bloques arquitectura
    arch = [
        (NAVY,  "DESKTOP",  "Electron + React\nApp nativa Windows (.EXE)\nTailwind CSS"),
        (BLUE,  "BACKEND",  "Python FastAPI\nPostgreSQL · Railway Cloud\nDocker deploy"),
        (GREEN, "IA",       "Claude Opus 4.5\nClasificacion productos\nJustificaciones CRM"),
    ]
    aw = (W - 40*mm - 8) / 3
    ah = 52
    ax0 = 20*mm
    for i, (col_, tag, desc) in enumerate(arch):
        ax = ax0 + i * (aw + 4)
        rr(c, ax, y - ah, aw, ah, r=5, fill=col_)
        txt(c, ax + aw/2, y - 10, tag, "Helvetica-Bold", 9, WHITE, "center")
        line(c, ax + 8, y - 15, ax + aw - 8, y - 15,
             colors.HexColor("#FFFFFF44"), 0.5)
        for j, part in enumerate(desc.split("\n")):
            txt(c, ax + aw/2, y - 25 - j*10, part,
                "Helvetica", 7.5, colors.HexColor("#B0C8E8"), "center")

    y -= ah + 8

    # Features rápidas en 2 columnas
    features = [
        ("Multi-usuario", "Login con roles ADMIN / AUDITOR"),
        ("Multi-moneda",  "Conversion ARS-USD automatica"),
        ("Expedientes",   "Por distribuidor y anio, con progreso persistente"),
        ("Exportacion",   "Excel formateado con estilos OGSA listo para entregar"),
    ]
    fw = (W - 40*mm - 6) / 2
    for i, (tit, desc) in enumerate(features):
        col = i % 2
        row = i // 2
        fx = 20*mm + col * (fw + 6)
        fy = y - row * 16
        txt(c, fx, fy, "▸ " + tit + ":", "Helvetica-Bold", 8, BLUE)
        txt(c, fx + c.stringWidth("▸ " + tit + ":  ", "Helvetica-Bold", 8),
            fy, desc, "Helvetica", 8, BLACK)

    # Footer p1
    line(c, 20*mm, 13*mm, W - 20*mm, 13*mm, BORDER, 0.5)
    txt(c, 20*mm, 9*mm, "Confidencial — OGSA Auditores · 2026",
        "Helvetica", 7.5, MUTED)
    txt(c, W - 20*mm, 9*mm, "1 / 2", "Helvetica", 7.5, MUTED, "right")


# ─── PÁGINA 2 ─────────────────────────────────────────────────────────────────
def page2(c):
    # Header
    rect(c, 0, H - 22*mm, W, 22*mm, fill=NAVY)
    txt(c, 20*mm, H - 10*mm, "OGSA", "Helvetica-Bold", 9,
        colors.HexColor("#7FB3E8"))
    txt(c, 30*mm, H - 10*mm, "Sistema de Auditorias Comerciales",
        "Helvetica", 9, colors.HexColor("#9CB8D8"))
    txt(c, W - 20*mm, H - 10*mm, "Confidencial · 2026",
        "Helvetica", 7.5, MUTED, "right")
    rect(c, 0, H - 22*mm - 2, W, 2, fill=GOLD)

    y = H - 32*mm

    # ── LOS 6 PASOS ──
    txt(c, 20*mm, y, "PROCESO DE AUDITORIA: 6 PASOS SECUENCIALES",
        "Helvetica-Bold", 8, BLUE)
    line(c, 20*mm, y - 3, W - 20*mm, y - 3, BLUE, 1)
    y -= 12
    intro = ("Cada paso se habilita al completar el anterior. El sistema guia al auditor "
             "con los archivos necesarios, ejecuta los cruces automaticamente y genera "
             "los resultados listos para revision.")
    y = wrap_text(c, intro, 20*mm, y, W - 40*mm, "Helvetica", 8.5, BLACK, 12) - 8

    pasos = [
        ("01", "Cruce Gestion vs. ARCA",
         "Compara la bajada del ERP contra comprobantes emitidos en ARCA (AFIP). "
         "Concilia comprobante por comprobante en USD negando notas de credito. "
         "Clasifica: OK · DIFERENCIA · SOLO ARCA · SOLO GESTION."),
        ("02", "Analisis de Ventas",
         "Ranking clientes y productos. Muestreo de 70 clientes con inclusion "
         "forzada de especiales. IA clasifica cada producto: Agroquimico (SI/NO) "
         "y Syngenta (SI/NO). Tabla de apertura mensual."),
        ("03", "Cruce CRM Syngenta",
         "Compara ventas agroquimicos Syngenta de gestion vs reporte CRM. "
         "Claude Opus genera justificaciones automaticas para cada diferencia "
         "detectada. Ahorra analisis manual de cientos de registros."),
        ("04", "Analisis de Compras",
         "Analiza comprobantes recibidos de ARCA. Convierte todo a USD con tipo "
         "de cambio del periodo. Agrupa por proveedor y mes. Desglose FC/NC/ND "
         "para proveedores especiales definidos por el usuario."),
        ("05", "Informe Ejecutivo Excel",
         "Genera Excel formateado con 3 anexos: Resumen Compras (proveedores top "
         "90% del gasto), Venta Agroquimicos (tabla apertura) y Cruce CRM. "
         "Estilos y branding OGSA listos para entregar."),
        ("06", "Informe + Glosario IA",
         "Identico al Paso 5 mas columna 'Nombre Glosario' en Anexo II. "
         "Claude mapea cada producto al nombre estandarizado del glosario "
         "institucional, unificando nomenclaturas entre distribuidores."),
    ]

    sw = (W - 40*mm - 6) / 2
    sh = 62

    for i, (num, title, desc) in enumerate(pasos):
        col = i % 2
        row = i // 2
        sx = 20*mm + col * (sw + 6)
        sy = y - row * (sh + 5)

        # Fondo tarjeta
        rr(c, sx, sy - sh, sw, sh, r=5, fill=LIGHT)
        # Borde izquierdo color
        band_col = BLUE if int(num) <= 4 else GREEN
        rr(c, sx, sy - sh, 24, sh, r=5, fill=band_col)
        rect(c, sx + 16, sy - sh, 8, sh, fill=band_col)  # parche esquina recta derecha

        # Numero
        txt(c, sx + 12, sy - sh/2 - 5, num, "Helvetica-Bold", 15, WHITE, "center")

        # Contenido
        cx = sx + 30
        cw = sw - 36

        txt(c, cx, sy - 10, title, "Helvetica-Bold", 9, NAVY)
        wrap_text(c, desc, cx, sy - 22, cw, "Helvetica", 7.5,
                  colors.HexColor("#374151"), 11)

        # Conector flecha (excepto últimos)
        if col == 0 and i < len(pasos) - 1:
            mid_x = sx + sw + 3
            mid_y = sy - sh/2
            txt(c, mid_x, mid_y - 3, "→", "Helvetica-Bold", 10, BORDER, "center")

    y -= 3 * (sh + 5) + 8

    # ── BENEFICIOS ──
    txt(c, 20*mm, y, "BENEFICIOS CONCRETOS", "Helvetica-Bold", 8, BLUE)
    line(c, 20*mm, y - 3, W - 20*mm, y - 3, BLUE, 1)
    y -= 12

    beneficios = [
        ("Velocidad",      "De dias a minutos por expediente"),
        ("Consistencia",   "Mismo proceso, sin variacion entre auditores"),
        ("Estandarizacion","Glosario unifica nombres entre distribuidores"),
        ("Trazabilidad",   "Historial completo de pasos, archivos y resultados"),
        ("Entregables",    "Excel formateado OAG sin retoques manuales"),
        ("Multi-auditor",  "Varios auditores en simultaneo desde cualquier PC"),
    ]

    bw = (W - 40*mm - 10) / 3
    bh = 28
    for i, (tit, desc) in enumerate(beneficios):
        col = i % 3
        row = i // 3
        bx = 20*mm + col * (bw + 5)
        by = y - row * (bh + 4)
        rr(c, bx, by - bh, bw, bh, r=4, fill=ACCENT)
        rect(c, bx, by - bh, 3, bh, fill=BLUE)
        txt(c, bx + 8, by - 10, tit, "Helvetica-Bold", 8, NAVY)
        wrap_text(c, desc, bx + 8, by - 20, bw - 14,
                  "Helvetica", 7.5, MUTED, 10)

    y -= 2 * (bh + 4) + 10

    # ── STACK TECNOLOGICO ──
    txt(c, 20*mm, y, "STACK TECNOLOGICO", "Helvetica-Bold", 8, BLUE)
    line(c, 20*mm, y - 3, W - 20*mm, y - 3, BLUE, 1)
    y -= 12

    tech = [
        ("Frontend",  "Electron + React + TypeScript  ·  App nativa Windows (.EXE)  ·  Tailwind CSS"),
        ("Backend",   "Python FastAPI  ·  PostgreSQL  ·  Railway Cloud  ·  Docker"),
        ("IA",        "Anthropic Claude Opus 4.5  ·  Clasificacion  ·  Normalizacion  ·  Justificaciones"),
        ("Reportes",  "pandas + openpyxl  ·  Excel formateado con branding OGSA"),
        ("Auth",      "JWT  ·  Roles ADMIN / AUDITOR  ·  Sesion persistente 8hs"),
    ]

    row_h = 13
    for i, (label, desc) in enumerate(tech):
        ty = y - i * row_h
        bg = ZEBRA if i % 2 == 0 else WHITE
        rect(c, 20*mm, ty - row_h + 2, W - 40*mm, row_h, fill=bg)
        txt(c, 22*mm, ty - 7, label, "Helvetica-Bold", 8, BLUE)
        txt(c, 50*mm, ty - 7, desc, "Helvetica", 8, BLACK)

    y -= len(tech) * row_h + 8

    # ── CTA ──
    cta_h = 30
    rr(c, 20*mm, y - cta_h, W - 40*mm, cta_h, r=6, fill=NAVY)
    line(c, 20*mm, y - cta_h, W - 20*mm, y - cta_h, GOLD, 2.5)
    line(c, 20*mm, y, W - 20*mm, y, GOLD, 2.5)
    txt(c, W/2, y - 11, "Sistema en produccion  ·  oag.up.railway.app",
        "Helvetica-Bold", 10, WHITE, "center")
    txt(c, W/2, y - 21,
        "Backend activo en Railway  ·  App .EXE instalable en cualquier equipo Windows",
        "Helvetica", 8, colors.HexColor("#9CB8D8"), "center")

    # Footer p2
    line(c, 20*mm, 13*mm, W - 20*mm, 13*mm, BORDER, 0.5)
    txt(c, 20*mm, 9*mm, "Confidencial — OGSA Auditores · 2026",
        "Helvetica", 7.5, MUTED)
    txt(c, W - 20*mm, 9*mm, "2 / 2", "Helvetica", 7.5, MUTED, "right")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    output = "OGSA_Auditoria_Pitch.pdf"
    c = canvas.Canvas(output, pagesize=A4)
    c.setTitle("OGSA Sistema de Auditorias Comerciales")
    c.setAuthor("OGSA Auditores")
    c.setSubject("Presentacion del sistema de auditoria para distribuidores Syngenta")

    page1(c)
    c.showPage()
    page2(c)
    c.showPage()
    c.save()

    print(f"PDF generado: {os.path.abspath(output)}")

if __name__ == "__main__":
    main()
