# A shared vocabulary for the interface

[Home](Home.md) · [Frontend](frontend.md)

The design values live in `:root` in [styles.css](../frontend/src/styles.css). Version 2.2.0 consolidates the older surfaces as well as the reading cards: 258 distinct inline hex colors outside the root now use shared tokens or mixes of those tokens. Every CSS font size and border radius uses a named step. This keeps a local change from creating another almost-identical shade or size.

## Choose by purpose

| Purpose | Tokens |
|---|---|
| Page, panels, inputs and raised surfaces | `--bg`, `--panel`, `--surface-input`, `--surface-raised`, `--surface-rail` |
| Main text and decreasing emphasis | `--text`, `--text-secondary`, `--muted`, `--text-subtle`, `--text-faint` |
| Borders and quiet interaction fills | `--line-soft`, `--line`, `--line-strong`, `--fill-subtle`, `--fill-hover` |
| Measurement identity | `--metric-ph`, `--metric-turbidity`, `--metric-temperature`, `--metric-water_level` |
| Status and actions | `--mint`, `--lavender`, `--amber`, `--red`, plus their named softer variants |

Use the metric token when a color means a particular measurement. For example, a water-level line, selected control and legend all use `--metric-water_level`. A red warning expresses status instead. Do not infer status from a measurement's identity color.

Use `color-mix(in srgb,var(--mint) 12%,transparent)` when an accent needs a translucent fill. Reuse the named line and fill tokens for neutral treatments. Add a root token only when it represents a distinct reusable role; `--surface-calm`, for example, keeps the calm status gradient dark without borrowing a text color.

## Use the existing steps

Spacing uses `--sp-1` through `--sp-9`: 4, 8, 12, 16, 20, 24, 32, 40 and 48 px. Apply these to ordinary padding, margins and gaps. A panel can use `padding:var(--sp-6)` while a compact row uses `gap:var(--sp-2)`.

Type has thirteen steps: micro 9, label 10, small 11, caption 12, UI 13, body 14, subheading 16, heading 18, section 20, title 24, display 28, reading 32 and hero 48 px. Their names use the `--type-` prefix. The smallest steps serve compact labels and decorative details; body copy uses the body step.

Radii use `--radius-detail` (4 px), `--radius-small` (8 px), `--radius-control` (12 px), `--radius-panel` (16 px), `--radius-dialog` (20 px), `--radius-pill` (999 px) and `--radius-circle` (50%). Choose the role before choosing a size.

Not every number belongs on the spacing scale. Border widths, 1–3 px optical adjustments, icon geometry, responsive breakpoints, control dimensions and clearances for floating controls remain explicit. Check their layout purpose before replacing them.

## Keep charts and CSS in agreement

[Chart.tsx](../frontend/src/Chart.tsx) reads resolved custom properties with `getComputedStyle()`. Plotly receives concrete colors, the inherited font family and the caption size. Its grid and min–max shading derive alpha colors from the shared palette. The alpha conversion expects six-digit hex primitives after CSS aliases resolve; preserve that format for the metric and muted tokens, or update the conversion when changing their representation.

After changing a shared token, run both test suites and the frontend build, then inspect Overview, Setup, History, Settings and Rill in the isolated review app. Include a narrow phone layout and a desktop layout. Check text contrast, wrapped controls, overlays and chart colors; a successful build cannot establish that those still look right.

The 2.3.0 visual pass checks the 600/601 px breakpoint explicitly. Tablets keep Settings in the navigation rail, put chart controls on their own row and lay out status details below the main message. Reading-card help panels anchor to the card and raise the open card above its neighbors, so animation stacking contexts cannot cover the explanation. Settings headings align with their icons, and helper copy has a shared gap after actions.
