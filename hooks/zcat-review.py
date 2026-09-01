#!/usr/bin/env python3
"""Record the senior-designer review for a page — with evidence, not a boolean.

  python3 .claude/hooks/zcat-review.py <page.html> --json '{...}'

Required JSON:
  reference_screenshot : filename from AI Automation/Screenshots referance/
                         (must actually exist — it is the quality bar you compared against)
  three_differences    : 3 SPECIFIC things the reference does that your screen does not
  wireframe_divergence : 2+ STRUCTURAL ways your layout differs from the wireframe
  top_issue            : the weakest thing on your screen, named honestly
  fix_applied          : what you changed as a result (or why nothing was needed)

The point is that writing these requires actually looking at both images.
A boolean does not.
"""
import json
import os
import re
import sys

HOOKS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(HOOKS, "..", ".."))
STATE = os.path.join(PROJECT, ".zcat-state")
# Reference screenshots live in two possible places. On the author's machine the
# AI Automation project is linked in and is the live original; in a CLONE that
# link does not exist, so the repo carries its own copy. Prefer the original
# when present so an update there is picked up without re-copying.
_REF_CANDIDATES = (
    os.path.join(PROJECT, "AI Automation", "Screenshots referance"),
    os.path.join(PROJECT, "reference-screenshots"),
)
SHOTS_REF = next((p for p in _REF_CANDIDATES if os.path.isdir(p)), _REF_CANDIDATES[-1])

GENERIC = re.compile(
    r"^(?:it |the )?(?:looks?|is|has|uses?|used)\b.*\b(better|good|nice|clean|polished|"
    r"improved|consistent)\b|^used zcat|^different colou?rs?$|^better spacing$|"
    r"^more polished$|^improved hierarchy$", re.I)
STRUCTURAL = re.compile(
    r"\b(merged?|moved?|split|promoted?|demoted?|reordered?|re-ordered?|combined?|"
    r"converted?|replaced?|grouped?|regrouped?|collapsed?|column|row|tab|card|"
    r"sidebar|header|section|popup|inline|stacked?|side-by-side)\b", re.I)


def die(msg):
    print("REVIEW REJECTED\n" + msg)
    sys.exit(1)


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--json":
        die(__doc__)
    page = sys.argv[1]
    abs_page = os.path.join(PROJECT, page) if not os.path.isabs(page) else page
    if not os.path.exists(abs_page):
        die(f"no such page: {page}")
    try:
        d = json.loads(sys.argv[3])
    except Exception as e:
        die(f"--json is not valid JSON: {e}")

    errs = []

    ref = (d.get("reference_screenshot") or "").strip()
    if not ref:
        errs.append("reference_screenshot is missing — name the production screenshot "
                    "you compared against.")
    elif os.path.isdir(SHOTS_REF) and not os.path.exists(os.path.join(SHOTS_REF, ref)):
        avail = sorted(os.listdir(SHOTS_REF))[:8]
        errs.append(f"reference_screenshot '{ref}' does not exist. Available e.g.: "
                    + ", ".join(avail))

    diffs = d.get("three_differences") or []
    if len(diffs) < 3:
        errs.append(f"three_differences needs 3 entries, got {len(diffs)}.")
    for i, t in enumerate(diffs[:3], 1):
        t = (t or "").strip()
        if len(t) < 40:
            errs.append(f"three_differences[{i}] is too short ({len(t)} chars) — "
                        f"be specific about what the reference does.")
        elif GENERIC.search(t):
            errs.append(f"three_differences[{i}] is generic (\"{t[:50]}…\"). "
                        f"Name the concrete thing, not a verdict.")

    div = d.get("wireframe_divergence") or []
    if len(div) < 2:
        errs.append(f"wireframe_divergence needs 2+ entries, got {len(div)}. If you "
                    f"cannot name two structural changes, you copied the wireframe.")
    for i, t in enumerate(div, 1):
        t = (t or "").strip()
        if len(t) < 40:
            errs.append(f"wireframe_divergence[{i}] is too short ({len(t)} chars).")
        elif not STRUCTURAL.search(t):
            errs.append(f"wireframe_divergence[{i}] describes no structural change "
                        f"(\"{t[:50]}…\"). Restyling is not divergence — merging, "
                        f"splitting, moving, re-ordering or re-columning is.")

    for k, n in (("top_issue", 30), ("fix_applied", 30)):
        t = (d.get(k) or "").strip()
        if len(t) < n:
            errs.append(f"{k} is too short ({len(t)} chars) — "
                        f"'everything passed' is not available here.")

    if errs:
        die("\n".join(f"  - {e}" for e in errs))

    os.makedirs(STATE, exist_ok=True)
    rel = os.path.relpath(abs_page, PROJECT)
    out = os.path.join(STATE, rel.replace("/", "__").replace("\\", "__")[:-5] + ".review.json")
    d["page"], d["recorded"] = rel, __import__("datetime").datetime.now().isoformat(timespec="seconds")
    json.dump(d, open(out, "w"), indent=2)
    print(f"REVIEW RECORDED for {rel}")


if __name__ == "__main__":
    main()
