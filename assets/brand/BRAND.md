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

Not yet done: a README badge for this package. (The favicon set and
wordmark lockups are drafted below; the 1280×640 hero image above is
unchanged.)

## Logo concepts (DRAFT, for GG to choose)

All three derive from the dimension-line motif, use only the tokens
above (`ink`, `paper`, `needle`, `graphite`, `tick`), and carry no
pass/fail colour. Every mark has a light-background and a dark-background
(`-dark`) file; `logo-concept-X.svg` is the lockup (mark + traced Space
Grotesk 700 wordmark), `logo-concept-X-mark.svg` the mark alone. All are
transparent-background. Regenerate with `scripts/generate_brand_assets.py`.
None is a gauge, dial, needle or bar-series, so none can be mistaken for
a recolour of `tracegauge`'s marks (dial-and-needle, then a bar series
with an accent bar).

- **A — bracket over paired marks.** A hollow "before" circle and a filled
  `needle` "after" circle sit under a bracket whose legs are the pin lines.
  The after mark is nudged up 3 units: a visible but small gap, so a zero
  gap still reads correctly. Most literal expression of the motif, and
  the sturdiest at 16 px (three bold shapes).
- **B — "ag" monogram.** Space Grotesk "a" and "g" with a dimension line
  spanning the space between them; the gap is the measurement. Most
  ownable, but the mark-only form is wide (about 1.6:1) and the dimension
  line is hairline-thin at 16 px, so it is a poor favicon.
- **C — tick-and-bracket glyph.** An ink corner bracket, a `needle` leg
  that stops short of the left leg (the offset), and a ground line.
  Minimal, but the least tied to the product name and the most generic.

**Recommended: A.** It carries the hollow-before / filled-after /
bracket-gap story without explanation, survives 16 px, and is what the
favicon, apple-touch icon and 1200×630 OG image use. B is the runner-up
if a wordmark-first identity is preferred.

Contrast (WCAG 2.x, computed by `generate_brand_assets.py`):

| Background | Role (token) | Ratio |
|---|---|---|
| paper `#F0EDE4` | structure / wordmark (ink) | 15.84 |
| paper | hollow "before" mark (graphite) | 5.72 |
| paper | "after" mark (needle) | 3.41 |
| ink `#12140F` | structure / wordmark (paper) | 15.84 |
| ink | hollow "before" mark (tick) | 7.05 |
| ink | "after" mark (needle) | 4.65 |

All graphical marks clear the 3:1 non-text threshold; the wordmark clears
AA text. `tick` is not used on paper (below 3:1), hence graphite there.

Usage rules (draft): clear space of half the mark height on every side;
minimum size 16 px for the mark alone (concepts A/C), 96 px wide for a
lockup; use the `-dark` file on ink/dark surfaces and the default file on
paper/light ones; never recolour `needle`, never add a green/red pair.

Files: `logo-concept-{a,b,c}[-mark][-dark].svg`, `favicon.svg`,
`favicon-32.png`, `favicon-16.png`, `apple-touch-icon.png` (180×180,
full-bleed square), `og-preview-1200x630.svg` / `.png` (the 1280×640
files are unchanged). PNGs keep the `IHDR+IDAT+IEND` RGB-8 structure.
Side-by-side preview:
`reports/screenshots/brand-identity-drafts/contact-sheet.png`.
