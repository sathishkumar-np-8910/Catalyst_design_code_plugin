---
name: zcat-code
description: Build HTML/CSS/JS product screens from the zcat UI component library (zc-* classes). Use whenever the user asks to build, develop, code, or generate a page, screen, dashboard, or UI as HTML using zcat / zcat-ui / the Catalyst design system — from a wireframe, screenshot, PRD, or text description.
license: Internal — follows the zcat-ui repository's terms
compatibility: Requires the zcat-ui clone at ./zcat-ui in the project (github.com/VengateshB12/zcat-ui), python3, and node with Playwright + Chromium installed in the plugin's hooks/ folder (npm install && npx playwright install chromium). The zcat MCP ships with this plugin.
metadata:
  author: srinath.p@zohocorp.com
  version: "1.0"
allowed-tools: Read Grep Glob Bash(python3:*) Bash(node:*)
---

# zcat-code — build pages from the zcat UI library

This skill is a thin router. The full workflow lives in the cloned library and
MUST be read and followed step by step — do not build from memory of it.

## STEP 0 — SETUP GATE (do this before anything else)

The library clone is the source of the workflow, the API contract, the CSS/JS
and the icons. Without it every reference below dangles and builds come out
broken. Check for `zcat-ui/zcat-ui/zcat.css` (or `zcat-ui/zcat.css`) in the
project root:

- Missing → clone it first: `git clone https://github.com/VengateshB12/zcat-ui.git`
  (then the library folder is `zcat-ui/zcat-ui/`). If the clone fails, STOP and
  tell the user — NEVER build pages without the library present.
- Present → carry on.

Also remind the user that pages must be viewed over HTTP (e.g.
`python3 -m http.server 4581` from the project root) — file:// breaks all
relative links.

## Read in this order, every build

1. `zcat-ui/zcat-ui/.claude/skills/zcat-code.md` — THE WORKFLOW (steps 0–8:
   contract → inventory → composition → mapping → build → validation → senior
   designer review → show). Follow every step; the screen inventory (step 2)
   requires user confirmation before building.
2. `zcat-ui/zcat-ui/ONBOARDING.md` — the component API contract. Authoritative.
3. Usage comments atop the owning `zcat-ui/zcat-ui/src/components/*.css` files
   for every component you will use.
4. `zcat-ui/zcat-ui/docs/template.html` — the Catalyst shell to copy verbatim.

## Live rules — zcat MCP (preferred over any file on disk)

Use `zcat_get_hard_rules`, `zcat_get_decision_rules` (only the topic needed),
`zcat_get_sample_data`, `zcat_search_components`, `zcat_search_icons`,
`zcat_get_screenshot_patterns`. NOTE: the `AI Automation/` folder referenced in
the repo docs is NOT in this clone (it is the author's private repo) — the zcat
MCP and `reference-screenshots/` (symlinked at project root) replace it.

## Project layout (this workspace)

- Built pages go in `pages/` at the project root — NEVER inside `zcat-ui/`.
- Library include paths from `pages/`:
  `<link rel="stylesheet" href="../zcat-ui/zcat-ui/zcat.css">`
  `<script src="../zcat-ui/zcat-ui/zcat.js" defer></script>`
  (The doubled folder is real: repo root `zcat-ui/` contains the library folder
  `zcat-ui/`. Existing pages already use this path — keep it.)
- Icons only from `zcat-ui/zcat-ui/docs/icons/`.
- `zcat-ui/**` is deny-listed for Write/Edit — the library is read-only here.
- Enforcement hooks ship with this plugin and fire automatically; manual
  runs (the plugin root is shown by the hook messages; state is written to
  `.zcat-state/` at the project root):
  `node "$PLUGIN/hooks/zcat-render-audit.js" pages/<page>.html`
  `python3 "$PLUGIN/hooks/zcat-features.py" pages/<page>.html --json '{...}'`
  `python3 "$PLUGIN/hooks/zcat-design-score.py" pages/<page>.html`
  `python3 "$PLUGIN/hooks/zcat-review.py" pages/<page>.html --json '{...}'`

## Examples

**"Build a databases list page"** → Read the workflow + contract, then STOP and
confirm the screen inventory first: populated list, empty state, create popup,
detail page, edit popup, delete confirmation. Only build after the user
confirms. Each state = its own file in `pages/` (e.g. `databases.html`,
`databases-empty.html`).

**User sends a wireframe image** → The wireframe is a FEATURE LIST, not the
design. Count every tab/column/button/field, list them back, then compose a
different, better layout from zc-* components. If the built page and the
wireframe look identical side by side, the build failed.

**"Add a chart card to the overview"** → Targeted edit to the existing page,
never a rebuild. After the edit, the hooks demand fresh proofs (rendered
audit, feature receipt, design score, design review) — run all four before
declaring done.

**A needed component seems missing** → Never hand-build a lookalike. Check
ONBOARDING.md's API tables and `grep src/components/` first; if it truly has
no class, tell the user and ask.

**Edge cases:** pages viewed via file:// lose all styling — always serve via
the launch.json dev server (http://localhost:4581/pages/...). JS-rendered
content (e.g. three-dot row menus) can't be matched by the static feature
checker — note it in the receipt's `source` field. Library-token contrast
warnings from the audit are designer-side; never "fix" them in the page.

## Non-negotiables (summary — the workflow file has the full list)

- Wireframe = feature list, never the design. 100% feature coverage; recompose
  the layout.
- Every product screen starts from the `.zc-layout` shell copied from
  template.html; shell is sacred.
- Never restyle a `zc-*` class; glue CSS is page-scoped selectors only.
- Zero raw hex — every color is `var(--zc-*)`. No odd-number spacing/radius.
- Typography via `.zc-h*` / `.zc-subtitle-*` / `.zc-body-*` classes only.
- At most ONE fill button per visible screen. Create/Edit = `.zc-popup`.
- Realistic sample data, never lorem ipsum. Icons never emoji/unicode.
