# Design System

RestoreProof is a CLI. Its only visual surface is the self-contained offline HTML evidence report, styled by `src/restoreproof/reporting/report.css`. These are the values in use.

## 01 Brand Identity
Sober, evidential, readable, printable.

## 02 Colour Palette
| Name | Hex | Use for |
|---|---|---|
| Ink (`--ink`) | #172e42 | Text, brand mark |
| Paper (`--paper`) | #f3f7fa | Page background |
| Teal (`--teal`) | #087b6e | PASS / healthy |
| Amber (`--amber`) | #855600 | INCOMPLETE / warnings |
| Berry (`--berry`) | #9e3151 | FAIL / INVALID |
| Line (`--line`) | #d6e1e8 | Borders, dividers |
| Muted (`--muted`) | #51667a | Secondary text |
| Link / focus | #175786 | Links, 3px focus outline |

## 03 Typography
- **Font:** "Segoe UI", then system UI; monospace Consolas, "Liberation Mono"
- **Base:** 16px, line-height 1.55, paragraphs max 76ch
- **H1:** clamp(34px, 4.5vw, 54px), weight 650, letter-spacing −1.6px
- **H2:** 25px; **H3:** 16px; intro text 19px muted

## 04 Spacing
- Page max width 1180px, padding 32px (16px on small screens)
- Common steps: 9, 12, 16, 24, 32, 40px

## 05 Border Radius
- Brand mark 5px, small chips 4px, panels 12px

## 06 Components
- **Outcome badges:** colour by outcome (teal, amber, berry), always with the outcome word, never colour alone
- **Records:** collapsible `<details>` per run with latest attempt, last success, backup identity and checks
- **Focus:** visible 3px outline on links, summaries and focusable regions; skip link

## 07 Icons
None. Text labels only, so the report works offline and in print.

## 08 Breakpoints
- Desktop default; ≤720px single column
- `@media print`: flattened layout, records don't break across pages
- `prefers-reduced-motion`: no smooth scrolling

## Rules
- No external assets (fonts, scripts, images): the report must open offline
- Never use colours outside this palette
