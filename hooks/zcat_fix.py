#!/usr/bin/env python3
"""Aggressive auto-fixer for zcat page files.

Every change it makes is appended to .zcat-state/autofix.log so the design
edits it performs can be reviewed and reverted. Fixes only things with one
correct answer; anything requiring judgement is left for the blocking report.
"""
import os
import re
import datetime

HOOKS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(HOOKS, "..", ".."))
STATE = os.path.join(PROJECT, ".zcat-state")
LOG = os.path.join(STATE, "autofix.log")

SPACE = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36,
         40, 44, 48, 50, 64, 80, 120]
RADIUS = [2, 4, 6, 10, 14, 18, 20]


def _tokens():
    """hex -> [(varname, group)] from the library's light theme block."""
    f = os.path.join(PROJECT, "zcat-ui", "src", "tokens", "colors.css")
    out = {}
    try:
        txt = open(f, encoding="utf-8").read()
    except OSError:
        return out
    dark = txt.find("prefers-color-scheme: dark")
    if dark > 0:
        txt = txt[:dark]
    for name, hexv in re.findall(r"(--zc-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", txt):
        out.setdefault(hexv.lower(), []).append(name)
    return out


TOKENS = _tokens()


def _nearest(v, scale):
    return min(scale, key=lambda s: (abs(s - v), s))


def _pick(hexv, prop):
    """Choose the token whose namespace matches the CSS property being set."""
    cands = TOKENS.get(hexv.lower())
    if not cands:
        return None
    p = prop.lower()
    if "border" in p or "outline" in p:
        want = "border"
    elif "background" in p:
        want = "bg"
    elif "color" in p or "fill" in p or "stroke" in p:
        want = "text"
    else:
        want = ""
    for c in cands:
        if want and want in c:
            return c
    return cands[0]


def autofix(path, text, is_css_file, allow_bump=True):
    """Return (new_text, [descriptions of what changed])."""
    changes = []
    lines = text.splitlines(keepends=True)

    # Which lines are CSS context (whole file, or <style> blocks / inline style=)
    css_ctx = [is_css_file] * len(lines)
    if not is_css_file:
        inside = False
        for i, ln in enumerate(lines):
            if re.search(r"<style\b", ln, re.I):
                inside = True
            css_ctx[i] = inside or ("style=" in ln)
            if re.search(r"</style>", ln, re.I):
                inside = False

    prop_re = (r"(?P<prop>color|background(?:-color)?|border(?:-[a-z]+)?-color|border|"
               r"fill|stroke|outline-color|caret-color)"
               r"(?P<mid>\s*:\s*[^;{}]*?)"
               r"(?P<hex>#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b)")

    for i, ln in enumerate(lines):
        orig = ln

        # 1. raw hex -> exact matching --zc-* token
        def sub_hex(m):
            tok = _pick(m.group("hex"), m.group("prop"))
            if not tok:
                return m.group(0)
            changes.append(f"line {i+1}: {m.group('hex')} -> var({tok})  [{m.group('prop')}]")
            return f"{m.group('prop')}{m.group('mid')}var({tok})"
        ln = re.sub(prop_re, sub_hex, ln, flags=re.I)

        if css_ctx[i]:
            # 2. spacing / radius off the scale -> nearest token value
            def sub_px(m):
                prop, val = m.group("p").lower(), int(m.group("v"))
                scale = RADIUS if "radius" in prop else SPACE
                near = _nearest(val, scale)
                if near == val:
                    return m.group(0)
                changes.append(f"line {i+1}: {prop} {val}px -> {near}px  [snapped to token scale]")
                return m.group(0).replace(f"{val}px", f"{near}px")
            ln = re.sub(
                r"(?P<p>gap|row-gap|column-gap|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|"
                r"border-radius|top|left|right|bottom)\s*:\s*[^;{}]*?(?P<v>\d+)px",
                sub_px, ln, flags=re.I)

            # 3. raw font rules -> removed (typography comes from .zc-* classes)
            if re.search(r"\bfont-(?:size|weight|family)\s*:", ln, re.I):
                stripped = re.sub(r"\s*font-(?:size|weight|family)\s*:[^;}]*;?", "", ln, flags=re.I)
                if stripped.strip() != ln.strip():
                    changes.append(f"line {i+1}: removed raw font rule "
                                   f"(use .zc-h*/.zc-subtitle-*/.zc-body-* classes)")
                    ln = stripped

        if ln != orig:
            lines[i] = ln

    text = "".join(lines)

    # 4. page must load the library
    if path.endswith(".html") and "zcat.css" not in text:
        rel = os.path.relpath(os.path.join(PROJECT, "zcat-ui"), os.path.dirname(path))
        tag = (f'  <link rel="stylesheet" href="{rel}/zcat.css?v=1">\n'
               f'  <script src="{rel}/zcat.js?v=1" defer></script>\n')
        if "</head>" in text:
            text = text.replace("</head>", tag + "</head>", 1)
            changes.append("inserted missing zcat.css + zcat.js includes")

    # 5. cache-bust the page's OWN glue css/js (the known stale-fix trap).
    #    Gated: only when the page's real content changed, so repeated hook runs
    #    on an unchanged file cannot inflate the version forever.
    def bump(m):
        n = int(m.group("n")) + 1
        return f'{m.group("pre")}?v={n}'
    # The page's OWN glue only — never the library's refs. zcat-ui carries its
    # own version ritual; bumping it here would desync pages from the library.
    new = re.sub(
        r'(?P<pre>(?:href|src)="(?!(?:[^"]*/)?zcat-ui/)\.[^"]*\.(?:css|js))\?v=(?P<n>\d+)',
        bump, text) if allow_bump else text
    if new != text:
        changes.append("bumped ?v= on the page's own css/js (cache-bust)")
        text = new

    return text, changes


def log(path, changes):
    if not changes:
        return
    os.makedirs(STATE, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[{stamp}] {os.path.relpath(path, PROJECT)}\n")
        for c in changes:
            f.write(f"  - {c}\n")
