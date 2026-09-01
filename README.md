# Catalyst_design_code_plugin

Build product screens (HTML/CSS/JS) from the **zcat UI** component library
(the Zoho Catalyst design system) with the full enforcement pipeline attached.

This is a standalone repackaging of the zcat-ui code-mode toolchain — the
build skill plus its 5-layer enforcement — installable under its own name,
independent of any other marketplace.

## What's inside

| Piece | What it does |
|---|---|
| `skills/zcat-code/` | The build skill — routes any "build a page with zcat" request through the full workflow (inventory → composition → component mapping → build → proofs) |
| `hooks/` | 5-layer enforcement: static validation with auto-fix (PostToolUse), rendered Chromium audit, feature-coverage receipts, design scoring, and a Stop gate that refuses to finish unproven pages |
| `.mcp.json` | The zcat rules MCP (`https://zcat.catalystappsail.in/mcp`) — live design rules, tokens, component search, sample data. Public, no key. |

## Install

```bash
claude plugin marketplace add /path/to/Catalyst_design_code_plugin
claude plugin install Catalyst_design_code_plugin@catalyst-design-code-marketplace
```

Then install the audit's browser runtime (one time, inside the installed
plugin's `hooks/` folder):

```bash
cd "$(claude plugin list --json | jq -r '.[] | select(.name=="Catalyst_design_code_plugin") | .path')/hooks" && npm install && npx playwright install chromium
```

## Project requirements

Each project using this plugin needs:

1. The component library clone at the project root:
   `git clone https://github.com/VengateshB12/zcat-ui.git`
2. Pages go in `pages/`, linking the library relatively:
   `<link rel="stylesheet" href="../zcat-ui/zcat-ui/zcat.css">`
   `<script src="../zcat-ui/zcat-ui/zcat.js" defer></script>`
3. Serve over HTTP to view (relative links break on `file://`), e.g.
   `python3 -m http.server 4581` from the project root.
4. (Recommended) `reference-screenshots` symlink at the project root pointing
   to `zcat-ui/reference-screenshots` so design reviews can name a reference.

Enforcement state is written to `.zcat-state/` at the project root.

## The 5 enforcement layers (`hooks/`)

1. **Static validation with auto-fix** (`zcat-validate.py`, PostToolUse on
   every Write/Edit/Bash file change) — blocks on hard-rule violations
   (raw hex, off-scale spacing, restyled `zc-*` classes, missing includes)
   and auto-fixes the mechanical ones.
2. **Rendered audit** (`zcat-render-audit.js`) — renders the page in headless
   Chromium and checks real geometry: alignment, overflow, overlap, collapsed
   boxes, contrast (light + dark), CTA count, tab state, hand-built controls.
3. **Feature coverage** (`zcat-features.py`) — every tab/column/action/field
   the requirement named is declared and matched against the built page, so
   nothing is dropped silently.
4. **Design score** (`zcat-design-score.py`) — scores composition, emphasis,
   component use, CTA restraint and card variety; pass is 75+ with no
   dimension at 0.
5. **Stop gate** (`zcat-gate.py`) — a page cannot be called done without a
   passing rendered audit, a feature-coverage receipt, a passing design
   score, and a design review with real evidence (reference screenshot, 3
   named differences from it, 2 structural ways the layout diverges from the
   wireframe).

## Path resolution

Hook scripts resolve the project from `$CLAUDE_PROJECT_DIR` (set by Claude
Code when invoking hooks). Outside a hook context, pass it explicitly:

```bash
CLAUDE_PROJECT_DIR=/path/to/project node hooks/zcat-render-audit.js pages/x.html
```
