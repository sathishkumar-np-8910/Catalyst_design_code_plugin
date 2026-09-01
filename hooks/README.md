# zcat enforcement — how a screen gets approved

Three layers. Each catches what the others cannot. A screen is approved only
when all three are silent.

| Layer | When | What it catches |
|---|---|---|
| **1. Static** `zcat-validate.py` | PostToolUse: Write, Edit, **Bash** | raw hex, off-scale px, restyled `zc-*`, raw font rules, emoji icons, popup width overrides, missing zcat.css, lorem ipsum |
| **2. Rendered** `zcat-render-audit.js` | Stop hook (and manually) | **the real geometry** — alignment, overflow, overlap, collapsed boxes, uneven rows, rhythm, contrast (light + dark), CTA count, tab state, placeholder text, tabs-in-container, hand-built controls, assembled-not-composed |
| **3. Design review** `zcat-review.py` | Stop hook | evidence that a human-grade critique happened |

## Why Bash is in the matcher

The old matcher was `Write|Edit`. Some Claude Code modes prefer `sed`/heredocs
over the Write/Edit tools — every one of those edits bypassed the hook silently.
Bash carries no `file_path`, so on a Bash call the hook scans page files touched
in the last 180s instead. The same hook also refuses Bash writes into
`AI Automation/`, which the `Write(...)`/`Edit(...)` deny rules cannot cover.

## Auto-fix

Layer 1 fixes anything with exactly one correct answer, in place:
raw hex → the matching `--zc-*` token (property-aware: text/bg/border),
off-scale spacing and radius → nearest token, raw font rules → removed,
missing library includes → inserted, page glue `?v=` → bumped.

Every change is appended to `.zcat-state/autofix.log`. **These are design
changes — read the log.** The version bump is fingerprint-gated (content with
`?v=` stripped), so re-running the hook on an unchanged file cannot inflate it,
and it never touches the library's own `zcat-ui/zcat.css?v=` refs.

Anything needing judgement is never rewritten — it blocks with the violation.

## The Stop gate

An agent cannot end its turn while a page it touched is unproven. For each
touched page (tracked in `.zcat-state/touched.json`) it requires:

1. a **passing** rendered audit, re-run automatically if the page changed since;
2. a **feature-coverage receipt** — proof the build contains what the
   requirement asked for;
3. a **design score of 75+ with no zero dimension** — proof the screen was
   composed rather than assembled;
4. a **design review recorded after the page's last edit**.

All four are blocking, and all four go stale the moment the page is edited
again. There is no flag to skip one.

## Feature coverage — `zcat-features.py`

The rendered audit has never seen the wireframe, so it cannot know a feature was
dropped. This closes that: the agent declares what the requirement contained and
every item is matched against the built page (visible text *and* attribute text,
because a Search field's placeholder is the feature).

```bash
python3 .claude/hooks/zcat-features.py pages/x/page.html --json '{
  "source":  "the wireframe / PRD the features came from",
  "tabs":    ["Overview", "Settings"],
  "columns": ["Name", "Status"],
  "actions": ["Create Database", "Refresh"],
  "fields":  ["Database name"],
  "other":   ["copy icon on host", "three-dot row menu"],
  "states":  ["populated", "empty", "create popup"],
  "dropped": [] }'
```

Rejects when: anything declared is absent from the page; `dropped` has an entry
that does not record the user's prior approval; `states` is empty (a wireframe
only ever draws the happy path).

## Design score — `zcat-design-score.py`

**What it is, honestly:** a script cannot judge beauty. It measures the signals
that separate a composed screen from a stack of components. A high score does
not certify taste; a low score is strong evidence the screen was assembled.

| Dimension | Max | What it measures |
|---|---|---|
| Composition | 30 | the widest side-by-side group; penalised for one long stacked run |
| Emphasis | 25 | distinct `.zc-h*` / `.zc-subtitle-*` levels actually used |
| Component use | 20 | distinct `zc-*` components on the page |
| CTA restraint | 15 | exactly one filled button |
| Card variety | 10 | cards differ in size by importance rather than all matching |

Pass is **75 AND no dimension may be 0** — a screen cannot be average-good while
one whole aspect of it is missing. Reads the metrics the rendered audit already
collected, so run the audit first.

Known result worth keeping: `template.html` and `databases.html` currently score
75 but FAIL on Emphasis 0/25 — they use no heading or subtitle classes at all.
That flatness is real, and now measurable.

## Recording a design review

```bash
python3 .claude/hooks/zcat-review.py pages/x/page.html --json '{
  "reference_screenshot": "<file from AI Automation/Screenshots referance/>",
  "three_differences":    ["...", "...", "..."],
  "wireframe_divergence": ["...", "..."],
  "top_issue":            "...",
  "fix_applied":          "..."
}'
```

It is rejected unless the reference screenshot really exists, the three
differences are specific (not "better spacing"), and the two divergences name a
**structural** change — merged, split, moved, re-ordered, re-columned. Restyling
is not divergence. If you cannot name two, you copied the wireframe.

## Running the audit by hand

```bash
node .claude/hooks/zcat-render-audit.js pages/x/page.html
```

Screenshots land in `.zcat-state/shots/` (light + dark), the verdict in
`.zcat-state/<slug>.json`. Exit 1 = failures.

## Calibration

Tuned against the real pages: `databases`, `database-detail`,
`databases-empty`, `template` all pass with zero failures. Two fixtures in
`fixtures/` (`broken.html`, `assembled.html`) carry known defects and must keep
failing — use them as the regression test after any change to the audit.

The library shell (rail, topbar, sidemenu) is out of scope: it is verified and
sacred. Only page-authored content is audited.

Contrast failures on library tokens (badges, chips, buttons) are **warnings**,
not failures — a page build cannot edit `zcat-ui/`. They are for the designer.
