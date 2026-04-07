#!/usr/bin/env python3
"""
CCC Daily News -- PDF Generation Module
========================================
Generates 8-page A4 PDF newsletters with CJK Japanese font support.
Uses reportlab canvas drawing for layout with registered Noto fonts.

Updated to use Japanese fields (title_jp, content_jp, summary_jp) from articles,
and Japanese headline/summary/editor's note from the issue record.

Page structure:
    1. Cover
    2. Table of Contents
    3-4. Featured Stories
    5-6. Category News
    7. Data Page
    8. Editor's Note
"""

import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


# =============================================================================
# COLORS
# =============================================================================

BEIGE = HexColor('#F5F0E8')
CHARCOAL = HexColor('#2D2D2D')
BURGUNDY = HexColor('#8B2252')
LIGHT_BEIGE = HexColor('#FAF7F2')
CREAM = HexColor('#E8E0D4')
WARM_GRAY = HexColor('#6B6560')
WHITE = HexColor('#FFFFFF')

# =============================================================================
# PAGE DIMENSIONS
# =============================================================================

W, H = A4
MARGIN = 20 * mm
CONTENT_W = W - 2 * MARGIN

# =============================================================================
# FONTS
# =============================================================================

FONT_SANS = None
FONT_SANS_BOLD = None
FONT_SERIF = None
FONT_SERIF_BOLD = None

_fonts_registered = False


def register_fonts():
    global FONT_SANS, FONT_SANS_BOLD, FONT_SERIF, FONT_SERIF_BOLD, _fonts_registered
    if _fonts_registered:
        return

    font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
    pdfmetrics.registerFont(TTFont('NotoSansJP', f'{font_dir}/NotoSansJP-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSansJP-Bold', f'{font_dir}/NotoSansJP-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSerifJP', f'{font_dir}/NotoSerifJP-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('NotoSerifJP-Bold', f'{font_dir}/NotoSerifJP-Bold.ttf'))

    FONT_SANS = 'NotoSansJP'
    FONT_SANS_BOLD = 'NotoSansJP-Bold'
    FONT_SERIF = 'NotoSerifJP'
    FONT_SERIF_BOLD = 'NotoSerifJP-Bold'
    _fonts_registered = True


def _create_styles():
    return {
        'body': ParagraphStyle(
            'body', fontName=FONT_SERIF, fontSize=8.5,
            leading=15, textColor=CHARCOAL,
        ),
        'body_justified': ParagraphStyle(
            'body_j', fontName=FONT_SERIF, fontSize=8.5,
            leading=15, textColor=CHARCOAL, alignment=TA_JUSTIFY,
        ),
        'body_small': ParagraphStyle(
            'body_small', fontName=FONT_SERIF, fontSize=7.5,
            leading=13, textColor=WARM_GRAY,
        ),
        'heading': ParagraphStyle(
            'heading', fontName=FONT_SANS_BOLD, fontSize=13,
            leading=18, textColor=CHARCOAL,
        ),
        'subheading': ParagraphStyle(
            'subheading', fontName=FONT_SANS_BOLD, fontSize=10,
            leading=15, textColor=CHARCOAL,
        ),
        'caption': ParagraphStyle(
            'caption', fontName=FONT_SANS, fontSize=7,
            leading=10, textColor=WARM_GRAY,
        ),
    }


# =============================================================================
# ARTICLE FIELD HELPERS -- prefer Japanese fields, fallback to original
# =============================================================================

def _art_title(art):
    """Return the best available title (prefer Japanese)."""
    return art.get('title_jp') or art.get('title', '')


def _art_content(art):
    """Return the best available body content (prefer Japanese)."""
    return art.get('content_jp') or art.get('content', '')


def _art_summary(art):
    """Return the best available summary (prefer Japanese)."""
    return art.get('summary_jp') or art.get('summary', '')


# =============================================================================
# HELPER DRAWING FUNCTIONS
# =============================================================================

def _draw_page_bg(c):
    c.setFillColor(BEIGE)
    c.rect(0, 0, W, H, fill=1, stroke=0)


def _draw_header_bar(c, page_num, issue_number, date_str):
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(0.5)
    c.line(MARGIN, H - 12 * mm, W - MARGIN, H - 12 * mm)

    c.setFont(FONT_SANS_BOLD, 7)
    c.setFillColor(BURGUNDY)
    c.drawString(MARGIN, H - 10.5 * mm, 'CCC Daily News')

    c.setFont(FONT_SANS, 6)
    c.setFillColor(WARM_GRAY)
    c.drawRightString(W - MARGIN, H - 10.5 * mm, f'\u7b2c{issue_number}\u53f7 | {date_str}')


def _draw_footer(c, page_num):
    y = 10 * mm
    c.setStrokeColor(CREAM)
    c.setLineWidth(0.3)
    c.line(MARGIN, y + 4 * mm, W - MARGIN, y + 4 * mm)

    c.setFont(FONT_SANS, 6)
    c.setFillColor(WARM_GRAY)
    c.drawString(MARGIN, y, 'CCC Daily News')
    c.drawCentredString(W / 2, y, f'\u2014 {page_num} \u2014')
    c.drawRightString(W - MARGIN, y, 'CCC Daily News \u00a9 2026')


def _draw_category_tag(c, x, y, text, color=None):
    color = color or BURGUNDY
    c.setFont(FONT_SANS, 6)
    tw = c.stringWidth(text, FONT_SANS, 6)
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.roundRect(x, y - 2, tw + 8, 12, 1, fill=0, stroke=1)
    c.drawString(x + 4, y, text)


def _draw_separator(c, y, width=None):
    w = width or CONTENT_W
    c.setStrokeColor(CREAM)
    c.setLineWidth(0.3)
    c.line(MARGIN, y, MARGIN + w, y)


def _draw_text_block(c, text, x, y, width, style):
    p = Paragraph(text, style)
    _, ph = p.wrap(width, 500)
    p.drawOn(c, x, y - ph)
    return ph


def _wrap_text_lines(text, font_name, font_size, max_width):
    if not text:
        return ['']
    lines = []
    current = ''
    for char in text:
        test = current + char
        w = pdfmetrics.stringWidth(test, font_name, font_size)
        if w > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _extract_keywords(articles):
    keywords = []
    seen = set()
    for art in articles:
        cat = art.get('category', '')
        if cat and cat not in seen:
            keywords.append(cat)
            seen.add(cat)
        title = _art_title(art)
        parts = re.split(r'[\u3001\uff0c,\uff1a:\uff5c|\u2014\u2013\-\s]+', title)
        for part in parts:
            part = part.strip()
            if 2 <= len(part) <= 12 and part not in seen:
                keywords.append(part)
                seen.add(part)
                if len(keywords) >= 8:
                    return keywords
    return keywords[:8]


def _safe_article(articles, idx):
    if idx < len(articles):
        return articles[idx]
    return {'title': '', 'title_jp': '', 'category': '', 'summary': '', 'summary_jp': '',
            'content': '', 'content_jp': ''}


# =============================================================================
# PAGE 1 -- COVER
# =============================================================================

def _draw_cover(c, issue_number, date_str, headline, summary, articles):
    _draw_page_bg(c)

    # Top burgundy bar
    c.setFillColor(BURGUNDY)
    c.rect(0, H - 28 * mm, W, 28 * mm, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont(FONT_SANS_BOLD, 22)
    c.drawString(MARGIN, H - 18 * mm, 'CCC Daily News')

    c.setFont(FONT_SANS, 9)
    c.drawString(MARGIN + 155, H - 17 * mm, '\u4e2d\u56fd\u30c6\u30c3\u30af\u30fbAI\u30cb\u30e5\u30fc\u30b9\u30c0\u30a4\u30b8\u30a7\u30b9\u30c8')

    c.saveState()
    c.setStrokeColor(HexColor('#FFFFFF40'))
    c.setLineWidth(0.5)
    c.circle(W - 35 * mm, H - 14 * mm, 18 * mm, fill=0, stroke=1)
    c.circle(W - 35 * mm, H - 14 * mm, 12 * mm, fill=0, stroke=1)
    c.restoreState()

    y = H - 48 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS, 9)
    c.drawString(MARGIN, y, f'\u7b2c{issue_number}\u53f7')
    c.setFillColor(WARM_GRAY)
    c.setFont(FONT_SANS, 8)
    c.drawString(MARGIN + 45, y, f'|  {date_str}')

    y -= 6 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(1)
    c.line(MARGIN, y, MARGIN + 50 * mm, y)

    y -= 18 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 24)
    headline_lines = _wrap_text_lines(headline, FONT_SANS_BOLD, 24, CONTENT_W)
    for line in headline_lines:
        c.drawString(MARGIN, y, line)
        y -= 11 * mm

    y -= 5 * mm
    c.setFont(FONT_SERIF, 10)
    c.setFillColor(WARM_GRAY)
    summary_lines = _wrap_text_lines(summary, FONT_SERIF, 10, CONTENT_W)
    for line in summary_lines:
        c.drawString(MARGIN, y, line)
        y -= 5.5 * mm

    y -= 12 * mm
    c.setStrokeColor(CREAM)
    c.setLineWidth(0.3)
    c.line(MARGIN, y, W - MARGIN, y)

    y -= 12 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 9)
    c.drawString(MARGIN, y, '\u4eca\u65e5\u306e\u6ce8\u76ee\u8a18\u4e8b')
    y -= 10 * mm
    for art in articles[:4]:
        cat = art.get('category', '')
        title = _art_title(art)
        c.setFillColor(BURGUNDY)
        c.setFont(FONT_SANS, 7)
        c.drawString(MARGIN + 2, y, f'[{cat}]')
        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SERIF, 8.5)
        max_title_w = CONTENT_W - 55
        display_title = title
        if pdfmetrics.stringWidth(display_title, FONT_SERIF, 8.5) > max_title_w:
            while pdfmetrics.stringWidth(display_title + '\u2026', FONT_SERIF, 8.5) > max_title_w and len(display_title) > 1:
                display_title = display_title[:-1]
            display_title += '\u2026'
        c.drawString(MARGIN + 55, y, display_title)
        y -= 8 * mm

    c.saveState()
    c.setFillColor(HexColor('#8B225508'))
    c.setFont(FONT_SANS_BOLD, 200)
    c.drawString(W - 160 * mm, 30 * mm, 'AI')
    c.restoreState()

    c.setFillColor(BURGUNDY)
    c.rect(MARGIN, 22 * mm, 30 * mm, 0.8 * mm, fill=1, stroke=0)
    c.setFillColor(CREAM)
    c.rect(MARGIN + 32 * mm, 22 * mm, 60 * mm, 0.8 * mm, fill=1, stroke=0)

    _draw_footer(c, 1)


# =============================================================================
# PAGE 2 -- TABLE OF CONTENTS
# =============================================================================

def _draw_toc(c, issue_number, date_str, articles):
    _draw_page_bg(c)
    _draw_header_bar(c, 2, issue_number, date_str)

    y = H - 30 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 16)
    c.drawString(MARGIN, y, '\u4eca\u65e5\u306e\u30cb\u30e5\u30fc\u30b9\u4e00\u89a7')

    y -= 4 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(1.5)
    c.line(MARGIN, y, MARGIN + 35 * mm, y)

    def _page_for_index(idx):
        return 3 + idx // 2

    y -= 12 * mm
    for i, art in enumerate(articles):
        num_str = f'{i + 1:02d}'
        cat = art.get('category', '')
        title = _art_title(art)
        page_ref = f'P.{_page_for_index(i)}'

        c.setFillColor(BURGUNDY)
        c.setFont(FONT_SANS_BOLD, 18)
        c.drawString(MARGIN, y - 2, num_str)

        c.setFont(FONT_SANS, 6.5)
        c.setFillColor(WARM_GRAY)
        c.drawString(MARGIN + 22 * mm, y + 5, cat)

        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SERIF, 9.5)
        max_w = (W - MARGIN) - (MARGIN + 22 * mm) - 25 * mm
        display = title
        if pdfmetrics.stringWidth(display, FONT_SERIF, 9.5) > max_w:
            while pdfmetrics.stringWidth(display + '\u2026', FONT_SERIF, 9.5) > max_w and len(display) > 1:
                display = display[:-1]
            display += '\u2026'
        c.drawString(MARGIN + 22 * mm, y - 5, display)

        c.setFillColor(BURGUNDY)
        c.setFont(FONT_SANS_BOLD, 9)
        c.drawRightString(W - MARGIN, y - 3, page_ref)

        c.setStrokeColor(CREAM)
        c.setLineWidth(0.3)
        c.setDash(1, 3)
        title_w = c.stringWidth(display, FONT_SERIF, 9.5)
        c.line(MARGIN + 22 * mm + title_w + 5, y - 3, W - MARGIN - 18, y - 3)
        c.setDash()

        y -= 20 * mm

    keywords = _extract_keywords(articles)
    box_x = W - MARGIN - 55 * mm
    box_w = 55 * mm
    box_h = 65 * mm
    box_y = 25 * mm

    c.setFillColor(LIGHT_BEIGE)
    c.setStrokeColor(CREAM)
    c.setLineWidth(0.5)
    c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=1)

    ky = box_y + box_h - 8 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS_BOLD, 8)
    c.drawString(box_x + 5 * mm, ky, '\u4eca\u65e5\u306e\u30ad\u30fc\u30ef\u30fc\u30c9')

    ky -= 3 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(0.5)
    c.line(box_x + 5 * mm, ky, box_x + box_w - 5 * mm, ky)

    ky -= 8 * mm
    for kw in keywords:
        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SERIF, 7.5)
        c.drawString(box_x + 5 * mm, ky, f'\u25cf {kw}')
        ky -= 7.5 * mm

    _draw_footer(c, 2)


# =============================================================================
# PAGES 3-4 -- FEATURED STORIES
# =============================================================================

def _draw_featured_page(c, styles, issue_number, date_str, articles, page_num, article_indices):
    _draw_page_bg(c)
    _draw_header_bar(c, page_num, issue_number, date_str)

    y = H - 30 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS, 7)
    c.drawString(MARGIN, y + 3, '\u7279\u96c6\u8a18\u4e8b  FEATURED')
    y -= 3 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(1)
    c.line(MARGIN, y, MARGIN + 25 * mm, y)

    footer_limit = 22 * mm

    for idx_in_page, ai in enumerate(article_indices):
        art = _safe_article(articles, ai)
        title = _art_title(art)
        if not title:
            continue

        y -= 10 * mm
        _draw_category_tag(c, MARGIN, y, art.get('category', ''))

        y -= 10 * mm
        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SANS_BOLD, 14)
        title_lines = _wrap_text_lines(title, FONT_SANS_BOLD, 14, CONTENT_W)
        for tl in title_lines:
            c.drawString(MARGIN, y, tl)
            y -= 7 * mm
        y += 2 * mm

        c.setStrokeColor(CREAM)
        c.setLineWidth(0.3)
        c.line(MARGIN, y, W - MARGIN, y)
        y -= 3 * mm

        body_text = _art_content(art) or _art_summary(art)
        if body_text:
            paragraphs = [p.strip() for p in body_text.split('\n') if p.strip()]
            for para in paragraphs:
                if y < footer_limit + 15 * mm:
                    break
                ph = _draw_text_block(c, para, MARGIN, y, CONTENT_W, styles['body_justified'])
                y -= ph + 3 * mm

        if y > footer_limit + 5 * mm:
            c.setFont(FONT_SANS, 6)
            c.setFillColor(WARM_GRAY)
            c.drawString(MARGIN, y, f'\u51fa\u5178: CCC Daily News \u7b2c{issue_number}\u53f7')
            y -= 5 * mm

        if idx_in_page == 0 and len(article_indices) > 1:
            y -= 8 * mm
            _draw_separator(c, y)

    _draw_footer(c, page_num)


# =============================================================================
# PAGES 5-6 -- CATEGORY NEWS
# =============================================================================

def _draw_category_page(c, styles, issue_number, date_str, articles, page_num, article_indices):
    _draw_page_bg(c)
    _draw_header_bar(c, page_num, issue_number, date_str)

    y = H - 30 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS, 7)
    c.drawString(MARGIN, y + 3, '\u30ab\u30c6\u30b4\u30ea\u30fc\u30cb\u30e5\u30fc\u30b9  CATEGORY NEWS')
    y -= 3 * mm
    c.setStrokeColor(CHARCOAL)
    c.setLineWidth(1)
    c.line(MARGIN, y, MARGIN + 25 * mm, y)

    footer_limit = 22 * mm

    for idx_in_page, ai in enumerate(article_indices):
        art = _safe_article(articles, ai)
        title = _art_title(art)
        if not title:
            continue

        y -= 10 * mm
        _draw_category_tag(c, MARGIN, y, art.get('category', ''))

        y -= 10 * mm
        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SANS_BOLD, 14)
        title_lines = _wrap_text_lines(title, FONT_SANS_BOLD, 14, CONTENT_W)
        for tl in title_lines:
            c.drawString(MARGIN, y, tl)
            y -= 7 * mm
        y += 2 * mm
        _draw_separator(c, y)
        y -= 3 * mm

        body_text = _art_summary(art) or _art_content(art)
        if body_text:
            paragraphs = [p.strip() for p in body_text.split('\n') if p.strip()]
            for para in paragraphs:
                if y < footer_limit + 15 * mm:
                    break
                ph = _draw_text_block(c, para, MARGIN, y, CONTENT_W, styles['body'])
                y -= ph + 3 * mm

        if y > footer_limit + 5 * mm:
            c.setFont(FONT_SANS, 6)
            c.setFillColor(WARM_GRAY)
            c.drawString(MARGIN, y, f'\u51fa\u5178: CCC Daily News \u7b2c{issue_number}\u53f7')
            y -= 5 * mm

        if idx_in_page == 0 and len(article_indices) > 1:
            y -= 8 * mm
            _draw_separator(c, y)

    _draw_footer(c, page_num)


# =============================================================================
# PAGE 7 -- DATA PAGE
# =============================================================================

def _draw_data_page(c, styles, issue_number, date_str, articles):
    _draw_page_bg(c)
    _draw_header_bar(c, 7, issue_number, date_str)

    y = H - 30 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS, 7)
    c.drawString(MARGIN, y + 3, '\u30c7\u30fc\u30bf  DATA & FIGURES')
    y -= 3 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(1)
    c.line(MARGIN, y, MARGIN + 25 * mm, y)

    y -= 8 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 16)
    c.drawString(MARGIN, y, '\u4eca\u65e5\u306e\u30c7\u30fc\u30bf')

    y -= 15 * mm
    table_x = MARGIN
    table_w = CONTENT_W
    col1_w = 35 * mm
    col2_w = table_w - col1_w

    c.setFillColor(BURGUNDY)
    c.rect(table_x, y - 1 * mm, table_w, 8 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(FONT_SANS_BOLD, 7.5)
    c.drawString(table_x + 3 * mm, y + 1 * mm, '\u30ab\u30c6\u30b4\u30ea\u30fc')
    c.drawString(table_x + col1_w + 3 * mm, y + 1 * mm, '\u8a18\u4e8b\u30bf\u30a4\u30c8\u30eb')

    y -= 10 * mm

    for i, art in enumerate(articles[:8]):
        row_h = 10 * mm
        if i % 2 == 0:
            c.setFillColor(LIGHT_BEIGE)
        else:
            c.setFillColor(WHITE)
        c.rect(table_x, y - 2 * mm, table_w, row_h, fill=1, stroke=0)

        c.setFillColor(BURGUNDY)
        c.setFont(FONT_SANS, 7)
        c.drawString(table_x + 3 * mm, y + 2 * mm, art.get('category', ''))

        c.setFillColor(CHARCOAL)
        c.setFont(FONT_SERIF, 7.5)
        title = _art_title(art)
        max_title_w = col2_w - 6 * mm
        if pdfmetrics.stringWidth(title, FONT_SERIF, 7.5) > max_title_w:
            while pdfmetrics.stringWidth(title + '\u2026', FONT_SERIF, 7.5) > max_title_w and len(title) > 1:
                title = title[:-1]
            title += '\u2026'
        c.drawString(table_x + col1_w + 3 * mm, y + 2 * mm, title)

        y -= row_h

    y -= 15 * mm
    box_h = 45 * mm
    c.setFillColor(LIGHT_BEIGE)
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(0.5)
    c.rect(MARGIN, y - box_h, CONTENT_W, box_h, fill=1, stroke=1)

    by = y - 8 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS_BOLD, 9)
    c.drawString(MARGIN + 5 * mm, by, '\u672c\u65e5\u306e\u30cb\u30e5\u30fc\u30b9\u30b5\u30de\u30ea\u30fc')

    by -= 5 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(0.3)
    c.line(MARGIN + 5 * mm, by, MARGIN + CONTENT_W - 5 * mm, by)

    by -= 10 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SERIF, 8)
    summary_text = f'\u672c\u65e5\u306f{len(articles)}\u672c\u306e\u30cb\u30e5\u30fc\u30b9\u3092\u304a\u5c4a\u3051\u3057\u307e\u3057\u305f\u3002'
    c.drawString(MARGIN + 5 * mm, by, summary_text)

    cats = {}
    for art in articles:
        cat = art.get('category', '\u305d\u306e\u4ed6')
        cats[cat] = cats.get(cat, 0) + 1

    by -= 8 * mm
    for cat, count in cats.items():
        line = f'\u25cf {cat}: {count}\u672c'
        c.drawString(MARGIN + 5 * mm, by, line)
        by -= 6 * mm

    _draw_footer(c, 7)


# =============================================================================
# PAGE 8 -- EDITOR'S NOTE
# =============================================================================

def _draw_editors_note(c, styles, issue_number, date_str, articles, editors_note_text=""):
    _draw_page_bg(c)
    _draw_header_bar(c, 8, issue_number, date_str)

    y = H - 30 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS, 7)
    c.drawString(MARGIN, y + 3, "\u7de8\u96c6\u5f8c\u8a18  EDITOR'S NOTE")
    y -= 3 * mm
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(1)
    c.line(MARGIN, y, MARGIN + 25 * mm, y)

    y -= 12 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 16)
    c.drawString(MARGIN, y, '\u7de8\u96c6\u5f8c\u8a18')

    y -= 15 * mm

    if editors_note_text:
        # Use provided AI-generated editor's note
        paragraphs = [p.strip() for p in editors_note_text.split('\n') if p.strip()]
        for para in paragraphs:
            ph = _draw_text_block(c, para, MARGIN, y, CONTENT_W, styles['body_justified'])
            y -= ph + 5 * mm
    else:
        # Fallback default
        reflection = (
            f'\u7b2c{issue_number}\u53f7\u3092\u304a\u5c4a\u3051\u3057\u307e\u3057\u305f\u3002\u672c\u65e5\u306f{len(articles)}\u672c\u306e\u8a18\u4e8b\u3092'
            '\u30d4\u30c3\u30af\u30a2\u30c3\u30d7\u3057\u3001\u4e2d\u56fd\u30c6\u30c3\u30af\u30fbAI\u5206\u91ce\u306e\u6700\u65b0\u52d5\u5411\u3092\u304a\u4f1d\u3048\u3057\u307e\u3057\u305f\u3002'
            '\u6025\u901f\u306b\u5909\u5316\u3059\u308b\u6280\u8853\u30c8\u30ec\u30f3\u30c9\u306e\u4e2d\u3067\u3001\u8aad\u8005\u306e\u7686\u69d8\u306e\u30d3\u30b8\u30cd\u30b9\u3084'
            '\u7814\u7a76\u306b\u5c11\u3057\u3067\u3082\u304a\u5f79\u306b\u7acb\u3066\u308c\u3070\u5e78\u3044\u3067\u3059\u3002'
        )
        ph = _draw_text_block(c, reflection, MARGIN, y, CONTENT_W, styles['body_justified'])
        y -= ph + 5 * mm

        second_para = (
            '\u5f15\u304d\u7d9a\u304d\u3001\u6700\u65b0\u306e\u52d5\u5411\u3092\u8ffd\u3044\u3001\u5206\u304b\u308a\u3084\u3059\u304f\u304a\u5c4a\u3051\u3057\u3066\u307e\u3044\u308a\u307e\u3059\u3002'
            '\u3054\u610f\u898b\u3084\u3054\u8981\u671b\u304c\u3054\u3056\u3044\u307e\u3057\u305f\u3089\u3001\u304a\u6c17\u8efd\u306b\u304a\u77e5\u3089\u305b\u304f\u3060\u3055\u3044\u3002'
        )
        ph = _draw_text_block(c, second_para, MARGIN, y, CONTENT_W, styles['body_justified'])
        y -= ph + 15 * mm

    y -= 10 * mm
    _draw_separator(c, y)
    y -= 12 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS_BOLD, 14)
    c.drawString(MARGIN, y, '\u6b21\u53f7\u4e88\u544a')

    y -= 12 * mm
    preview_text = (
        '\u6b21\u53f7\u3067\u306f\u3001\u5f15\u304d\u7d9a\u304d\u4e2d\u56fd\u30c6\u30c3\u30af\u30fbAI\u5206\u91ce\u306e\u30cb\u30e5\u30fc\u30b9\u3092'
        '\u53b3\u9078\u3057\u3066\u304a\u5c4a\u3051\u3057\u307e\u3059\u3002\u304a\u697d\u3057\u307f\u306b\u3002'
    )
    ph = _draw_text_block(c, preview_text, MARGIN, y, CONTENT_W, styles['body'])
    y -= ph + 20 * mm

    box_h = 40 * mm
    box_y = max(y - box_h, 25 * mm)
    c.setFillColor(LIGHT_BEIGE)
    c.setStrokeColor(BURGUNDY)
    c.setLineWidth(0.5)
    c.rect(MARGIN, box_y, CONTENT_W, box_h, fill=1, stroke=1)

    iy = box_y + box_h - 10 * mm
    c.setFillColor(BURGUNDY)
    c.setFont(FONT_SANS_BOLD, 10)
    c.drawCentredString(W / 2, iy, 'CCC Daily News \u8cfc\u8aad\u6848\u5185')

    iy -= 10 * mm
    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SERIF, 8)
    c.drawCentredString(W / 2, iy, '\u6bce\u65e5\u306e\u4e2d\u56fd\u30c6\u30c3\u30af\u30fbAI\u30cb\u30e5\u30fc\u30b9\u3092\u65e5\u672c\u8a9e\u3067\u304a\u5c4a\u3051\u3057\u307e\u3059')

    iy -= 8 * mm
    c.setFont(FONT_SANS, 7)
    c.setFillColor(WARM_GRAY)
    c.drawCentredString(W / 2, iy, '\u914d\u4fe1\u306b\u3064\u3044\u3066\u306e\u304a\u554f\u3044\u5408\u308f\u305b: info@cccdailynews.com')

    c.setFillColor(CHARCOAL)
    c.setFont(FONT_SANS, 6.5)
    c.drawCentredString(W / 2, 25 * mm, f'CCC Daily News \u7b2c{issue_number}\u53f7 | {date_str}')
    c.setFillColor(WARM_GRAY)
    c.setFont(FONT_SANS, 6)
    c.drawCentredString(W / 2, 20 * mm, '\u00a9 2026 CCC Daily News. All rights reserved.')

    _draw_footer(c, 8)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def generate_issue_pdf(issue_number, date_str, headline, summary, articles,
                       output_dir='generated_pdfs', editors_note=""):
    """
    Generate an 8-page PDF newsletter.

    Args:
        issue_number: int
        date_str: str (e.g., '2026年3月20日')
        headline: str - main headline (Japanese)
        summary: str - summary paragraph (Japanese)
        articles: list of dicts with keys including title_jp, content_jp, summary_jp
        output_dir: str
        editors_note: str - AI-generated editor's note in Japanese

    Returns:
        str - full path to the generated PDF file
    """
    register_fonts()
    styles = _create_styles()

    os.makedirs(output_dir, exist_ok=True)

    filename = f'ccc_daily_news_{issue_number:03d}.pdf'
    filepath = os.path.join(output_dir, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    c.setTitle(f'CCC Daily News \u7b2c{issue_number}\u53f7')
    c.setAuthor('CCC Daily News')

    _draw_cover(c, issue_number, date_str, headline, summary, articles)
    c.showPage()

    _draw_toc(c, issue_number, date_str, articles)
    c.showPage()

    indices_p3 = [i for i in [0, 1] if i < len(articles)]
    _draw_featured_page(c, styles, issue_number, date_str, articles, 3, indices_p3)
    c.showPage()

    indices_p4 = [i for i in [2, 3] if i < len(articles)]
    if indices_p4:
        _draw_featured_page(c, styles, issue_number, date_str, articles, 4, indices_p4)
    else:
        _draw_page_bg(c)
        _draw_header_bar(c, 4, issue_number, date_str)
        _draw_footer(c, 4)
    c.showPage()

    indices_p5 = [i for i in [4, 5] if i < len(articles)]
    if indices_p5:
        _draw_category_page(c, styles, issue_number, date_str, articles, 5, indices_p5)
    else:
        _draw_page_bg(c)
        _draw_header_bar(c, 5, issue_number, date_str)
        _draw_footer(c, 5)
    c.showPage()

    indices_p6 = [i for i in [6, 7] if i < len(articles)]
    if indices_p6:
        _draw_category_page(c, styles, issue_number, date_str, articles, 6, indices_p6)
    else:
        _draw_page_bg(c)
        _draw_header_bar(c, 6, issue_number, date_str)
        _draw_footer(c, 6)
    c.showPage()

    _draw_data_page(c, styles, issue_number, date_str, articles)
    c.showPage()

    _draw_editors_note(c, styles, issue_number, date_str, articles, editors_note)
    c.showPage()

    c.save()
    return filepath
