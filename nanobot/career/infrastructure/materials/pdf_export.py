"""Generate an ATS-readable PDF and verify it by parsing and actual rendering."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import ClassVar
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from nanobot.career.domain.common.errors import CareerDomainError


@dataclass(frozen=True, slots=True)
class PdfExportResult:
    pdf_bytes: bytes
    preview_png: bytes
    sha256: str
    size_bytes: int
    page_count: int
    text_layer_ok: bool
    render_ok: bool
    extracted_text_hash: str


class VerifiedPdfExporter:
    _registered_fonts: ClassVar[tuple[str, str] | None] = None

    def __init__(self) -> None:
        if self._registered_fonts is None:
            type(self)._registered_fonts = self._register_fonts()
        self.regular_font, self.bold_font = self._registered_fonts

    def generate(
        self,
        *,
        title: str,
        subtitle: str,
        sections: list[tuple[str, list[str]]],
    ) -> PdfExportResult:
        stream = BytesIO()
        document = SimpleDocTemplate(
            stream,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=title,
            author="Nanobot Career",
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CareerTitle",
            parent=styles["Title"],
            fontName=self.bold_font,
            fontSize=19,
            leading=24,
            alignment=TA_CENTER,
            textColor="#173a3c",
            spaceAfter=4 * mm,
        )
        subtitle_style = ParagraphStyle(
            "CareerSubtitle",
            parent=styles["Normal"],
            fontName=self.regular_font,
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor="#5f716d",
            spaceAfter=5 * mm,
        )
        heading_style = ParagraphStyle(
            "CareerHeading",
            parent=styles["Heading2"],
            fontName=self.bold_font,
            fontSize=12,
            leading=16,
            textColor="#173a3c",
            spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
            borderWidth=0,
            borderPadding=0,
        )
        body_style = ParagraphStyle(
            "CareerBody",
            parent=styles["BodyText"],
            fontName=self.regular_font,
            fontSize=9.5,
            leading=14,
            textColor="#263b3b",
            leftIndent=4 * mm,
            firstLineIndent=-3 * mm,
            bulletIndent=0,
            spaceAfter=1.5 * mm,
            wordWrap="CJK",
        )
        story = [Paragraph(escape(title), title_style), Paragraph(escape(subtitle), subtitle_style)]
        for heading, lines in sections:
            if not lines:
                continue
            story.extend([Paragraph(escape(heading), heading_style), Spacer(1, 1 * mm)])
            for line in lines:
                story.append(Paragraph(f"• {escape(line)}", body_style))
        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        pdf_bytes = stream.getvalue()
        return self._verify(pdf_bytes)

    def _verify(self, pdf_bytes: bytes) -> PdfExportResult:
        try:
            document = pdfium.PdfDocument(pdf_bytes)
            page_count = len(document)
            extracted_parts: list[str] = []
            for page_index in range(page_count):
                page = document[page_index]
                text_page = page.get_textpage()
                extracted_parts.append(text_page.get_text_bounded())
                text_page.close()
                page.close()
            extracted = "\n".join(extracted_parts)
            if not 1 <= page_count <= 3:
                raise CareerDomainError(
                    "Exported PDF must contain between 1 and 3 pages.",
                    code="pdf_page_count_invalid",
                )
            text_layer_ok = len("".join(extracted.split())) >= 20
            page = document[0]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil().convert("RGB")
            preview_stream = BytesIO()
            image.save(preview_stream, format="PNG")
            preview = preview_stream.getvalue()
            extrema = image.getextrema()
            render_ok = (
                image.width > 500
                and image.height > 700
                and min(channel[0] for channel in extrema) < 245
            )
            bitmap.close()
            page.close()
            document.close()
        except CareerDomainError:
            raise
        except Exception as exc:
            raise CareerDomainError(
                "The PDF could not be rendered and verified.", code="pdf_render_failed"
            ) from exc
        if not text_layer_ok:
            raise CareerDomainError(
                "The PDF does not contain a usable ATS text layer.", code="pdf_text_layer_invalid"
            )
        if not render_ok:
            raise CareerDomainError("The PDF render verification failed.", code="pdf_render_failed")
        return PdfExportResult(
            pdf_bytes,
            preview,
            hashlib.sha256(pdf_bytes).hexdigest(),
            len(pdf_bytes),
            page_count,
            text_layer_ok,
            render_ok,
            hashlib.sha256(extracted.encode("utf-8")).hexdigest(),
        )

    def _footer(self, canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(self.regular_font, 7.5)
        canvas.setFillColor("#73827e")
        canvas.drawCentredString(A4[0] / 2, 8 * mm, f"Nanobot Career · {document.page}")
        canvas.restoreState()

    @staticmethod
    def _register_fonts() -> tuple[str, str]:
        candidates = [
            (Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/msyhbd.ttc")),
            (
                Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            ),
            (
                Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
                Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            ),
        ]
        for regular, bold in candidates:
            if regular.is_file():
                try:
                    pdfmetrics.registerFont(TTFont("CareerRegular", str(regular), subfontIndex=0))
                    pdfmetrics.registerFont(
                        TTFont(
                            "CareerBold", str(bold if bold.is_file() else regular), subfontIndex=0
                        )
                    )
                    return "CareerRegular", "CareerBold"
                except Exception:
                    continue
        for name in ("STSong-Light",):
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(UnicodeCIDFont(name))
        return "STSong-Light", "STSong-Light"
