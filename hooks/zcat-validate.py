#!/usr/bin/env python3
"""PostToolUse hook — zcat page validation with auto-fix.

Covers Write, Edit AND Bash. Bash is the important addition: some Claude Code
modes prefer sed/heredocs over Write/Edit, and the old matcher never saw those
edits, so the hook was silently bypassed.

Order of operations per page file:
  1. auto-fix everything with one correct answer (logged to .zcat-state/autofix.log)
  2. re-scan; block on whatever is left (those need judgement)

Also refuses Bash writes into AI Automation/, which the Write/Edit deny rules
in settings.json cannot cover.
"""
import json
import os
import re
import subprocess
import sys
import time
import hashlib

HOOKS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(HOOKS, "..", ".."))
# GUARD: this plugin is user-scope installable — never act outside a zcat
# workspace. A zcat workspace is identified by the library clone.
def _is_zcat_project(p):
    return (os.path.exists(os.path.join(p, "zcat-ui", "zcat-ui", "zcat.css"))
            or os.path.exists(os.path.join(p, "zcat-ui", "zcat.css")))

if not _is_zcat_project(PROJECT):
    sys.exit(0)

sys.path.insert(0, HOOKS)
from zcat_checks import static_issues          # noqa: E402
import zcat_fix                                 # noqa: E402

# "/.claude/hooks/" (not just .zcat-state) so the hook's OWN files are out of
# scope — fixtures/assembled.html and fixtures/broken.html are deliberate
# negative test cases that exist to make the audit fail. Before this, they were
# recorded in touched.json and the Stop gate demanded they be "fixed", which
# would have destroyed the tests.
# "/hooks/fixtures/" is name-agnostic on purpose: it was previously matched by
# literal plugin-folder names ("/zcat-plugin/"), which silently stopped
# excluding these fixtures the moment the plugin package was renamed/repackaged
# (e.g. into Catalyst_design_code_plugin/). Matching the fixtures directory
# itself survives any future rename.
SKIP = ("/zcat-ui/", "/ai automation/", "/.claude/hooks/", "/zcat-plugin/",
        "/hooks/fixtures/",
        "/node_modules/", "/scratchpad/", "/.git/",
        # generated deploy artefact — rebuilt by build-docs-site.sh from
        # zcat-ui/, so there is nothing here for a human to fix
        "/slate-docs/")
WRITE_CMD = re.compile(
    r"(>|>>|\bsed\b\s+-i|\btee\b|\bcp\b|\bmv\b|\brm\b|\btruncate\b|"
    r"\bdd\b|\bpython3?\b[^|]*\bopen\(|\bcat\b[^|]*>)", re.I)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def is_page(p):
    low = p.lower()
    if not (low.endswith(".html") or low.endswith(".css")):
        return False
    return not any(s in low for s in SKIP)


def recent_pages(seconds=180):
    """Page files touched recently — how we catch Bash edits, which carry no
    file_path in the hook payload."""
    out, cutoff = [], time.time() - seconds
    for root, dirs, files in os.walk(PROJECT):
        dirs[:] = [d for d in dirs if d not in
                   ("node_modules", ".git", "zcat-ui", "AI Automation", ".zcat-state", "zcat-plugin", "_archive")]
        for f in files:
            p = os.path.join(root, f)
            if is_page(p):
                try:
                    if os.path.getmtime(p) >= cutoff:
                        out.append(p)
                except OSError:
                    pass
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response") or {}

    # --- guard the read-only source of truth against Bash writes -----------
    if tool == "Bash":
        cmd = ti.get("command") or ""
        if re.search(r"AI[ _]Automation", cmd) and WRITE_CMD.search(cmd):
            block("BLOCKED: that Bash command writes into 'AI Automation/', which is "
                  "READ-ONLY (CLAUDE.md hard rule). The Write/Edit deny rules do not "
                  "cover Bash, so this hook enforces it. Put temporary files in the "
                  "scratchpad instead.")

    # --- collect target page files ----------------------------------------
    if tool in ("Write", "Edit", "MultiEdit"):
        fp = ti.get("file_path") or tr.get("filePath") or ""
        targets = [os.path.abspath(fp)] if fp and is_page(os.path.abspath(fp)) else []
    elif tool == "Bash":
        targets = recent_pages()
    else:
        return
    if not targets:
        return

    # Record what was touched so the Stop gate knows what to hold to account.
    try:
        os.makedirs(os.path.join(PROJECT, ".zcat-state"), exist_ok=True)
        tf = os.path.join(PROJECT, ".zcat-state", "touched.json")
        known = json.load(open(tf)) if os.path.exists(tf) else []
        for t in targets:
            r = os.path.relpath(t, PROJECT)
            if t.lower().endswith(".html") and r not in known:
                known.append(r)
        json.dump(known, open(tf, "w"), indent=1)
    except Exception:
        pass

    all_issues, fixed_any = [], []
    for p in targets:
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue

        # Content fingerprint with version numbers stripped: a bump is only
        # earned when the page itself changed, not when the hook re-ran.
        bare = re.sub(r"\?v=\d+", "?v=", text)
        h = hashlib.sha1(bare.encode("utf-8", "replace")).hexdigest()
        hf = os.path.join(PROJECT, ".zcat-state", "hashes.json")
        try:
            seen = json.load(open(hf)) if os.path.exists(hf) else {}
        except Exception:
            seen = {}
        rel_p = os.path.relpath(p, PROJECT)
        allow_bump = seen.get(rel_p) != h

        new, changes = zcat_fix.autofix(p, text, p.lower().endswith(".css"), allow_bump)
        if changes:
            try:
                open(p, "w", encoding="utf-8").write(new)
                zcat_fix.log(p, changes)
                fixed_any.append((p, changes))
                text = new
            except OSError:
                pass
        try:
            seen[rel_p] = hashlib.sha1(
                re.sub(r"\?v=\d+", "?v=", text).encode("utf-8", "replace")).hexdigest()
            os.makedirs(os.path.dirname(hf), exist_ok=True)
            json.dump(seen, open(hf, "w"), indent=1)
        except Exception:
            pass

        left = static_issues(p, text)
        if left:
            rel = os.path.relpath(p, PROJECT)
            all_issues.extend(f"{rel} :: {i}" for i in left)

    msg = []
    if fixed_any:
        msg.append("AUTO-FIXED (already applied to the file — review them, they are "
                   "design changes; full log: .zcat-state/autofix.log):")
        for p, ch in fixed_any:
            msg.append(f"  {os.path.relpath(p, PROJECT)}")
            for c in ch[:8]:
                msg.append(f"    - {c}")
            if len(ch) > 8:
                msg.append(f"    - (+{len(ch) - 8} more)")

    if all_issues:
        shown = all_issues[:20]
        more = f"\n(+{len(all_issues) - 20} more)" if len(all_issues) > 20 else ""
        msg.append("")
        msg.append(f"STILL BROKEN — {len(all_issues)} violation(s) that need your "
                   f"judgement (hard rules from zcat-ui/.claude/skills/zcat-code.md):")
        msg.extend(f"  - {i}" for i in shown)
        msg.append(more)
        msg.append("")
        msg.append("Fix these now. Do not continue to another file first.")
        block("\n".join(msg))

    if fixed_any:
        # Not a failure, but the model must see what was changed on its behalf.
        block("\n".join(msg) + "\n\nNothing else is broken. Verify these auto-fixes "
              "look right, then continue.")


if __name__ == "__main__":
    main()
