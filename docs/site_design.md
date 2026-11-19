# Site design: tokens, fonts and how to change them (D57, D58)

The static site (`python run.py site`, written to `site/`) has one light theme, the Hallmark theme Editorial (D58). There is no dark mode and no theme toggle. D58 replaced the visual layer of D57 (dark navy, Inter, IBM Plex Mono); the structure D57 introduced (the home-page order, the answer panels, the research links, the split labels and the chart labels) is unchanged. Every colour and every font goes through a token, so a change is made in one place and then checked.

## Where things live

| What | File | Notes |
|---|---|---|
| Page colours, fonts, rule weights | `src/site_assets/style.css`, the first `:root` block | The theme's names hold the values (`--color-paper`, `--color-paper-2`, `--color-paper-3`, `--color-ink`, `--color-ink-2`, `--color-muted`, `--color-rule`, `--color-rule-2`, `--color-accent`, `--color-focus`, `--color-error`, `--font-display`, `--font-body`, `--rule-hair`, `--rule-mid`, `--rule-heavy`). The names from before D57 (`--bg`, `--card`, `--ink`, `--text`, `--muted`, `--line`, `--soft`, `--accent`, `--increase`, `--hold`, `--decrease`, `--warn-*`, `--info-*`, `--ok-*`, `--bad-*`, …) and from D57 (`--navy`, `--slate`, `--steel`, `--teal`, `--coral`, `--font-ui`, `--font-mono`, …) are kept as aliases of the editorial roles, so older rules keep working. |
| Chart colours (SVG `fill`/`stroke` and the redrawn track record in `app.js`) | `PALETTE` in `src/site_dashboard.py` | `site_build.PALETTE` and `site_interactive.PALETTE` are the same dictionary. Legend swatches use the matching `--chart-<key>` tokens in `style.css`, so each value is written twice: in `PALETTE` and in `--chart-<key>`. Change both. The keys have not changed since before D57. |
| Fonts | `src/site_assets/fonts/` | Copied to `site/fonts/` by the build (next to `site/assets/`, which holds only text files); the stylesheet loads them from `../fonts/`. |
| Icons | `--mask-*` tokens in `style.css` | SVG source inside a CSS mask, filled with a colour token; no `<svg>` element is added to the page (the home page keeps at most three charts, a test checks this). |
| The theme record | the comment lines at the top of `style.css` | The Hallmark stamp, the critique line, the waivers and dismissals of the design linter, each with its reason. |
| Design record | `docs/deviations.md`, D57 and D58 | Contrast ratios and byte sizes. |

## Palette (D58)

The theme states its colours in OKLCH; the hex values are the sRGB conversions used in the contrast checks.

| Role | Token | Value |
|---|---|---|
| Page and panels (warm white paper) | `--color-paper` (`--bg`, `--card`) | `oklch(97% 0.007 86)` = `#F7F5F0` |
| Wells (notes, notices, code) | `--color-paper-2` | `oklch(94% 0.010 86)` = `#EEEBE4` |
| Pressed control | `--color-paper-3` | `oklch(91% 0.012 84)` = `#E5E1D9` |
| Heads, key numbers, rules, ink band | `--color-ink` (`--ink`) | `oklch(16% 0.012 280)` = `#0C0D12` |
| Reading text | `--color-ink-2` (`--text`) | `oklch(29% 0.011 280)` = `#2A2B31` |
| Captions and labels | `--color-muted` (`--muted`) | `oklch(48% 0.010 75)` = `#615D57` |
| Hairlines | `--color-rule` (`--line`) | `oklch(85% 0.009 85)` = `#D0CDC7` |
| Hairline under a table head, edges of fields and scales | `--color-rule-2` (`--field-edge`) | `oklch(64% 0.010 80)` = `#8F8C85` |
| Printer's green: link hover, controls, focus only | `--color-accent`, `--color-focus` | `oklch(49% 0.130 152)` = `#007439`; `oklch(52% 0.135 152)` = `#067E3F` |
| Failed checks and the caution mark | `--color-error` | `oklch(52% 0.19 27)` = `#BE2323` |
| Outcome Increase ▲ | `--class-increase` | `#009E73` |
| Outcome Hold ■ | `--class-hold` | `#0072B2` |
| Outcome Decrease ▼ | `--class-decrease` | `#D55E00` |
| Hold marker in charts | `--class-hold-grey` | `#6E6E6E` |
| Model series in charts | `PALETTE["blue"]`, `--chart-blue` | `#2A2B31` (ink-2) |
| Actual series and cursor in charts | `PALETTE["ink"]`, `--chart-ink` | `#0C0D12` (ink) |
| Axis labels in charts | `PALETTE["black"]`, `--chart-black` | `#615D57` (muted) |
| Holdout band in charts | `PALETTE["shade"]`, `--chart-shade` | `#F3F0E9` |
| Candidate specification, class frequencies | `PALETTE["orange"]`, `PALETTE["sky"]` | `#B87F06`, `#3293C6` (the Okabe–Ito hues, darkened in OKLCH at a fixed hue to 3:1) |

Rules for the colours:
- The outcome colours appear only on marks: the square behind a ▲ ■ ▼ glyph, a probability bar, a chart point. The word next to a mark is always ink, so colour is never the only cue and no class colour is used as text.
- Increase `#009E73` reaches 3:1 on the paper (3.14) and on the holdout band (3.01) but not on `paper-2` (2.87). For that reason no class mark sits on a `paper-2` well; the probability tracks, the top row of a card and the holdout band are kept at paper or lighter.
- The printer's green is for links (hover), controls and focus only. It is never used for an outcome or a chart series. Its CIEDE2000 distance from Increase is 16.6 (the focus green 13.3).
- No rule is green. Sections and tables open with an ink rule (`--rule-heavy` 4px for a section head, `--rule-mid` 2px for a table, a metric or the research index); 1px hairlines part rows. Corners are square and nothing has a shadow.

## Fonts (D58)

| File | Family and setting | Source (exact download) | sha256 of the downloaded file |
|---|---|---|---|
| `bricolage-800-condensed.woff2` | Bricolage Grotesque 800, `wdth 75`, `opsz 96` (heads, the large figures) | `https://raw.githubusercontent.com/ateliertriay/bricolage/8070cdb6a383aafd10792111cd94e4d472aa0f0c/fonts/variable/BricolageGrotesque%5Bopsz%2Cwdth%2Cwght%5D.ttf` | `413e7357809ddd12fd80a96a8a396de0e401638d4acd3cb3e37532f0472ac682` |
| `bricolage-500.woff2` | Bricolage Grotesque 500, `wdth 100`, `opsz 12` (labels, captions, nav, controls, tables, figures in tables and panels) | same file | same |
| `source-serif-4-400.woff2` | Source Serif 4 400 (reading text) | `https://github.com/adobe-fonts/source-serif/releases/download/4.005R/source-serif-4.005_Desktop.zip` (release tag `4.005R`), member `source-serif-4.005_Desktop/TTF/SourceSerif4-Regular.ttf` | zip `549fdb8f9a682bd06944298621404969f6de77c2e422ff3b8244a1dcd6a0c425`; member `e5a4ee6a3d87bb9024796be390c6771e2a0eb1883dae25effaf57ca01668e24b` |
| `source-serif-4-600.woff2` | Source Serif 4 600 (`strong` and figures inside sentences) | same zip, member `source-serif-4.005_Desktop/TTF/SourceSerif4-Semibold.ttf` | member `36db62940cb5728b12b1802476dc7fcf4c6c519a7bdd476ba23a4e555fc4655f` |

Notes on the sources:
- **Bricolage Grotesque.** The repository `ateliertriay/bricolage` has no GitHub releases or tags. The file was therefore downloaded at the commit that last changed `fonts/variable/` (`8070cdb6a383aafd10792111cd94e4d472aa0f0c`, 19 July 2023), and the URL above is pinned to that commit.
- **Licences.** Both families are licensed under the SIL Open Font License 1.1. `BricolageGrotesque-OFL.txt` is `OFL.txt` from the same commit (sha256 `4b5a7d8f37f5602621c8a8d7358a6a2e71317e6c231c661e15aef0275d3e07ba`). `SourceSerif4-LICENSE.md` is `LICENSE.md` from the zip.
- **Italic.** The site uses no italic, so none is shipped.

**Instances and subsetting.** The fonts were made with fontTools 4.67; writing woff2 also needs the `brotli` package, which is not in `requirements*.txt`.
- **Bricolage instances.** The two Bricolage files are static instances of the variable font. The condensed width is built into the file, so the stylesheet needs no `font-variation-settings`:

  ```
  python -m fontTools.varLib.instancer BricolageGrotesque[opsz,wdth,wght].ttf wght=800 wdth=75 opsz=96 -o b800.ttf
  python -m fontTools.varLib.instancer BricolageGrotesque[opsz,wdth,wght].ttf wght=500 wdth=100 opsz=12 -o b500.ttf
  ```

- **Subset.** Every file is then subset to Basic Latin, Latin-1 and the symbols the site uses:

  ```
  python -m fontTools.subset <input> --unicodes="U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-2019,U+201C-201D,U+2026,U+2192,U+2212,U+2248,U+2264-2265,U+25A0,U+25B2,U+25BC" --layout-features='kern,tnum,lnum,onum,case,liga' --flavor=woff2 --no-hinting --desubroutinize --name-IDs='*' --output-file=<output>
  ```

- **Fallbacks.** Every `@font-face` uses `font-display: swap`, and each family has a system fallback (`--font-display`, `--font-body`).

**Figures.** Both families have tabular (`tnum`) and lining (`lnum`) figures, checked in the downloaded files' GSUB tables. Every number is set with `font-variant-numeric: tabular-nums lining-nums`, and the body text is set lining too, because nearly every number in a sentence is a ledger value. Bricolage Grotesque has no ▲ ■ ▼ glyphs, so the marks are set in Source Serif 4, which has them.

**Code.** The theme sets no monospace face. The one exception is the copy-paste commands on `run.html` and the file paths in `<code>`, which use a system monospace stack (`--font-code`); no web font is downloaded for them.

## How to change a colour

1. Edit the value in the first `:root` block of `src/site_assets/style.css`. Change the theme name (for example `--color-muted`), not an alias.
2. If the colour is also used in charts, change the same entry in `PALETTE` (`src/site_dashboard.py`) and the matching `--chart-<key>` token.
3. Check the contrast:
   - Text needs 4.5:1 against `#F7F5F0` and against the `paper-2` wells `#EEEBE4`.
   - Marks, chart lines and field edges need 3:1 against the paper. Chart marks also need 3:1 against the holdout band `#F3F0E9`.
   - A short check (sRGB hex only):

   ```
   python -c "f=lambda h:[(c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4) for c in (int(h[i:i+2],16)/255 for i in (1,3,5))]; L=lambda h:0.2126*f(h)[0]+0.7152*f(h)[1]+0.0722*f(h)[2]; r=lambda a,b:(max(L(a),L(b))+0.05)/(min(L(a),L(b))+0.05); print(r('#009E73','#F7F5F0'), r('#009E73','#F3F0E9'))"
   ```

4. Rebuild and test: `python run.py site`, then `python -m pytest -q`. `tests/test_site.py` checks that every chart colour is in `PALETTE` and that no external font, `@import` or CDN is loaded.
5. Run the design linter on the built pages if Node is available: `node <hallmark>/scripts/sloplint.mjs site/*.html site/assets/style.css --genre editorial --render`.
6. Record the change in `docs/deviations.md`.

## How to change a font

1. Download the font from the project's own GitHub release, or from its repository at a pinned commit when it has no releases.
2. Record the URL, the tag or commit, and the sha256 here.
3. Make the static instance if needed, subset it with the commands above, and replace the file in `src/site_assets/fonts/`. Keep the file name, or change the `@font-face` rule.

Fonts are never taken from Google Fonts or a CDN, and the stylesheet has no `@import` (a test checks both).

## How to switch to another theme

The visual layer is the token block, the `@font-face` rules and the last block of `style.css` (headed "D58: Hallmark Editorial theme"). The HTML, ids, classes, data attributes and script hooks do not depend on the theme. To switch:
1. **Tokens.** Run `node <hallmark>/scripts/theme.mjs scaffold <slug> --redesign restyle --dir <a scratch folder>`. The scaffold must not write `tokens.css`/`base.css` into the repository, and the site test forbids `@import`. Copy its tokens into the first `:root` block.
2. **Aliases.** Point the old token names at the new roles. Then replace the theme block at the end of `style.css`, keeping the class names.
3. **Fonts.** Replace the files and the `@font-face` rules as described above.
4. **Chart colours.** Set `PALETTE` and the `--chart-*` tokens for the new background, and recompute every pair listed in the palette section.
5. **Record.** Rewrite the Hallmark stamp, critique and waiver lines at the top of `style.css`. Rebuild, run the tests and the linter, and record the switch as a new entry in `docs/deviations.md`, with the byte sizes (`config/site_budget.json`).

## Motion

The only motion is on state changes, at 150 ms or less:
- colour on hover and pressed controls;
- the underline of a link turning green;
- the opacity of a track-record redraw;
- the reorder of the factor-effects rows.

There is no reveal and nothing moves on scroll. Under `prefers-reduced-motion: reduce` every transition is off.

## Russia, China, ECB page (D59)

- **Files.** `src/site_assets/partners.css` and `src/site_assets/partners.js`, copied to `site/assets/` and linked only from `corridor.html` (`EXTRA_CSS` in `src/site_build.py`), so the home-page budget does not carry them. `partners.css` opens with a Hallmark stamp line and uses the tokens of the first `:root` of `style.css` only; it declares no colour of its own.
- **Series.** NBK ink `--chart-ink` (solid, 2.5px), Russia `--chart-orange` (solid), China `--chart-sky` (dashed 6 4), ECB `--chart-black` (dotted 2 3). The dash is a second cue next to the colour, and the legend swatches repeat it (`border-left-style`). No outcome-class colour is used for a partner.
- **Contrast on the paper `#F7F5F0`.** Ink 17.81:1, ink-2 `#2A2B31` 12.95:1, warm grey `#615D57` 6.00:1, ochre `#B87F06` 3.17:1, sky `#3293C6` 3.15:1; every line and bar is at least 3:1. The gridlines `#D0CDC7` (1.46:1) are decorative.
- **Series pills.** A pressed series pill keeps the paper ground with a heavy ink rule under it, so the swatch stays visible. An off pill is muted with a faded swatch. A series without data in the current view (the ECB in the real view) is disabled and says why in its tooltip.
- **Mechanism.** `ol.mech-steps`: five columns under a 2px ink rule, numbered by a CSS counter in the condensed head face. It becomes one column under 760 px.
- **Export bars.** `ul.trade-bars`: name, bar and value in a grid; the bar width is the share relative to the largest share (`--w`). Under 480 px the bar moves under the name.
- **Tables.** Tables are set in the label face, which ships weight 500 only, so `partners.css` keeps figures in tables at 500 instead of a synthesised 600. The other pages still ask for 600 in table cells (unchanged here).
- **Research index.** The seventh link uses `--mask-partners`, a globe drawn like the other masks (24px, 1.75 stroke).

## Home page as a story (D60)

- **Order.** Nothing is folded and every block stays in its step:
  - the opening section holds the question, the answer sentence (`p.story-answer`, `--text-lg`) and the three-panel answer desk;
  - the overview and context strip follow;
  - then steps 1 to 7, then a closing section "Read further" with the research index (four columns above 960 px).
- **Step heads.** Each h2 reads "N. Title." (`span.step-tag`, on its own line, same face, weight and colour) and then a one-sentence action headline at `--text-xl`. A connector line (`p.story-link`, serif, `--text-lg`, ink-2) ends steps 1 to 6.
- **Rail.** The sticky "On this page" list is the rail. On the home page its links are the step titles. `app.js` appends `p.rail-pos` ("Step n of 7", label face, `--text-xs`, muted, `aria-live="polite"`), driven by the D56 scroll spy.
- **Figures in headings.** `h2 .num` and `.story-answer .num` inherit the weight of their text, so a figure in a head differs only by the dotted source cue (waiver 38iii in the stamp block).
- **Colours.** No new colour; the outcome marks and their colours are unchanged.
- **How to change a headline.** The sentences are built in `index_page` in `src/site_build.py` (`answer`, `head1` to `head7`), the connectors in `CONNECTORS` and the step titles in `STEP_TITLES`. The step titles are pinned by `tests/test_site.py`. The headline rules, and the rule that every block stays in its step, are in `tests/test_story.py`.
