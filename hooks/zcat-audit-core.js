/* zcat rendered-page audit — runs INSIDE the page.
 * Measures real geometry. Catches what a text hook cannot: alignment,
 * overflow, collapsed boxes, uneven rows, broken rhythm, contrast.
 *
 * Usage (Playwright):  page.evaluate(auditSource + "; __zcatAudit()")
 * Usage (Browser MCP): paste this file, then call __zcatAudit()
 * Returns: { fails: [...], warns: [...], stats: {...} }
 */
function __zcatAudit() {
  const F = [], W = [];
  const SCALE = [0,1,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,36,40,44,48,50,64,80,120];
  const TOL = 1.5;                       // sub-pixel tolerance for alignment
  const fail = (rule, msg, el) => F.push({ rule, msg, sel: path(el) });
  const warn = (rule, msg, el) => W.push({ rule, msg, sel: path(el) });

  function path(el) {
    if (!el || !el.tagName) return "(page)";
    const bits = [];
    for (let n = el, d = 0; n && n.tagName && d < 4; n = n.parentElement, d++) {
      let s = n.tagName.toLowerCase();
      const zc = [...n.classList].filter(c => c.startsWith("zc-"))[0];
      if (zc) s += "." + zc;
      else if (n.id) s += "#" + n.id;
      else if (n.classList[0]) s += "." + n.classList[0];
      bits.unshift(s);
    }
    return bits.join(" > ");
  }
  const vis = el => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" &&
           cs.display !== "none" && cs.opacity !== "0";
  };
  const px = v => parseFloat(v) || 0;
  const onScale = v => SCALE.some(s => Math.abs(s - v) < 0.6);

  // SCOPE — the library shell (rail/topbar/sidemenu) is verified and sacred.
  // Audit only what the page author actually built.
  const SHELL = ".zc-layout__rail, .zc-layout__topbar, .zc-sidemenu";
  const OWN = [...document.querySelectorAll(
    ".zc-layout__container, .zc-layout__subheader, .zc-popup, .zc-fullpopup, .zc-empty")];
  const scopes = OWN.length ? OWN : [document.body];
  const inScope = el =>
    scopes.some(s => s !== el && s.contains(el)) &&   // audit contents, not the library container itself
    !el.closest(SHELL) &&
    !(el.ownerSVGElement || el.tagName === "svg" && false) &&
    !el.closest("svg") &&
    !el.closest("script,style,head");
  const all = [...document.body.querySelectorAll("*")].filter(el => inScope(el) && vis(el));
  const isDivider = el =>
    !el.children.length && !(el.textContent || "").trim() &&
    (el.getBoundingClientRect().height <= 2 || el.getBoundingClientRect().width <= 2);
  const clips = el => {
    const cs = getComputedStyle(el);
    return cs.textOverflow === "ellipsis" || cs.whiteSpace === "nowrap" ||
           cs.overflow === "hidden" || cs.overflowX === "hidden";
  };

  /* ── 1. Page must not scroll sideways ─────────────────────────────── */
  const de = document.documentElement;
  if (de.scrollWidth > window.innerWidth + 2)
    F.push({ rule: "PAGE H-SCROLL",
      msg: `page scrolls horizontally (${de.scrollWidth}px content in ${window.innerWidth}px viewport) — something overflows`,
      sel: "(document)" });

  /* ── 2. Content overflowing its own box ───────────────────────────── */
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.overflowX === "auto" || cs.overflowX === "scroll") continue;
    if (clips(el)) continue;                      // ellipsis / nowrap is intentional
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0)
      fail("OVERFLOW", `content is ${el.scrollWidth - el.clientWidth}px wider than its box`, el);
  }

  /* ── 3. Collapsed boxes (the 40x40 icon that became 40x18) ────────── */
  for (const el of all) {
    if (isDivider(el)) continue;                  // 1px rules are deliberate
    const hasContent = el.children.length || (el.textContent || "").trim();
    if (!hasContent) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 6 && r.height < 4) fail("COLLAPSED", `box has content but height collapsed to ${r.height.toFixed(1)}px`, el);
    if (r.height > 6 && r.width < 4) fail("COLLAPSED", `box has content but width collapsed to ${r.width.toFixed(1)}px`, el);
  }

  /* ── 4. Clipped text ──────────────────────────────────────────────── */
  for (const el of all) {
    if (!el.children.length && el.textContent.trim()) {
      const cs = getComputedStyle(el);
      if (cs.overflow === "hidden" && cs.textOverflow !== "ellipsis" &&
          el.scrollHeight > el.clientHeight + 2)
        fail("TEXT CLIPPED", `text is cut off (${el.scrollHeight}px of text in ${el.clientHeight}px box)`, el);
    }
  }

  /* ── 5. Row children must align and match height ──────────────────── */
  for (const el of all) {
    const cs = getComputedStyle(el);
    const isRow = (cs.display.includes("flex") && cs.flexDirection.startsWith("row")) ||
                  cs.display.includes("grid");
    if (!isRow) continue;
    const kids = [...el.children].filter(vis);
    if (kids.length < 2) continue;
    const rects = kids.map(k => k.getBoundingClientRect());
    const sameLine = rects.every(r => Math.abs(r.top - rects[0].top) < TOL);

    const cardLike = rects.every(r => r.width >= 100);
    if (cardLike && sameLine && (cs.alignItems === "stretch" || cs.alignItems === "normal")) {
      const hs = rects.map(r => r.height);
      const spread = Math.max(...hs) - Math.min(...hs);
      if (spread > 2)
        fail("UNEVEN ROW", `items in this row differ in height by ${spread.toFixed(0)}px — they should stretch equal`, el);
    }
    // Centred / baseline rows legitimately have different tops — compare the
    // axis the row actually aligns on, not the top edge.
    const ai = cs.alignItems;
    if (ai === "center") {
      const mids = rects.map(r => r.top + r.height / 2);
      const spread = Math.max(...mids) - Math.min(...mids);
      if (spread > TOL)
        fail("MISALIGNED ROW", `items in a centred row are ${spread.toFixed(1)}px off centre`, el);
    } else if (ai === "flex-start" || ai === "start") {
      const tops = rects.map(r => r.top);
      const spread = Math.max(...tops) - Math.min(...tops);
      if (spread > TOL && spread < 24)
        fail("MISALIGNED ROW", `top-aligned items are ${spread.toFixed(1)}px out of alignment`, el);
    }
  }

  /* ── 6. Left edges of stacked sections must line up ───────────────── */
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (!(cs.display.includes("flex") && cs.flexDirection.startsWith("column"))) continue;
    if (cs.alignItems === "center" || cs.alignItems === "flex-end") continue;  // centred by design
    const kids = [...el.children].filter(vis).filter(k => k.getBoundingClientRect().width > 40);
    if (kids.length < 2) continue;
    const ls = kids.map(k => k.getBoundingClientRect().left);
    const spread = Math.max(...ls) - Math.min(...ls);
    if (spread > TOL)
      fail("EDGE MISALIGN", `stacked sections start at different left edges (${spread.toFixed(1)}px apart)`, el);
  }

  /* ── 7. Consistent vertical rhythm between siblings ───────────────── */
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (!(cs.display.includes("flex") && cs.flexDirection.startsWith("column"))) continue;
    const kids = [...el.children].filter(vis);
    if (kids.length < 3) continue;
    const gaps = [];
    for (let i = 1; i < kids.length; i++) {
      const a = kids[i - 1].getBoundingClientRect(), b = kids[i].getBoundingClientRect();
      gaps.push(b.top - a.bottom);
    }
    const spread = Math.max(...gaps) - Math.min(...gaps);
    if (spread > 4)
      warn("RHYTHM", `uneven vertical gaps between sections (${gaps.map(g => g.toFixed(0)).join(", ")}px)`, el);
  }

  /* ── 8. Spacing must sit on the token scale ───────────────────────── */
  for (const el of all) {
    if (el.closest(".zc-layout__topbar, .zc-layout__rail, .zc-sidemenu")) continue;
    const cs = getComputedStyle(el);
    for (const prop of ["gap", "rowGap", "columnGap", "paddingTop", "paddingRight",
                        "paddingBottom", "paddingLeft"]) {
      const v = px(cs[prop]);
      if (v > 0 && !onScale(v))
        warn("OFF-SCALE", `${prop} is ${v}px — not on the --zc-space-* scale`, el);
    }
  }

  /* ── 9. Siblings must not overlap ─────────────────────────────────── */
  for (const el of all) {
    const kids = [...el.children].filter(vis).filter(k => {
      const p = getComputedStyle(k).position;
      return p === "static" || p === "relative";
    });
    for (let i = 0; i < kids.length; i++)
      for (let j = i + 1; j < kids.length; j++) {
        const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
        const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (ox > 2 && oy > 2)
          fail("OVERLAP", `two siblings overlap by ${ox.toFixed(0)}x${oy.toFixed(0)}px`, kids[i]);
      }
  }

  /* ── 10. Exactly one primary CTA on the page ──────────────────────── */
  const fills = [...document.querySelectorAll('.zc-btn[data-variant="fill"]')]
    .filter(vis).filter(b => !b.closest(".zc-popup"));
  if (fills.length > 1)
    F.push({ rule: "CTA HIERARCHY",
      msg: `${fills.length} primary (fill) buttons visible: ${fills.map(b => `"${b.textContent.trim().slice(0,24)}"`).join(", ")} — only ONE per page`,
      sel: path(fills[1]) });

  /* ── 11. Exactly one active tab per tab group ─────────────────────── */
  for (const tabs of document.querySelectorAll(".zc-tabs")) {
    if (!vis(tabs)) continue;
    const act = tabs.querySelectorAll('[data-state="active"]').length;
    if (act !== 1) fail("TAB STATE", `tab group has ${act} active tabs — must be exactly 1`, tabs);
  }

  /* ── 12. No placeholder content ───────────────────────────────────── */
  const PLACEHOLDER = /\b(Select List|Enter Label Text|Button Text|Lorem ipsum|Placeholder|Text Field|Sample Text|TODO)\b/i;
  for (const el of all) {
    if (el.children.length) continue;
    const t = (el.textContent || "").trim();
    if (t && PLACEHOLDER.test(t)) fail("PLACEHOLDER", `placeholder text "${t.slice(0,40)}" left in the page`, el);
  }
  for (const el of document.querySelectorAll("input[placeholder]")) {
    const v = el.value, ph = el.getAttribute("placeholder");
    if (!v && PLACEHOLDER.test(ph)) warn("PLACEHOLDER", `input still shows demo placeholder "${ph}"`, el);
  }

  const isEmptyState = !![...document.querySelectorAll(".zc-empty")].filter(vis).length;

  /* ── 13. Built from components, not divs ──────────────────────────── */
  const zcSet = new Set();
  for (const el of all) for (const c of el.classList) if (c.startsWith("zc-")) zcSet.add(c.split("__")[0]);
  if (zcSet.size < 10 && !isEmptyState)
    F.push({ rule: "TOO FEW COMPONENTS",
      msg: `only ${zcSet.size} distinct zc-* components used — a real screen uses 10+; this looks hand-built`,
      sel: "(page)" });

  /* ── 14. Typography hierarchy must exist ──────────────────────────── */
  const heads = [...document.querySelectorAll(
    '[class^="zc-h"],[class*=" zc-h"],[class*="zc-subtitle-"]')]
    .filter(el => /\bzc-(h[1-6]|subtitle-[123])\b/.test(el.className)).filter(vis);
  const cards = [...document.querySelectorAll(".zc-card")].filter(vis);
  const tableDriven = [...document.querySelectorAll(".zc-table")].filter(vis).length > 0 &&
                      cards.length < 2;
  if (!heads.length && !tableDriven && !isEmptyState)
    F.push({ rule: "NO HIERARCHY",
      msg: `page authored ${cards.length} card(s) but uses no .zc-h* / .zc-subtitle-* anywhere — all text is Regular weight, so it has no hierarchy`,
      sel: "(page)" });

  /* ── 15. Text contrast (WCAG AA) ──────────────────────────────────── */
  const lum = c => {
    const s = c.map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); });
    return .2126 * s[0] + .7152 * s[1] + .0722 * s[2];
  };
  const rgb = str => (str.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  function bgOf(el) {
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const c = getComputedStyle(n).backgroundColor;
      const a = (c.match(/[\d.]+/g) || [])[3];
      if (c && c !== "transparent" && a !== "0") return rgb(c);
    }
    return [255, 255, 255];
  }
  const seen = new Set();
  for (const el of all) {
    if (el.children.length || !el.textContent.trim()) continue;
    const cs = getComputedStyle(el);
    const fg = rgb(cs.color), bg = bgOf(el);
    if (fg.length < 3) continue;
    const key = fg.join() + "|" + bg.join();
    if (seen.has(key)) continue;
    seen.add(key);
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
    const size = px(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 600;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) {
      const libOwned = [...el.classList].some(c => c.startsWith("zc-")) ||
                       !!el.closest('[class*="zc-badge"],[class*="zc-chip"],[class*="zc-btn"]');
      const m = `text contrast ${ratio.toFixed(2)}:1 (needs ${need}:1) — rgb(${fg}) on rgb(${bg})`;
      if (libOwned) warn("CONTRAST (LIBRARY)", m + " — library token, cannot be fixed in the page; raise with the designer", el);
      else fail("CONTRAST", m, el);
    }
  }

  /* ── 16. Cards in a row must share padding ────────────────────────── */
  const cardRows = new Map();
  for (const c of document.querySelectorAll(".zc-card")) {
    if (!vis(c) || !c.parentElement) continue;
    if (!cardRows.has(c.parentElement)) cardRows.set(c.parentElement, []);
    cardRows.get(c.parentElement).push(c);
  }
  for (const [parent, cards] of cardRows) {
    if (cards.length < 2) continue;
    const pads = cards.map(c => {
      const s = getComputedStyle(c);
      return [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].join("/");
    });
    if (new Set(pads).size > 1)
      fail("CARD PADDING", `sibling cards have different padding (${[...new Set(pads)].join("  vs  ")})`, parent);
  }

  /* ── 17. Fixed heights on cards/containers ────────────────────────── */
  for (const el of document.querySelectorAll(".zc-card, .zc-container, .zc-layout__container")) {
    if (!vis(el)) continue;
    const h = el.style.height || "";
    if (h && !h.includes("%") && !h.includes("auto"))
      fail("FIXED HEIGHT", `inline fixed height "${h}" — cards and containers must hug their content`, el);
  }

  /* ── 18. The Catalyst layout shell is mandatory ───────────────────── */
  const layout = document.querySelector(".zc-layout");
  const container = document.querySelector(".zc-layout__container");
  const subheader = document.querySelector(".zc-layout__subheader");
  // A full-page popup covers the viewport and legitimately has no shell.
  // A deliberately shell-less screen (landing page) must say so explicitly:
  //   <body data-zcat-no-shell="landing page — approved by user">
  const popupOnly = !!document.querySelector(".zc-fullpopup") ||
    (!!document.querySelector(".zc-popup") && !document.querySelector(".zc-layout__container"));
  const optedOut = document.body.hasAttribute("data-zcat-no-shell");
  if (!layout && !popupOnly && !optedOut)
    F.push({ rule: "NO LAYOUT SHELL",
      msg: "page does not start from .zc-layout — every product screen is built inside the Catalyst shell (rail, topbar, sidemenu, subheader, container), never as a floating card",
      sel: "(page)" });

  /* ── 19. Primary tabs belong in the Sub Header, never the container ─
     Deliberately NOT gated on a sub header existing: a page that omits the sub
     header and drops its primary tabs into the container is the very case this
     rule exists to catch, and the old `if (subheader)` guard let it through. */
  {
    const containerTabs = [...document.querySelectorAll(".zc-layout__container .zc-tabs")]
      .filter(vis).filter(t => t.getAttribute("data-type") !== "secondary" &&
                               !t.closest(".zc-popup, .zc-fullpopup, .zc-cheader"));
    for (const t of containerTabs)
      fail("TABS IN CONTAINER",
        "page-level tabs are sitting in the container — primary tabs MUST live in the Sub Header (.zc-layout__subheader-tabs); only section-scoped tabs may sit inside the container, as data-type=\"secondary\" in the Container Header. A wireframe drawing them in the container is low fidelity, not an instruction", t);
    const shTabs = [...document.querySelectorAll(".zc-layout__subheader .zc-tabs")].filter(vis);
    if (!shTabs.length && containerTabs.length)
      F.push({ rule: subheader ? "SUB HEADER HAS NO TABS" : "NO SUB HEADER FOR PAGE TABS",
        msg: subheader
          ? "this page has tabs but the Sub Header has none — the Sub Header is where the page's primary tab level lives"
          : "this page has page-level tabs but no Sub Header at all — add the Sub Header and put the primary tabs in its tabs row",
        sel: "(subheader)" });
  }

  /* ── 19b. An action bar must not be one lonely button ───────────────
     A primary action floating on the right with an empty left half is the
     "assembled, not designed" tell. The Container Header has two sides on
     purpose: actions right, and a heading / Search / filters left. */
  {
    const hasText = el => (el.textContent || "").trim().length > 0;
    for (const ch of [...document.querySelectorAll(".zc-cheader")].filter(vis)) {
      const left = ch.querySelector(".zc-cheader__left");
      const right = ch.querySelector(".zc-cheader__right");
      const rightBtns = right ? [...right.querySelectorAll(".zc-btn")].filter(vis) : [];
      const leftFilled = left && (hasText(left) || left.querySelector("input, .zc-search-wrap, .zc-select-shell, .zc-tabs"));
      if (rightBtns.length && !leftFilled)
        fail("LONE ACTION BUTTON",
          "this Container Header has actions on the right but nothing on the left — put the section heading, a Search field or the filters there; a primary button floating alone against empty space is the assembled-not-designed tell", ch);
    }
    /* Buttons stacked directly above a table with no Container Header at all */
    for (const tw of [...document.querySelectorAll(".zc-layout__container .zc-table-wrap")].filter(vis)) {
      const prev = tw.previousElementSibling;
      if (!prev || prev.classList.contains("zc-cheader")) continue;
      const btns = [...prev.querySelectorAll(".zc-btn")].filter(vis);
      const hasLeft = prev.querySelector(".zc-search-wrap, .zc-select-shell, .zc-cheader__title") ||
                      (prev.textContent || "").replace(/\s+/g, " ").trim().length > btns.reduce((n, b) => n + (b.textContent || "").trim().length, 0) + 2;
      if (btns.length && !hasLeft)
        fail("ACTION BAR NOT A CONTAINER HEADER",
          "buttons are sitting above this table in a hand-made row — that bar is the Container Header (.zc-cheader), with actions right and a heading / Search / filters left", prev);
    }
  }

  /* ── 20. Hand-built controls instead of components ─────────────────── */
  for (const el of all) {
    const hasZc = [...el.classList].some(c => c.startsWith("zc-"));
    if (hasZc) continue;
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute("role") || "";
    const clickable = el.hasAttribute("onclick") ||
      ["button", "tab", "checkbox", "radio", "switch", "menuitem"].includes(role);
    if (clickable && !["button", "a", "input", "select", "textarea"].includes(tag))
      fail("HAND-BUILT CONTROL",
        `<${tag}> acts as a control but carries no zc-* component class — use the zcat component (.zc-btn / .zc-tab / .zc-checkbox / .zc-toggle …), never a styled div`, el);
    const INPUT_OWNERS = ".zc-input-wrap, .zc-search-wrap, .zc-select-shell, .zc-select-wrap, " +
      ".zc-textarea, .zc-otp, .zc-checkbox, .zc-radio, .zc-toggle, .zc-datepicker, " +
      ".zc-timepicker, .zc-autocomplete, .zc-numstepper, .zc-input-stepper, " +
      ".zc-upload-input, .zc-kvfield, .zc-doublefield, .zc-slider, .zc-rating";
    if (tag === "input" && el.type !== "hidden" && !el.closest(INPUT_OWNERS))
      fail("HAND-BUILT CONTROL", "bare <input> outside any zcat component — use .zc-input-wrap / .zc-search-wrap / .zc-select-shell", el);
  }

  /* ── 21. Composed, or just stacked? (the "assembled" failure) ─────── */
  if (container && !isEmptyState) {
    // A single wrapper div is still the same stack — descend past it.
    let host = container;
    while (true) {
      const c = [...host.children].filter(vis);
      if (c.length === 1 && c[0].children.length) host = c[0]; else break;
    }
    const kids = [...host.children].filter(vis);
    const gridded = [...host.querySelectorAll("*")].filter(el => {
      if (!vis(el)) return false;
      const cs = getComputedStyle(el);
      const row = (cs.display.includes("flex") && cs.flexDirection.startsWith("row")) ||
                  cs.display.includes("grid");
      if (!row) return false;
      const ch = [...el.children].filter(vis);
      return ch.length >= 2 && ch.every(c => c.getBoundingClientRect().width >= 140);
    });
    if (kids.length >= 4 && !gridded.length && !cards.length && !tableDriven)
      F.push({ rule: "ASSEMBLED, NOT COMPOSED",
        msg: `the container is ${kids.length} components stacked in one vertical column — no multi-column grouping, no cards, no side-by-side relationship anywhere. This is the wireframe shape, not a designed screen: group related content, promote what matters, and use a real composition`,
        sel: path(host) });
  }

  /* ── 22. Every same-role element styled identically = no hierarchy ── */
  if (cards.length >= 3) {
    const sig = cards.map(c => {
      const r = c.getBoundingClientRect(), cs = getComputedStyle(c);
      return `${Math.round(r.width)}x${Math.round(r.height)}|${cs.padding}`;
    });
    if (new Set(sig).size === 1)
      warn("UNIFORM CARDS",
        `all ${cards.length} cards are identical in size and padding — if everything has equal weight, nothing is emphasised. Vary the recipe by importance`, cards[0]);
  }

  /* ── Design metrics — measurable proxies for "designed vs assembled".
     These do NOT judge beauty; they measure the things that reliably separate
     a composed screen from a stack of components: does anything sit side by
     side, is emphasis varied, and does the container run as one long column. */
  const dScope = container || document.body;

  /* widest side-by-side group anywhere in the container */
  let gridCols = 1;
  for (const el of dScope.querySelectorAll("*")) {
    const cs = getComputedStyle(el);
    if (cs.display === "grid") {
      const n = (cs.gridTemplateColumns || "").split(" ").filter(x => x && x !== "none").length;
      if (n > gridCols) gridCols = n;
    } else if (cs.display === "flex" && cs.flexDirection === "row") {
      const kids = [...el.children].filter(vis);
      if (kids.length > 1) {
        const tops = new Set(kids.map(k => Math.round(k.getBoundingClientRect().top / 8)));
        if (tops.size === 1 && kids.length > gridCols) gridCols = kids.length;
      }
    }
  }

  /* how many distinct emphasis levels the page actually uses */
  const typeClasses = new Set();
  for (const el of dScope.querySelectorAll("[class]"))
    for (const c of el.classList)
      if (/^zc-(h[1-6]|subtitle-[1-3])$/.test(c)) typeClasses.add(c);

  /* longest unbroken vertical run of siblings — the wireframe shape */
  let stackRun = 0;
  for (const el of [dScope, ...dScope.querySelectorAll("*")]) {
    const kids = [...el.children].filter(vis);
    if (kids.length < 2) continue;
    const lefts = new Set(kids.map(k => Math.round(k.getBoundingClientRect().left / 8)));
    if (lefts.size === 1 && kids.length > stackRun) stackRun = kids.length;
  }

  return {
    fails: F, warns: W,
    stats: { isEmptyState: isEmptyState, components: zcSet.size, elements: all.length, cards: cards.length,
             fills: fills.length, headings: heads.length,
             gridCols, typeLevels: typeClasses.size, stackRun,
             uniformCards: cards.length > 2 && new Set(cards.map(c => {
               const r = c.getBoundingClientRect();
               return Math.round(r.width) + "x" + Math.round(r.height);
             })).size === 1 }
  };
}
if (typeof module !== "undefined") module.exports = { __zcatAudit };
