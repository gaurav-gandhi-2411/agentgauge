"""Regenerate the logo concepts, favicon set, 1200x630 OG preview and contact sheet.

DRAFT identity assets (branch brand/identity-drafts). Builds on the existing system in
assets/brand/BRAND.md: Calibration palette tokens (ink/paper/needle/graphite/tick only) and the
dimension-line motif (hollow "before" mark, filled "after" mark, bracket marking the gap; a zero
gap is a valid reading, so nothing here implies pass/fail). Text is always traced to paths with
fontTools (reusing text_to_path from generate_og_preview.py), never live <text>.

Run from a throwaway venv, never the project's dev environment:
    uv venv --python 3.11 C:/some-throwaway-path
    uv pip install fonttools brotli resvg-py pillow --python C:/some-throwaway-path/Scripts/python.exe
    C:/some-throwaway-path/Scripts/python.exe scripts/generate_brand_assets.py
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import resvg_py  # noqa: E402
from generate_og_preview import (  # noqa: E402
    BODY_FONT,
    DISPLAY_FONT,
    GRAPHITE,
    INK,
    NEEDLE,
    PAPER,
    TICK,
    text_to_path,
)
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).parent.parent
BRAND = ROOT / "assets" / "brand"
SHEET = ROOT / "reports" / "screenshots" / "brand-identity-drafts" / "contact-sheet.png"

# Per-background colour roles. "fg" = structure (bracket, wordmark), "mid" = the hollow
# "before" mark, "needle" = the filled "after" mark. On paper, paper-coloured structure is
# invisible, so the light variant swaps fg to ink and mid to graphite (tick is < 3:1 on paper).
THEMES = {
    "light": {"bg": PAPER, "fg": INK, "mid": GRAPHITE, "needle": NEEDLE},
    "dark": {"bg": INK, "fg": PAPER, "mid": TICK, "needle": NEEDLE},
}

Mark = tuple[str, float, float]  # (svg fragment, width, height)


def mark_a(t: dict[str, str]) -> Mark:
    """Concept A: before/after marks under a bracket whose legs are the pins."""
    s = (
        f'<path d="M14 30V15H50V30" fill="none" stroke="{t["fg"]}" stroke-width="5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="14" cy="45" r="8" fill="none" stroke="{t["mid"]}" stroke-width="5"/>'
        f'<circle cx="50" cy="42" r="9" fill="{t["needle"]}"/>'
    )
    return s, 64, 64


def mark_b(t: dict[str, str]) -> Mark:
    """Concept B: 'ag' monogram; the gap between the letters is the dimension line."""
    size, base = 66.0, 46.0
    a_d, a_w = text_to_path(DISPLAY_FONT, "a", size, 0, base)
    gap = 26.0
    g_d, _ = text_to_path(DISPLAY_FONT, "g", size, a_w + gap, base)
    ymid = base - size * 0.24
    x0, x1 = a_w + 2, a_w + gap - 2
    s = (
        f'<path d="{a_d}" fill="{t["fg"]}"/><path d="{g_d}" fill="{t["needle"]}"/>'
        f'<path d="M{x0:.1f} {ymid:.1f}H{x1:.1f}M{x0:.1f} {ymid - 9:.1f}V{ymid + 9:.1f}'
        f'M{x1:.1f} {ymid - 9:.1f}V{ymid + 9:.1f}" fill="none" stroke="{t["mid"]}" '
        f'stroke-width="3.5" stroke-linecap="round"/>'
    )
    return s, a_w + gap + a_w * 1.02, 64


def mark_c(t: dict[str, str]) -> Mark:
    """Concept C: a bare tick-and-bracket glyph, no circles; right leg is the offset 'after'."""
    s = (
        f'<path d="M12 50V16H52" fill="none" stroke="{t["fg"]}" stroke-width="6" '
        f'stroke-linecap="square" stroke-linejoin="miter"/>'
        f'<path d="M52 16V44" fill="none" stroke="{t["needle"]}" stroke-width="6" '
        f'stroke-linecap="square"/>'
        f'<path d="M4 56H60" fill="none" stroke="{t["mid"]}" stroke-width="3.5" '
        f'stroke-linecap="round"/>'
    )
    return s, 64, 64


CONCEPTS = {"a": mark_a, "b": mark_b, "c": mark_c}


def svg_doc(inner: str, w: float, h: float, bg: str | None = None) -> str:
    """Wrap a fragment in an <svg>; optional full-bleed background rect."""
    rect = f'<rect width="{w:g}" height="{h:g}" fill="{bg}"/>' if bg else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" '
        f'width="{w:g}" height="{h:g}">{rect}{inner}</svg>\n'
    )


def lockup(concept: str, theme: str) -> tuple[str, float, float]:
    """Mark + traced 'agentgauge' wordmark, transparent background."""
    t = THEMES[theme]
    m, mw, mh = CONCEPTS[concept](t)
    name_d, nw = text_to_path(DISPLAY_FONT, "agentgauge", 44, mw + 18, 44)
    inner = f'{m}<path d="{name_d}" fill="{t["fg"]}"/>'
    return inner, mw + 18 + nw + 2, mh


def write_concepts() -> None:
    for c, fn in CONCEPTS.items():
        for theme in THEMES:
            suffix = "" if theme == "light" else "-dark"
            inner, w, h = lockup(c, theme)
            (BRAND / f"logo-concept-{c}{suffix}.svg").write_text(svg_doc(inner, w, h), "utf-8")
            m, mw, mh = fn(THEMES[theme])
            (BRAND / f"logo-concept-{c}-mark{suffix}.svg").write_text(svg_doc(m, mw, mh), "utf-8")


def render(svg: str, w: int, h: int) -> Image.Image:
    """Rasterize an SVG string to an RGBA image at exactly w x h."""
    data = resvg_py.svg_to_bytes(svg_string=svg, width=w, height=h)
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def save_conservative_png(img: Image.Image, path: Path) -> None:
    """Save RGB/8-bit/no-alpha PNG and assert the IHDR+IDAT+IEND structure."""
    img.convert("RGB").save(path, format="PNG")
    data = path.read_bytes()
    pos, chunks = 8, []
    while pos < len(data):
        n = struct.unpack(">I", data[pos : pos + 4])[0]
        chunks.append(data[pos + 4 : pos + 8].decode("ascii"))
        pos += 12 + n
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    assert (depth, ctype) == (8, 2), f"{path.name}: not RGB8"
    assert chunks == ["IHDR", "IDAT", "IEND"], f"{path.name}: chunks {chunks}"
    print(f"wrote {path.name} {w}x{h} {len(data)} bytes")


def favicon_svg() -> str:
    """Recommended concept (A) on a rounded ink tile, mark scaled to leave 6 units of padding."""
    m, _, _ = mark_a(THEMES["dark"])
    inner = (
        f'<rect width="64" height="64" rx="12" fill="{INK}"/>'
        f'<g transform="translate(6 6) scale(0.8125)">{m}</g>'
    )
    return svg_doc(inner, 64, 64)


def write_favicons() -> None:
    svg = favicon_svg()
    (BRAND / "favicon.svg").write_text(svg, "utf-8")
    for name, px in (("favicon-32.png", 32), ("favicon-16.png", 16), ("apple-touch-icon.png", 180)):
        img = render(svg, px, px)
        if name == "apple-touch-icon.png":
            # iOS applies its own rounding: ship a full-bleed square, not a rounded tile.
            img = render(svg.replace('rx="12" ', ""), px, px)
        save_conservative_png(img, BRAND / name)


def write_og() -> None:
    W, H = 1200, 630
    t = THEMES["dark"]
    m, _, _ = mark_a(t)
    name_d, _ = text_to_path(DISPLAY_FONT, "agentgauge", 104, 400, 330)
    tag_d, _ = text_to_path(BODY_FONT, "Whether the change moved anything at all.", 30, 404, 392)
    inner = (
        f'<g transform="translate(100 187) scale(4)">{m}</g>'
        f'<path d="{name_d}" fill="{PAPER}"/><path d="{tag_d}" fill="{TICK}"/>'
    )
    svg = svg_doc(inner, W, H, INK)
    (BRAND / "og-preview-1200x630.svg").write_text(svg, "utf-8")
    save_conservative_png(render(svg, W, H), BRAND / "og-preview-1200x630.png")


def write_contact_sheet() -> None:
    font = ImageFont.load_default(size=14)
    cell, pad, label_w = 150, 12, 90
    sizes = (16, 32, 128)
    cols = [(s, th) for th in THEMES for s in sizes]
    lock_w, lock_h = 300, 120
    rows = len(CONCEPTS)
    width = label_w + len(cols) * (cell + pad) + pad
    # per concept: one mark row, one lockup row (light + dark side by side)
    row_h = cell + pad
    height = 40 + rows * (row_h + lock_h + pad) + pad
    sheet = Image.new("RGB", (width, height), "#888888")
    d = ImageDraw.Draw(sheet)
    for i, (s, th) in enumerate(cols):
        d.text((label_w + i * (cell + pad) + pad, 14), f"{th} {s}px", fill="white", font=font)
    y = 40
    for c, fn in CONCEPTS.items():
        d.text((pad, y + 4), f"concept {c.upper()}", fill="white", font=font)
        for i, (s, th) in enumerate(cols):
            m, mw, mh = fn(THEMES[th])
            w_px = s if mw >= mh else round(s * mw / mh)
            h_px = round(w_px * mh / mw)
            x = label_w + i * (cell + pad) + pad
            tile = Image.new("RGBA", (cell, cell), THEMES[th]["bg"])
            glyph = render(svg_doc(m, mw, mh), w_px, h_px)
            tile.alpha_composite(glyph, ((cell - w_px) // 2, (cell - h_px) // 2))
            sheet.paste(tile.convert("RGB"), (x, y))
        y += row_h
        for j, th in enumerate(THEMES):
            inner, lw, lh = lockup(c, th)
            w_px = lock_w
            h_px = round(lock_w * lh / lw)
            x = label_w + pad + j * (3 * (cell + pad))
            tile = Image.new("RGBA", (3 * cell + 2 * pad, lock_h), THEMES[th]["bg"])
            glyph = render(svg_doc(inner, lw, lh), w_px, h_px)
            tile.alpha_composite(glyph, ((tile.width - w_px) // 2, (lock_h - h_px) // 2))
            sheet.paste(tile.convert("RGB"), (x, y))
        y += lock_h + pad
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(SHEET, format="PNG", optimize=True)
    print(f"wrote {SHEET} {sheet.size}")


def _lum(hex_: str) -> float:
    ch = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colours."""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def print_contrast() -> None:
    for th, t in THEMES.items():
        for role in ("fg", "mid", "needle"):
            print(
                f"contrast {th}: {role} {t[role]} on {t['bg']} = {contrast(t[role], t['bg']):.2f}"
            )


def main() -> None:
    write_concepts()
    write_favicons()
    write_og()
    write_contact_sheet()
    print_contrast()


if __name__ == "__main__":
    main()
