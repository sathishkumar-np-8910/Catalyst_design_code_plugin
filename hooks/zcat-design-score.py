#!/usr/bin/env python3
"""Design-quality score for a built page.

WHAT THIS IS, HONESTLY: a script cannot judge whether a screen is beautiful.
What it CAN measure are the signals that reliably separate a composed screen
from a stack of components — the "assembled, not designed" failure. That is
what is scored here. A high score does not certify good taste; a low score is
strong evidence the screen was assembled rather than designed.

Reads the metrics the rendered audit already collected, so run the audit first.

    node   .claude/hooks/zcat-render-audit.js <page.html>
    python3 .claude/hooks/zcat-design-score.py <page.html>

Scored out of 100; PASS_MARK must be met before the Stop gate will finish.
"""
import json
import os
import re
import sys

HOOKS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(HOOKS, "..", ".."))
STATE = os.path.join(PROJECT, ".zcat-state")
PASS_MARK = 75
# A zero in ANY dimension is an automatic fail whatever the total: a screen
# cannot be 'good enough on average' while one whole aspect of it is absent.
NO_ZEROES = True


def slug(rel):
    """Same slug the render audit and the gate use: path separators to __,
    .html dropped, everything else left alone."""
    return rel.replace("/", "__").replace("\\", "__")[:-5]


def score(st, authored_text):
    """Returns (total, [(dimension, got, max, note)])."""
    rows = []

    # ── Composition: does anything sit BESIDE anything? ──────────────────
    cols, run = st.get("gridCols", 1), st.get("stackRun", 0)
    if cols >= 3:
        c, note = 30, f"{cols} columns side by side"
    elif cols == 2:
        c, note = 22, "two columns — some relationship expressed"
    else:
        c, note = 0, ("everything is one column stacked down the page — this is the "
                      "wireframe shape, not a composition")
    if run >= 8 and c:
        c -= 8
        note += f"; but one run of {run} stacked siblings is doing too much"
    rows.append(("Composition", max(c, 0), 30, note))

    # ── Emphasis: is anything promoted above anything else? ──────────────
    lv = st.get("typeLevels", 0)
    if authored_text < 3:
        e, note = 20, "little authored text — emphasis not applicable, not penalised"
    elif lv >= 3:
        e, note = 25, f"{lv} emphasis levels in use"
    elif lv == 2:
        e, note = 18, "two emphasis levels"
    elif lv == 1:
        e, note = 8, "one emphasis level — almost everything reads at equal weight"
    else:
        e, note = 0, ("no .zc-h* or .zc-subtitle-* anywhere — every authored word is "
                      "the same weight, so nothing is important")
    rows.append(("Emphasis", e, 25, note))

    # ── Richness: is the library actually being used? ────────────────────
    # Empty states are DELIBERATELY minimal (.zc-empty: illustration + heading
    # + desc + actions) — the rendered audit already exempts them from the
    # 10-component check; the score mirrors that calibration here.
    n = st.get("components", 0)
    if st.get("isEmptyState"):
        r, rnote = 20, f"{n} components — empty state, deliberately minimal (.zc-empty anatomy)"
    else:
        r = 20 if n >= 12 else 15 if n >= 10 else 8 if n >= 6 else 0
        rnote = (f"{n} distinct components" +
                 ("" if n >= 10 else " — a real screen uses 10+; this looks hand-built"))
    rows.append(("Component use", r, 20, rnote))

    # ── Restraint: exactly one call to action ────────────────────────────
    f = st.get("fills", 0)
    rows.append(("CTA restraint", 15 if f == 1 else 0, 15,
                 "one primary button" if f == 1 else
                 ("no primary button — nothing is the page's main action" if f == 0
                  else f"{f} filled buttons compete to be the primary")))

    # ── Variety: do the cards earn their differences? ────────────────────
    cards = st.get("cards", 0)
    if cards <= 2:
        v, note = 10, "too few cards to judge uniformity"
    elif st.get("uniformCards"):
        v, note = 0, (f"all {cards} cards are identical in size — if everything has "
                      "equal weight, nothing is emphasised")
    else:
        v, note = 10, "card sizes vary with importance"
    rows.append(("Card variety", v, 10, note))

    return sum(x[1] for x in rows), rows


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rel = os.path.relpath(os.path.abspath(sys.argv[1]), PROJECT)
    abs_p = os.path.join(PROJECT, rel)
    audit_f = os.path.join(STATE, slug(rel) + ".json")
    if not os.path.exists(audit_f):
        print(f"ERROR: no audit for {rel} — run it first:\n"
              f"  node .claude/hooks/zcat-render-audit.js {rel}")
        sys.exit(1)
    a = json.load(open(audit_f))
    st = a.get("stats") or {}

    raw = open(abs_p, encoding="utf-8", errors="replace").read()
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    authored = len([t for t in re.findall(r">([^<>]{4,})<", body) if t.strip()])

    total, rows = score(st, authored)
    zeroed = [n for n, g, m, _ in rows if g == 0]
    ok = total >= PASS_MARK and not (NO_ZEROES and zeroed)

    print(f"DESIGN SCORE {total}/100 — {'PASS' if ok else 'FAIL'} "
          f"(pass mark {PASS_MARK}, no dimension may be 0)   {rel}")
    for name, got, mx, note in rows:
        flag = " " if got == mx else ("!" if got == 0 else "~")
        print(f"  {flag} {name:<15} {got:>3}/{mx:<3}  {note}")
    if zeroed:
        print(f"\n  AUTOMATIC FAIL — scored 0 on: {', '.join(zeroed)}. A whole aspect")
        print("  of the design is simply absent; the total does not excuse it.")
    if not ok:
        print("\n  This measures COMPOSITION, not taste: side-by-side relationships,")
        print("  varied emphasis, real component use, one CTA, cards that differ by")
        print("  importance. A fail means the screen was assembled. Redesign the")
        print("  layout — do not just add a heading class to game the number.")

    os.makedirs(STATE, exist_ok=True)
    json.dump({"page": rel, "score": total, "pass": ok,
               "rows": [{"dim": n, "got": g, "max": m, "note": t} for n, g, m, t in rows],
               "_page_mtime": os.path.getmtime(abs_p)},
              open(os.path.join(STATE, slug(rel) + ".score.json"), "w"), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
