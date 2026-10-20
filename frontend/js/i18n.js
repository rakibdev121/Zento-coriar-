// Bangla / English switch for the website. English text is the key: every string the pages show is looked up in
// lang-bn.js and replaced when Bangla is chosen. A MutationObserver translates text the scripts add later, so most
// pages need no changes. Strings with variables use {0}, {1} ... placeholders (see lang-bn.js).
import { BN } from "./lang-bn.js";

const KEY = "zento.lang";
const EXACT = new Map(), EXACT_LC = new Map(), PATS = [];
const esc = (s) => s.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
for (const [en, bn] of BN) {
  if (/\{\d\}/.test(en)) PATS.push({ re: new RegExp("^" + esc(en).replace(/\{\d\}/g, "(.+?)") + "$"), bn });
  else { EXACT.set(en, bn); EXACT_LC.set(en.toLowerCase(), bn); }
}

const REV = new Map(BN.filter(([en]) => !/\{\d\}/.test(en)).map(([en, bn]) => [bn, en]));
/** Text read back from the page may already be Bangla (for example a button label saved before "Working..."): give the English key. */
export const toEnglish = (s) => REV.get(s.trim()) ?? s;

function detect() {
  try { const s = localStorage.getItem(KEY); if (s === "bn" || s === "en") return s; } catch { /* storage blocked */ }
  return (navigator.language || "").toLowerCase().startsWith("bn") ? "bn" : "en";
}
let lang = detect();
export const getLang = () => lang;
/** Locale for dates: Bangla month and day names, but Latin digits so they match the prices. */
export const locale = () => (lang === "bn" ? "bn-BD-u-nu-latn" : undefined);

function nested(g) { return tr(g) ?? EXACT_LC.get(g.trim().toLowerCase()) ?? g; }
function tr(en) {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(en), core = m[2];
  if (!core) return null;
  let out = EXACT.get(core);
  if (out == null) for (const p of PATS) {
    const r = p.re.exec(core);
    if (r) { out = p.bn.replace(/\{(\d)\}/g, (_, i) => nested(r[+i + 1] ?? "")); break; }
  }
  return out == null ? null : m[1] + out + m[3];
}
/** For text that is not shown through the page (confirm boxes etc.): pass the finished English sentence. */
export const t = (en) => (lang === "bn" ? tr(en) ?? en : en);

const ATTRS = ["placeholder", "aria-label", "title", "alt"];
const TEXT = new WeakMap(), ATTR = new WeakMap();
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "TITLE"]);

function applyText(node) {
  if (SKIP.has(node.parentNode?.nodeName)) return;
  const rec = TEXT.get(node);
  const en = rec && node.data === rec.shown ? rec.en : node.data;   // a script wrote new text: that is the new English
  const shown = (lang === "bn" ? tr(en) : null) ?? en;
  if (shown !== node.data) node.data = shown;
  TEXT.set(node, { en, shown });
}
function applyAttrs(el) {
  let rec = ATTR.get(el);
  for (const a of ATTRS) {
    if (!el.hasAttribute(a)) continue;
    rec ||= (ATTR.set(el, {}), ATTR.get(el));
    const cur = el.getAttribute(a), r = rec[a];
    const en = r && cur === r.shown ? r.en : cur;
    const shown = (lang === "bn" ? tr(en) : null) ?? en;
    if (shown !== cur) el.setAttribute(a, shown);
    rec[a] = { en, shown };
  }
}
function walk(root) {
  if (root.nodeType === 3) return applyText(root);
  if (root.nodeType !== 1 || SKIP.has(root.nodeName)) return;
  applyAttrs(root);
  for (const el of root.querySelectorAll("[placeholder],[aria-label],[title],[alt]")) applyAttrs(el);
  const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) applyText(n);
}

let titleEn = null, titleShown = null;
function applyTitle() {
  if (titleEn === null || document.title !== titleShown) titleEn = document.title;
  const [first, ...rest] = titleEn.split(" | ");
  const out = lang === "bn" ? tr(first) : null;
  titleShown = out ? [out, ...rest].join(" | ") : titleEn;
  if (document.title !== titleShown) document.title = titleShown;
}

function loadFont() {
  if (document.getElementById("bn-font")) return;
  const l = document.createElement("link");
  l.id = "bn-font"; l.rel = "stylesheet"; l.href = "https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&display=swap";
  document.head.append(l);
}

export function applyAll() {
  document.documentElement.lang = lang;
  if (lang === "bn") loadFont();
  walk(document.body);
  applyTitle();
}

export function setLang(next) {
  lang = next === "bn" ? "bn" : "en";
  try { localStorage.setItem(KEY, lang); } catch { /* storage blocked */ }
  applyAll();
  window.dispatchEvent(new Event("zento:lang"));
}

function start() {
  applyAll();
  new MutationObserver((list) => {
    for (const m of list) {
      if (m.type === "childList") m.addedNodes.forEach(walk);
      else if (m.type === "characterData") applyText(m.target);
      else if (m.type === "attributes") applyAttrs(m.target);
    }
    applyTitle();
  }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
