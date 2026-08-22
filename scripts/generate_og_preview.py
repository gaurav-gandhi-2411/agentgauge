"""Regenerate assets/brand/og-preview.svg and .png.

Run from a throwaway venv with fontTools, brotli, resvg-py, and pillow --
never this project's own dev environment (this script is design tooling,
not shipped code).

Shares the Calibration palette and type vocabulary with the sibling
package tracegauge (token-efficiency-scorer's assets/brand/BRAND.md is
the canonical reference), but a distinct motif: agentgauge measures
whether a change moved anything at all -- a paired before/after
comparison, not a single graduated reading or a pass/fail gate. Two
aligned marks joined by a dimension-line connector (the technical-drawing
convention for "the gap between these two is what's being measured"),
deliberately readable even when the delta is near zero -- both of this
package's own academic papers report null/near-null results as real
findings, not a broken measurement, and the hero image should not imply
"more spread = better."

Every character in the wordmark/tagline is a real path traced from this
file's own bundled font files via fontTools, never a live <text> element
-- this rasterization pipeline's SVG renderer does not do real
font-family matching (proven in tracegauge's AU1 rasterization: identical
font_extents regardless of the requested font name), so text is a shape
problem here, not a typography problem. The bundled font files are
subsetted to alphanumerics + space only (no punctuation at all) -- the
period this design needs is hand-drawn as a trivial filled circle; every
other character is a real glyph outline.

Usage:
    uv venv --python 3.11 C:/some-throwaway-path
    uv pip install fonttools brotli resvg-py pillow --python C:/some-throwaway-path/Scripts/python.exe
    C:/some-throwaway-path/Scripts/python.exe scripts/generate_og_preview.py
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).parent.parent
FONT_DIR = ROOT / "assets" / "brand" / "fonts"
DISPLAY_FONT = str(FONT_DIR / "spacegrotesk-700.woff2")
BODY_FONT = str(FONT_DIR / "ibmplexsans-400.woff2")
OUT_SVG = ROOT / "assets" / "brand" / "og-preview.svg"
OUT_PNG = ROOT / "assets" / "brand" / "og-preview.png"

# Calibration palette (shared with tracegauge's assets/brand/BRAND.md)
INK = "#12140F"
PAPER = "#F0EDE4"
NEEDLE = "#C9622B"
GRAPHITE = "#5B5D53"
TICK = "#A79F8C"

W, H = 1280, 640

_MANUAL_GLYPHS = {"-", "."}


def _manual_glyph_path(ch: str, font_size: float, cursor_x: float, y: float) -> tuple[str, float]:
    if ch == "-":
        w = font_size * 0.28
        h = font_size * 0.07
        gy = y - font_size * 0.32
        return f"M {cursor_x:.2f} {gy:.2f} h {w:.2f} v {h:.2f} h {-w:.2f} Z", font_size * 0.38
    if ch == ".":
        r = font_size * 0.045
        cx = cursor_x + r
        cy = y - r
        d = (
            f"M {cx - r:.2f} {cy:.2f} "
            f"a {r:.2f} {r:.2f} 0 1 0 {2 * r:.2f} 0 "
            f"a {r:.2f} {r:.2f} 0 1 0 {-2 * r:.2f} 0 Z"
        )
        return d, font_size * 0.22
    raise ValueError(f"no manual glyph for {ch!r}")


def text_to_path(
    font_path: str, text: str, font_size: float, x: float, y: float
) -> tuple[str, float]:
    font = TTFont(font_path)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = font_size / font["head"].unitsPerEm
    hmtx = font["hmtx"]
    path_parts = []
    cursor_x = x

    for ch in text:
        if ch in _MANUAL_GLYPHS:
            d, advance = _manual_glyph_path(ch, font_size, cursor_x, y)
        else:
            codepoint = ord(ch)
            if codepoint not in cmap:
                raise ValueError(f"glyph for {ch!r} not in font {font_path}")
            glyph_name = cmap[codepoint]
            advance = hmtx[glyph_name][0] * scale
            svg_pen = SVGPathPen(glyph_set)
            transform_pen = TransformPen(svg_pen, (scale, 0, 0, -scale, cursor_x, y))
            glyph_set[glyph_name].draw(transform_pen)
            d = svg_pen.getCommands()
        if d:
            path_parts.append(d)
        cursor_x += advance

    return " ".join(path_parts), cursor_x - x


def build_svg() -> str:
    baseline_y = 380
    before_x, after_x = 190, 470
    before_y = baseline_y
    after_y = baseline_y - 14  # deliberately near-equal -- see module docstring
    dim_y = 220

    pins = (
        f'<line x1="{before_x}" y1="{before_y}" x2="{before_x}" y2="{dim_y}" '
        f'stroke="{GRAPHITE}" stroke-width="3" stroke-dasharray="1 8" stroke-linecap="round"/>'
        f'<line x1="{after_x}" y1="{after_y}" x2="{after_x}" y2="{dim_y}" '
        f'stroke="{GRAPHITE}" stroke-width="3" stroke-dasharray="1 8" stroke-linecap="round"/>'
    )
    dim_line = (
        f'<line x1="{before_x}" y1="{dim_y}" x2="{after_x}" y2="{dim_y}" '
        f'stroke="{PAPER}" stroke-width="6" stroke-linecap="round"/>'
        f'<line x1="{before_x}" y1="{dim_y - 16}" x2="{before_x}" y2="{dim_y + 16}" '
        f'stroke="{PAPER}" stroke-width="6" stroke-linecap="round"/>'
        f'<line x1="{after_x}" y1="{dim_y - 16}" x2="{after_x}" y2="{dim_y + 16}" '
        f'stroke="{PAPER}" stroke-width="6" stroke-linecap="round"/>'
    )
    ground = (
        f'<line x1="{before_x - 60}" y1="{baseline_y + 40}" x2="{after_x + 60}" y2="{baseline_y + 40}" '
        f'stroke="{TICK}" stroke-width="2" opacity="0.5"/>'
    )
    marks = (
        f'<circle cx="{before_x}" cy="{before_y}" r="18" fill="none" stroke="{TICK}" stroke-width="5"/>'
        f'<circle cx="{after_x}" cy="{after_y}" r="18" fill="{NEEDLE}"/>'
    )

    motif = ground + pins + dim_line + marks

    name_d, _ = text_to_path(DISPLAY_FONT, "agentgauge", 72, 720, 300)
    tag_d, _ = text_to_path(BODY_FONT, "Whether the change moved anything at all.", 26, 720, 356)
    text = f'<path d="{name_d}" fill="{PAPER}"/><path d="{tag_d}" fill="{TICK}"/>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<rect width="{W}" height="{H}" fill="{INK}"/>
{motif}
{text}
</svg>'''


def main() -> None:
    svg = build_svg()
    OUT_SVG.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT_SVG}")

    import resvg_py

    png_data = resvg_py.svg_to_bytes(svg_path=str(OUT_SVG), width=W, height=H)
    img = Image.open(io.BytesIO(bytes(png_data))).convert("RGB")
    img.save(OUT_PNG, format="PNG")
    print(f"wrote {OUT_PNG}")

    data = OUT_PNG.read_bytes()
    pos = 8
    chunks = []
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunks.append(data[pos + 4 : pos + 8].decode("ascii"))
        pos += 8 + length + 4
    w, h, bitdepth, colortype = struct.unpack(">IIBB", data[16:26])
    print(
        f"verify: {w}x{h}, bitdepth={bitdepth}, colortype={colortype} (2=RGB truecolor), chunks={chunks}"
    )
    assert (w, h, bitdepth, colortype) == (W, H, 8, 2), "PNG constraint check failed"
    assert chunks == ["IHDR", "IDAT", "IEND"], "unexpected PNG chunks -- not maximally conservative"


if __name__ == "__main__":
    main()
