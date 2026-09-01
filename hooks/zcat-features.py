#!/usr/bin/env python3
"""Wireframe → build feature-coverage receipt.

The rendered audit proves a page is CORRECT. It cannot prove the page contains
everything the requirement asked for, because it has never seen the wireframe.
This closes that hole: the agent declares what the requirement contained, and
this script checks each declared item actually appears in the built page.

    python3 .claude/hooks/zcat-features.py <page.html> --json '{
      "source":  "what the features were read from (wireframe file, PRD, …)",
      "tabs":    ["Overview", "Settings"],
      "columns": ["Name", "Status"],
      "actions": ["Create Database", "Refresh"],
      "fields":  ["Database name", "Region"],
      "other":   ["copy icon on host", "three-dot row menu"],
      "states":  ["populated", "empty", "create popup"],
      "dropped": []
    }'

Rules enforced here:
  * every declared tab / column / action / field must be findable in the page
  * "dropped" must be empty unless each entry records the user's approval
  * "states" must name what was built beyond the happy path

Written next to the page's audit as <slug>.features.json; the Stop gate refuses
to finish without a current one.
"""
import json
import os
import re
import sys

HOOKS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(HOOKS, "..", ".."))
STATE = os.path.join(PROJECT, ".zcat-state")

LISTS = ("tabs", "columns", "actions", "fields", "other")


def slug(rel):
    """Same slug the render audit and the gate use: path separators to __,
    .html dropped, everything else left alone."""
    return rel.replace("/", "__").replace("\\", "__")[:-5]


def norm(s):
    """Compare loosely: case, punctuation and whitespace should not matter."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def main():
    if len(sys.argv) < 4 or sys.argv[2] != "--json":
        print(__doc__)
        sys.exit(1)
    rel = os.path.relpath(os.path.abspath(sys.argv[1]), PROJECT)
    abs_p = os.path.join(PROJECT, rel)
    if not os.path.exists(abs_p):
        print(f"ERROR: no such page: {rel}")
        sys.exit(1)
    try:
        d = json.loads(sys.argv[3])
    except Exception as e:
        print(f"ERROR: --json is not valid JSON ({e})")
        sys.exit(1)

    errs = []
    if not (d.get("source") or "").strip():
        errs.append('"source" is missing — name what you read the features from '
                    '(the wireframe file, the PRD, my message)')

    declared = {k: [x for x in (d.get(k) or []) if str(x).strip()] for k in LISTS}
    total = sum(len(v) for v in declared.values())
    if total == 0:
        errs.append("no features declared — list the tabs, columns, actions and "
                    "fields you found in the requirement; a screen always has some")

    # Match on what a user can actually read. Tag stripping alone would lose
    # placeholder / aria-label / title / alt / value text, which is real visible
    # content — a Search field's placeholder IS the feature.
    raw = open(abs_p, encoding="utf-8", errors="replace").read()
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    attrs = " ".join(re.findall(
        r'(?:placeholder|aria-label|title|alt|value|data-tooltip)\s*=\s*"([^"]*)"',
        text, flags=re.I))
    hay = norm(re.sub(r"<[^>]+>", " ", text) + " " + attrs)

    missing = []
    for kind, items in declared.items():
        for it in items:
            n = norm(it)
            # short labels ("ID") would match anything; require 3+ chars
            if len(n) >= 3 and n not in hay:
                missing.append(f"{kind[:-1]}: {it}")

    if missing:
        errs.append("DECLARED BUT NOT FOUND IN THE PAGE — you dropped these, or "
                    "renamed them without saying so:\n      - " +
                    "\n      - ".join(missing[:15]) +
                    (f"\n      (+{len(missing) - 15} more)" if len(missing) > 15 else ""))

    dropped = d.get("dropped") or []
    if dropped:
        unapproved = [x for x in dropped if "approved" not in str(x).lower()]
        if unapproved:
            errs.append("features are listed as dropped without recorded approval: " +
                        "; ".join(str(x) for x in unapproved[:5]) +
                        ". Removing a required feature needs the user's YES first — "
                        "ask, then record it here as approved.")

    states = [s for s in (d.get("states") or []) if str(s).strip()]
    if not states:
        errs.append('"states" is empty — a wireframe shows one happy path. Name the '
                    'states you built (empty, loading, error, selection) or say '
                    'explicitly which do not apply and why')

    if errs:
        print(f"FEATURE COVERAGE REJECTED for {rel}:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)

    os.makedirs(STATE, exist_ok=True)
    out = os.path.join(STATE, slug(rel) + ".features.json")
    d["_checked"] = total
    d["_page_mtime"] = os.path.getmtime(abs_p)
    json.dump(d, open(out, "w"), indent=1)
    print(f"FEATURE COVERAGE RECORDED for {rel} — {total} feature(s) verified "
          f"present, {len(states)} state(s) built")


if __name__ == "__main__":
    main()
