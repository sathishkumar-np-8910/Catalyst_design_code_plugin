#!/usr/bin/env python3
"""Static (text) checks for zcat page files. Extracted so both the PostToolUse
hook and the Stop gate run exactly the same rules."""
import re

RE_RAWCOLOR = re.compile(
    r'(?:color|background(?:-color)?|border(?:-[a-z]+)?-?color|border|fill|'
    r'stroke|box-shadow|outline|caret-color|text-decoration-color)'
    r'\s*[:=]\s*["\']?[^;"\'{}<>]*'
    r'(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()', re.I)
RE_SVGCOLOR = re.compile(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"')
RE_ODDPX = re.compile(r'(?<![0-9.])(3|5|7|9|1[13579]|2[13579]|3[13579])px\b')
RE_ZC_RESTYLE = re.compile(r'^\s*\.zc-[A-Za-z0-9_-]+[^{}]*\{')
RE_FONT = re.compile(r'\bfont-(?:size|weight|family)\s*:', re.I)
RE_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿←-⇿■-◿⬀-⯿]')
RE_SIDEMENU_STROKE = re.compile(
    r'zc-sidemenu__item(?:(?!zc-icon-stroke).)*?(fill="none"|stroke-width)')
RE_POPUP_W_CSS = re.compile(r'\.zc-popup[^{}]*\{[^}]*\bwidth\s*:')
RE_POPUP_W_INLINE = re.compile(r'class="[^"]*zc-popup[^"]*"[^>]*style="[^"]*width\s*:')
RE_GROUP_MAXW = re.compile(r'class="[^"]*zc-input-group[^"]*"[^>]*style="[^"]*max-width')


def static_issues(path, text):
    """Return a list of 'line N: RULE -> snippet' strings."""
    lines = text.splitlines()
    is_css = path.lower().endswith(".css")
    issues = []

    def add(n, rule, snip):
        snip = snip.strip()
        if len(snip) > 90:
            snip = snip[:90] + "…"
        issues.append(f"line {n}: {rule} -> {snip}")

    css_line = [is_css] * len(lines)
    if not is_css:
        inside = False
        for i, ln in enumerate(lines):
            if re.search(r"<style\b", ln, re.I):
                inside = True
            css_line[i] = inside or ("style=" in ln)
            if re.search(r"</style>", ln, re.I):
                inside = False

    for i, ln in enumerate(lines, 1):
        idx = i - 1
        if RE_SIDEMENU_STROKE.search(ln):
            add(i, "SIDEMENU STROKE ICON — use class=\"zc-icon-stroke\" (shell.css) or the fill-based glyph", ln)
        if css_line[idx] and RE_POPUP_W_CSS.search(ln):
            add(i, "POPUP WIDTH OVERRIDE — Popup is 550px / 414px (data-size=\"small\"); never widen it", ln)
        if RE_POPUP_W_INLINE.search(ln):
            add(i, "POPUP WIDTH OVERRIDE — Popup is 550px / 414px (data-size=\"small\"); never widen it", ln)
        if RE_GROUP_MAXW.search(ln):
            add(i, "CONSTRAINED FORM FIELD — input groups inside popups stretch full width; drop the max-width", ln)
        m = RE_RAWCOLOR.search(ln)
        if m and "var(--zc-" not in ln[max(0, m.start() - 5):m.end() + 40]:
            add(i, "RAW COLOR — every color must be var(--zc-*)", ln)
        if RE_SVGCOLOR.search(ln) and "currentColor" not in ln:
            add(i, "SVG hex fill/stroke — icons bind to currentColor / var(--zc-*)", ln)
        if css_line[idx]:
            m = RE_ODDPX.search(ln)
            if m:
                add(i, f"ODD PIXEL VALUE {m.group(0)} — use even --zc-space-* tokens", ln)
            if RE_FONT.search(ln):
                add(i, "RAW FONT RULE — use .zc-h*/.zc-subtitle-*/.zc-body-* classes", ln)
        if RE_ZC_RESTYLE.match(ln):
            add(i, "RESTYLED zc-* CLASS — never redefine library classes; use page-scoped glue classes", ln)
        m = RE_EMOJI.search(ln)
        if m:
            add(i, f"EMOJI/UNICODE GLYPH '{m.group(0)}' used as icon — use zcat-ui/docs/icons/ stroke icons", ln)

    if re.search(r"lorem\s+ipsum", text, re.I):
        issues.append("LOREM IPSUM found — use realistic sample data "
                      "(AI Automation/references/sample-data.md)")
    if path.lower().endswith(".html") and "zcat.css" not in text:
        issues.append("PAGE DOES NOT INCLUDE zcat.css — pages must load the library as-is")
    return issues
