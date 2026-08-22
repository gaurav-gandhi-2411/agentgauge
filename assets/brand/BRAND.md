# agentgauge brand system — Calibration

Shares the Calibration identity with the sibling package `tracegauge`
(`token-efficiency-scorer`'s `assets/brand/BRAND.md` is the canonical
palette/type reference — this file documents only what's specific to
this package: the motif and this repo's own asset list).

## Why a different motif, not a recolored gauge

`tracegauge` reports a continuous reading against a calibrated band.
`adk-tracegauge` reports whether a run clears a threshold line. Neither
is what `agentgauge` measures: this package's own work — both of its
academic papers, its regression/audit tooling — is fundamentally a
*paired comparison*. Did rewriting a tool description change task
success? Did a code change move a metric at all? The finding is the
*gap* between a before state and an after state, and — this is the part
that shapes the motif — a gap of zero is itself a real, reportable
finding for this package (both papers' central results are falsifications
and null effects, not positive ones). A gauge needle or a threshold gate
would visually imply "there is always a verdict to read off." A
dimension-line — the technical-drawing convention for explicitly marking
the distance between two points — reads correctly whether that distance
is large or collapsed to nothing.

## Color

Same seven Calibration tokens as `tracegauge` (see that repo's
`BRAND.md` for the full table and the reasoning behind each). This
motif uses four of the seven directly:

| Token | Hex | Role in this motif |
|---|---|---|
| `paper` | `#F0EDE4` | The dimension-line bracket, the wordmark |
| `needle` | `#C9622B` | The "after" mark — a live reading, not a verdict |
| `graphite` | `#5B5D53` | The pin lines connecting each mark to the bracket |
| `tick` | `#A79F8C` | The "before" mark (hollow), the ground line, the tagline |

(`calibrated`/`regression` are deliberately unused here — this motif
never asserts pass/fail, only "here is the measured gap," consistent
with this package's own papers never treating a null result as a
failure.)

## Type

Same as `tracegauge`: Space Grotesk 700 for the wordmark, IBM Plex Sans
400 for the tagline. Both open (SIL OFL), bundled locally in
`assets/brand/fonts/` (copied from `token-efficiency-scorer`'s own
bundled copies — same license, same files, no CDN dependency).

## Assets in this directory

- `fonts/spacegrotesk-700.woff2`, `fonts/ibmplexsans-400.woff2` — the two
  weights this package's hero image needs. Subsetted to alphanumerics +
  space only (no punctuation) — the period this design needs is
  hand-drawn, not a font glyph (see `scripts/generate_og_preview.py`'s
  docstring).
- `og-preview.svg` — 1280×640 link-unfurl preview (GitHub/Slack/social).
  Direction B composition: motif left (dominates), outlined wordmark +
  tagline right. Every character is a real path traced from this
  directory's own font files via `fontTools`, never a live `<text>`
  element — this rasterization pipeline's SVG renderer does not do real
  font-family matching (proven in `tracegauge`'s AU1 rasterization:
  identical `font_extents` regardless of the requested font name), so
  text is a shape problem here, not a typography problem.
- `og-preview.png` — 1280×640 PNG export of the above, for repo Settings
  → General → Social preview (GitHub serves this PNG directly; it
  doesn't render the SVG). RGB truecolor, 8-bit, no alpha, no
  interlacing, no ICC profile, exactly `IHDR+IDAT+IEND` — matching
  `tracegauge`'s own maximally-conservative PNG structure after its
  AU1/BR2/BS1 404 investigation.

Regenerate via `scripts/generate_og_preview.py` (see that file's
docstring for the throwaway-venv setup — never run design tooling
against this package's own dev environment).

Not yet done: a favicon, wordmark lockup, or README badge for this
package — this wave built only the hero/social-preview image.
