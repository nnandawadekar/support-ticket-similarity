"""Render the concise design from its Markdown source; requires the docs extra."""
import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent


def inline(text):
    text = escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#2355a4">\1</link>', text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r'<font name="Courier" size="8.2">\1</font>', text)


def raster_figure(path, max_width, max_height):
    """Embed a diagram as an RGB JPEG picture: submission tooling cannot read vector diagrams or PNG alpha."""
    from PIL import Image as PILImage

    with PILImage.open(ROOT / path) as source:
        picture = PILImage.new("RGB", source.size, "white")
        picture.paste(source, mask=source.convert("RGBA").split()[-1])
    picture.thumbnail((2400, 2400))
    buffer = BytesIO()
    picture.save(buffer, "JPEG", quality=88, optimize=True)
    buffer.seek(0)
    scale = min(max_width / picture.width, max_height / picture.height)
    return Image(buffer, width=picture.width * scale, height=picture.height * scale)


def main():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("DesignBody", fontName="Helvetica", fontSize=9.6, leading=12.3, spaceAfter=6))
    styles.add(ParagraphStyle("DesignTitle", fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=12))
    styles.add(ParagraphStyle("DesignHeading", fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                              textColor=colors.HexColor("#2355a4"), spaceBefore=7, spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle("DesignCaption", fontName="Helvetica-Oblique", fontSize=8.4, leading=10.6,
                              textColor=colors.HexColor("#334155"), spaceBefore=4, spaceAfter=8))
    styles.add(ParagraphStyle("DesignCell", fontName="Helvetica", fontSize=8.7, leading=11, alignment=TA_LEFT))
    story, paragraph, table_rows = [], [], []

    def flush():
        if paragraph:
            story.append(Paragraph(inline(" ".join(paragraph)), styles["DesignBody"]))
            paragraph.clear()
        if table_rows:
            table = Table([[Paragraph(inline(cell), styles["DesignCell"]) for cell in row] for row in table_rows],
                          colWidths=[211, A4[0] - 84 - 211], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf0f7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(table)
            table_rows.clear()

    for line in (ROOT / "SOLUTION_DESIGN.md").read_text().splitlines():
        if not line.strip():
            flush()
        elif line.lstrip().startswith("<!--"):
            continue  # Markdown-only notes
        elif line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), styles["DesignTitle"]))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), styles["DesignHeading"]))
        elif figure := re.fullmatch(r"!\[(.+)\]\(([^)]+)\)", line.strip()):
            flush()
            story.append(KeepTogether([raster_figure(figure.group(2), A4[0] - 84, 400),
                                       Paragraph(inline(figure.group(1)), styles["DesignCaption"])]))
        elif line.startswith("|"):
            if not re.fullmatch(r"[| :\-]+", line):
                table_rows.append([cell.strip() for cell in line.strip("|").split("|")])
        elif line.startswith("- "):
            flush()
            story.append(Paragraph(inline(line[2:]), styles["DesignBody"], bulletText="-"))
        else:
            paragraph.append(line.strip())
    flush()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(42, 34, A4[0] - 42, 34)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawString(42, 22, "Solari Analytics | Support Ticket Similarity Assistant")
        canvas.drawRightString(A4[0] - 42, 22, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(ROOT / "SOLUTION_DESIGN.pdf"), pagesize=A4,
                                 topMargin=38, bottomMargin=44, leftMargin=42, rightMargin=42,
                                 title="Support Ticket Similarity Assistant - Solution Design",
                                 author="Solari Analytics case study")
    document.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    main()
