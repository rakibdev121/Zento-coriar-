// ZENTO COURIER admin panel. Vanilla ES module, no build step. All server data is rendered with textContent / DOM nodes (never innerHTML).
const TOKEN_KEY = "zento.admin.token", SEEN_KEY = "zento.admin.seen";
const $app = document.getElementById("app");

/* ---------- DOM + icons ---------- */
const NS = "http://www.w3.org/2000/svg";
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (["value", "checked", "disabled", "selected", "hidden"].includes(k)) el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const c of kids.flat(Infinity)) if (c != null) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  return el;
}
const ICONS = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10", box: "M21 8l-9-5-9 5v8l9 5 9-5V8zM3 8l9 5 9-5M12 13v8",
  calendar: "M5 5h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2zM3 10h18M8 3v4M16 3v4", user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  bike: "M5.5 18a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM18.5 18a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM12 18l-3-7h6l3 7M9 11l-1-3H6",
  truck: "M1 6h13v10H1zM14 10h4l3 3v3h-7zM6 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z", tag: "M3 12V4h8l10 10-8 8L3 12zM7.5 8.5h.01",
  pin: "M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11zM12 12a2.5 2.5 0 100-5 2.5 2.5 0 000 5z", chart: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  bell: "M6 8a6 6 0 1112 0c0 7 3 8 3 8H3s3-1 3-8zM10 21h4",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
  search: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3", plus: "M12 5v14M5 12h14", check: "M5 12l5 5L20 7", down: "M6 9l6 6 6-6",
  up: "M12 19V5M5 12l7-7 7 7", dn: "M12 5v14M19 12l-7 7-7-7", right: "M5 12h14M13 5l7 7-7 7", x: "M6 6l12 12M18 6L6 18", menu: "M4 6h16M4 12h16M4 18h16",
  logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9", download: "M12 3v12M7 10l5 5 5-5M4 21h16", clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
};
const icon = (n, size) => s("svg", { class: "ic", viewBox: "0 0 24 24", "aria-hidden": "true", ...(size ? { style: `width:${size}px;height:${size}px` } : {}) }, s("path", { d: ICONS[n] }));

/* ---------- formatting ---------- */
const STATUS = { booked: "Pending", picked_up: "Picked Up", in_transit: "In Transit", out_for_delivery: "Out for Delivery", delivered: "Delivered", cancelled: "Cancelled" };
const pill = (st) => h("span", { class: `pill ${st}` }, STATUS[st] || st);
let CURRENCY = "USD";
function money(v, cur = CURRENCY) {
  const n = Number(v);
  for (const loc of ["en-BD", "en"]) { try { return new Intl.NumberFormat(loc, { style: "currency", currency: cur }).format(n); } catch { /* try next */ } }
  return `${cur} ${n.toFixed(2)}`;
}
const dShort = (iso) => new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const dLong = (iso) => new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
function etaLabel(iso) {
  if (!iso) return "–";
  const t = new Date(iso + "T00:00:00"), now = new Date(), day = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((t - day) / 864e5);
  return diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : dShort(iso);
}
function ago(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 6e4));
  if (m < 1) return "just now"; if (m < 60) return `${m} min${m === 1 ? "" : "s"} ago`;
  const hr = Math.round(m / 60); if (hr < 24) return `${hr} hr${hr === 1 ? "" : "s"} ago`;
  const d = Math.round(hr / 24); return `${d} day${d === 1 ? "" : "s"} ago`;
}
const initials = (n) => (n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const HUES = ["#e0334c", "#2b6ef6", "#8b4bf0", "#14a67a", "#d9822b", "#1d8fd1", "#c13584"];
const hue = (name) => HUES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % HUES.length];

/* ---------- API ---------- */
class ApiError extends Error { constructor(msg, status, fieldErrors = []) { super(msg); this.status = status; this.fieldErrors = fieldErrors; } }
const getToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ } };
async function api(path, { method = "GET", body, auth = true, blob = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`;
  let res;
  try { res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); }
  catch { throw new ApiError("Cannot reach the server. Check your connection and try again.", 0); }
  if (res.ok) return blob ? res.blob() : res.status === 204 ? null : res.json();
  let data = null; try { data = await res.json(); } catch { /* no body */ }
  if (res.status === 401 && auth && getToken()) { setToken(null); state.user = null; renderLogin("Your session has expired. Sign in again."); }
  throw new ApiError(typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.", res.status, Array.isArray(data?.errors) ? data.errors : []);
}

/* ---------- UI helpers ---------- */
const state = { user: null, unread: 0, pending: 0, renderId: 0 };
function toast(msg, bad = false) {
  const t = h("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, msg);
  document.body.append(t); setTimeout(() => t.remove(), 3500);
}
function modal(title, body, { wide = false } = {}) {
  const close = () => { ov.remove(); document.removeEventListener("keydown", esc); };
  const esc = (e) => { if (e.key === "Escape") close(); };
  const ov = h("div", { class: "overlay", onmousedown: (e) => { if (e.target === ov) close(); } },
    h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title },
      h("div", { class: "modal-head" }, h("h2", {}, title), h("button", { class: "x", "aria-label": "Close", onclick: close }, icon("x"))), body));
  document.addEventListener("keydown", esc); document.body.append(ov);
  ov.querySelector("input, select, textarea")?.focus();
  return { close };
}
/** Form field with an error slot; register it in `errs` so server field errors can be shown under it. */
function fld(label, input, errs, name) {
  const slot = h("div", { class: "err", hidden: true }); if (errs && name) errs[name] = slot;
  return h("div", { class: "fld" }, h("label", {}, label), input, slot);
}
function showErrors(box, errs, e) {
  Object.values(errs).forEach((x) => { x.hidden = true; x.textContent = ""; });
  let general = e.message;
  if (e.fieldErrors?.length) {
    const rest = [];
    for (const fe of e.fieldErrors) { const slot = errs[fe.field.split(".")[0]]; if (slot) { slot.hidden = false; slot.textContent = fe.message; } else rest.push(fe.message); }
    general = rest.length ? rest.join(" ") : "Some details need fixing.";
  }
  box.hidden = false; box.textContent = general;
}
async function run(btn, box, errs, fn) {
  btn.disabled = true; box.hidden = true;
  try { await fn(); } catch (e) { if (e instanceof ApiError) showErrors(box, errs, e); else throw e; } finally { btn.disabled = false; }
}
const opt = (v, label, sel) => h("option", { value: v, selected: !!sel }, label);
function table(cols, rows, empty = "Nothing here yet.") {
  if (!rows.length) return h("div", { class: "empty" }, empty);
  return h("div", { class: "tbl-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c.h)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, cols.map((c) => h("td", { class: c.wrap ? "wrap" : "" }, c.r(r))))))));
}
function pager(page, size, total, go) {
  const pages = Math.max(1, Math.ceil(total / size));
  return h("div", { class: "pager" }, h("span", {}, total ? `Showing ${(page - 1) * size + 1}–${Math.min(total, page * size)} of ${total}` : "No results"),
    h("div", {}, h("button", { class: "btn sm", disabled: page <= 1, onclick: () => go(page - 1) }, "Previous"), h("span", { style: "align-self:center" }, `${page} / ${pages}`),
      h("button", { class: "btn sm", disabled: page >= pages, onclick: () => go(page + 1) }, "Next")));
}
const pageHead = (title, sub, ...actions) => h("div", { class: "page-head" }, h("div", {}, h("h1", {}, title), sub && h("p", { class: "muted" }, sub)), h("div", { class: "toolbar", style: "margin:0" }, actions));
const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* ---------- charts ---------- */
function niceStep(max) { const raw = Math.max(max, 5) / 5, p = 10 ** Math.floor(Math.log10(raw)); return [1, 2, 2.5, 5, 10].map((m) => m * p).find((x) => x >= raw); }
function smooth(pts) {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2, k = 0.18;
    d += `C${p1[0] + (p2[0] - p0[0]) * k},${p1[1] + (p2[1] - p0[1]) * k} ${p2[0] - (p3[0] - p1[0]) * k},${p2[1] - (p3[1] - p1[1]) * k} ${p2[0]},${p2[1]}`;
  }
  return d;
}
function lineChart(labels, series) {
  const W = 560, H = 270, L = 42, R = 14, T = 12, B = 30, step = niceStep(Math.max(...series.flatMap((x) => x.values))), top = step * 5;
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, labels.length - 1), y = (v) => T + (H - T - B) * (1 - v / top);
  const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Parcel overview chart" });
  const defs = s("defs"); svg.append(defs);
  for (let i = 0; i <= 5; i++) {
    svg.append(s("line", { x1: L, x2: W - R, y1: y(i * step), y2: y(i * step), stroke: "#16294f", "stroke-width": 1 }), s("text", { x: L - 10, y: y(i * step) + 4, "text-anchor": "end" }, i * step));
  }
  labels.forEach((lb, i) => svg.append(s("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, lb)));
  series.forEach((sr, si) => {
    const pts = sr.values.map((v, i) => [x(i), y(v)]), id = `g${si}`;
    defs.append(s("linearGradient", { id, x1: 0, x2: 0, y1: 0, y2: 1 }, s("stop", { offset: "0%", "stop-color": sr.color, "stop-opacity": ".38" }), s("stop", { offset: "100%", "stop-color": sr.color, "stop-opacity": ".02" })));
    const line = smooth(pts);
    svg.append(s("path", { d: `${line}L${x(labels.length - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: `url(#${id})` }), s("path", { d: line, fill: "none", stroke: sr.color, "stroke-width": 2.5, "stroke-linecap": "round" }));
    pts.forEach(([px, py], i) => svg.append(s("circle", { cx: px, cy: py, r: 4, fill: sr.color, stroke: "#0b1a36", "stroke-width": 1.5 }, s("title", {}, `${sr.name}: ${sr.values[i]} (${labels[i]})`))));
  });
  return svg;
}
function barChart(labels, values, color, fmt = (v) => v) {
  const W = 700, H = 230, L = 46, R = 10, T = 10, B = 28, step = niceStep(Math.max(...values, 0)), top = step * 5, bw = (W - L - R) / values.length;
  const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img" });
  for (let i = 0; i <= 5; i++) { const yy = T + (H - T - B) * (1 - i / 5); svg.append(s("line", { x1: L, x2: W - R, y1: yy, y2: yy, stroke: "#16294f" }), s("text", { x: L - 8, y: yy + 4, "text-anchor": "end" }, fmt(i * step))); }
  const every = Math.ceil(values.length / 10);
  values.forEach((v, i) => {
    const bh = (H - T - B) * (v / top), bx = L + i * bw;
    svg.append(s("rect", { x: bx + bw * 0.15, y: H - B - bh, width: Math.max(1, bw * 0.7), height: bh, rx: 2, fill: color }, s("title", {}, `${labels[i]}: ${fmt(v)}`)));
    if (i % every === 0) svg.append(s("text", { x: bx + bw / 2, y: H - 8, "text-anchor": "middle" }, labels[i]));
  });
  return svg;
}
function liveMap(live) {
  const svg = s("svg", { class: "map", viewBox: "0 0 380 190", role: "img", "aria-label": "Live shipment route" });
  [[0, 40, 380, 55], [0, 120, 380, 105], [60, 0, 90, 190], [200, 0, 170, 190], [300, 0, 320, 190]].forEach(([a, b, c, d]) => svg.append(s("line", { x1: a, y1: b, x2: c, y2: d, stroke: "#0f2a52", "stroke-width": 2 })));
  const P = [[64, 82], [120, 160], [230, 18], [292, 102]], bez = (t) => [0, 1].map((i) => (1 - t) ** 3 * P[0][i] + 3 * (1 - t) ** 2 * t * P[1][i] + 3 * (1 - t) * t * t * P[2][i] + t ** 3 * P[3][i]);
  svg.append(s("path", { d: `M${P[0]} C${P[1]} ${P[2]} ${P[3]}`, fill: "none", stroke: "#2f7bff", "stroke-width": 3, "stroke-linecap": "round" }));
  const pin = (px, py, col, label) => { svg.append(s("path", { d: `M${px},${py}c-9,-9 -9,-26 0,-26s9,17 0,26z`, fill: col, transform: `translate(0,0)` }), s("circle", { cx: px, cy: py - 20, r: 4, fill: "#fff" }), s("text", { x: px, y: py + 16, "text-anchor": "middle", style: "fill:#dbe6ff;font-size:11px" }, label)); };
  pin(P[0][0], P[0][1], "#14c38e", live.pickup_city); pin(P[3][0], P[3][1], "#2b6ef6", live.delivery_city);
  const [tx, ty] = bez({ picked_up: 0.2, in_transit: 0.5, out_for_delivery: 0.8 }[live.status] ?? 0.5);
  svg.append(s("circle", { cx: tx, cy: ty, r: 11, fill: "#fff" }), s("path", { d: "M-6,-3h8v6h-8zM2,-1h3l2,2v2h-5z", fill: "#0b57d0", transform: `translate(${tx},${ty})` }));
  return svg;
}

/* ---------- shell ---------- */
const NAV = [["dashboard", "Dashboard", "home"], ["parcels", "Parcels", "box"], ["bookings", "Bookings", "calendar"], ["customers", "Customers", "user"], ["riders", "Riders", "bike"],
  ["providers", "Courier Providers", "truck"], ["pricing", "Delivery Pricing", "tag"], ["areas", "Service Areas", "pin"], ["reports", "Reports", "chart"], ["notifications", "Notifications", "bell"], ["settings", "Settings", "gear"]];
const logo = () => s("svg", { width: 46, height: 44, viewBox: "0 0 46 44", "aria-hidden": "true" }, s("defs", {}, s("linearGradient", { id: "zl", x1: 0, y1: 0, x2: 1, y2: 1 }, s("stop", { offset: "0", "stop-color": "#35c4ff" }), s("stop", { offset: "1", "stop-color": "#2b5df6" }))), s("path", { d: "M4 3h38v9L19 31h23v10H4v-9l23-19H4z", fill: "url(#zl)" }));
const brand = () => h("div", { class: "brand" }, logo(), h("div", {}, h("b", {}, "ZENTO"), h("small", {}, "COURIER")));
function logout() { setToken(null); state.user = null; renderLogin(); }

function renderLogin(msg) {
  const err = h("div", { class: "form-err", hidden: !msg }, msg || ""), email = h("input", { type: "email", autocomplete: "username", required: true, placeholder: "admin@example.com" }),
    pw = h("input", { type: "password", autocomplete: "current-password", required: true }), btn = h("button", { class: "btn primary", style: "justify-content:center;width:100%", type: "submit" }, "Sign in");
  const form = h("form", { class: "form", onsubmit: async (e) => {
    e.preventDefault(); btn.disabled = true; err.hidden = true;
    try {
      const r = await api("/auth/login", { method: "POST", body: { email: email.value.trim(), password: pw.value }, auth: false });
      if (!r.user.is_admin) throw new ApiError("This account does not have admin access.", 403);
      setToken(r.access_token); state.user = r.user; start();
    } catch (x) { err.hidden = false; err.textContent = x.message; btn.disabled = false; }
  } }, err, fld("Email", email), fld("Password", pw), btn);
  $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", {}, "Admin sign in"), h("p", { class: "muted" }, "ZENTO COURIER control panel"), form)));
}

let outlet, navEls = {}, clockEl;
function shell() {
  const side = h("aside", { class: "side", id: "side" }, brand(), h("nav", { class: "nav", "aria-label": "Admin" }, NAV.map(([id, label, ic]) => {
    const a = h("a", { href: `#/${id}`, onclick: () => side.classList.remove("open") }, icon(ic), label, id === "notifications" && h("span", { class: "badge", hidden: true }));
    navEls[id] = a; return a;
  })), h("div", { class: "side-foot" }, h("b", {}, "ZENTO COURIER"), h("small", {}, "Fast • Safe • Reliable")));
  const q = h("input", { type: "search", placeholder: "Search parcels, tracking number, customer...", "aria-label": "Search", onkeydown: (e) => { if (e.key === "Enter" && q.value.trim()) { location.hash = `#/parcels?q=${encodeURIComponent(q.value.trim())}`; } } });
  const bell = h("button", { class: "bell", "aria-label": "Notifications", onclick: () => { location.hash = "#/notifications"; } }, icon("bell", 24), h("span", { class: "badge", hidden: true }));
  const menu = h("div", { class: "menu", hidden: true }, h("button", { onclick: () => { menu.hidden = true; location.hash = "#/settings"; } }, icon("gear"), "Settings"), h("button", { onclick: logout }, icon("logout"), "Sign out"));
  const me = h("button", { class: "me", "aria-haspopup": "menu", onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; } }, h("span", { class: "avatar" }, initials(state.user.full_name)),
    h("div", {}, h("b", {}, state.user.full_name), h("small", {}, "Admin")), icon("down"), menu);
  document.addEventListener("click", () => { menu.hidden = true; });
  outlet = h("main", { class: "content", id: "main" });
  $app.replaceChildren(h("div", { class: "shell" }, side, h("div", { class: "main" },
    h("header", { class: "top" }, h("button", { class: "menu-btn", "aria-label": "Menu", onclick: () => side.classList.toggle("open") }, icon("menu", 24)), h("div", { class: "search" }, icon("search"), q), h("div", { class: "top-right" }, bell, me)),
    outlet, h("footer", { class: "foot" }, h("span", {}, "ZENTO COURIER Admin Panel v1.0"), h("nav", {}, h("a", { href: "/" }, "Website"), h("a", { href: "/track.html" }, "Track"), h("a", { href: "/api/health" }, "Status"))))));
  state.bell = bell.querySelector(".badge");
}
function updateBadges() {
  const n = state.unread > 99 ? "99+" : state.unread;
  for (const el of [state.bell, navEls.notifications?.querySelector(".badge")]) if (el) { el.hidden = !state.unread; el.textContent = n; }
}
async function pollNotifications() {
  if (!state.user) return;
  try {
    const { items } = await api("/admin/notifications"), seen = Number(localStorage.getItem(SEEN_KEY) || 0);
    state.unread = items.filter((i) => new Date(i.created_at).getTime() > seen).length; updateBadges();
  } catch { /* transient */ }
}

/* ---------- router ---------- */
const PAGES = {};
async function route() {
  if (!state.user) return;
  const [path, qs] = location.hash.replace(/^#\//, "").split("?"), name = PAGES[path] ? path : "dashboard", id = ++state.renderId;
  Object.entries(navEls).forEach(([k, a]) => a.classList.toggle("active", k === name));
  outlet.replaceChildren(h("div", { class: "empty" }, "Loading…")); window.scrollTo(0, 0);
  const ctx = { el: outlet, params: new URLSearchParams(qs || ""), stale: () => id !== state.renderId };
  try { await PAGES[name](ctx); }
  catch (e) { if (!ctx.stale()) outlet.replaceChildren(h("div", { class: "card" }, h("p", { class: "form-err" }, e.message || "Could not load this page."), h("button", { class: "btn", onclick: route }, "Retry"))); }
}
window.addEventListener("hashchange", route);

/* ---------- shared dialogs ---------- */
const ZONES = [["local", "Local"], ["regional", "Regional"], ["national", "National"]], SERVICES = [["standard", "Standard"], ["express", "Express"], ["same_day", "Same day"]];
const FORM_BOX = () => h("div", { class: "form-err", hidden: true });
function download(blob, name) { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }

function openCustomerForm(done) {
  const errs = {}, box = FORM_BOX(), v = { full_name: h("input", { autocomplete: "off" }), email: h("input", { type: "email", autocomplete: "off" }), phone: h("input", { type: "tel", placeholder: "+880 1XXX XXXXXX" }), password: h("input", { type: "text", autocomplete: "off", placeholder: "At least 8 characters, letters and numbers" }) };
  const btn = h("button", { class: "btn primary", type: "submit" }, "Add customer"), m = modal("Add Customer", h("form", { class: "form", onsubmit: (e) => {
    e.preventDefault();
    run(btn, box, errs, async () => { await api("/admin/customers", { method: "POST", body: Object.fromEntries(Object.entries(v).map(([k, el]) => [k, el.value])) }); m.close(); toast("Customer added"); done?.(); });
  } }, box, fld("Full name", v.full_name, errs, "full_name"), fld("Email", v.email, errs, "email"), fld("Phone", v.phone, errs, "phone"), fld("Temporary password", v.password, errs, "password"), h("div", { class: "actions" }, btn)));
}

function openRiderForm(r, done) {
  const errs = {}, box = FORM_BOX(), v = { full_name: h("input", { value: r?.full_name || "" }), phone: h("input", { type: "tel", value: r?.phone || "" }), city: h("input", { value: r?.city || "" }),
    vehicle: h("select", {}, ["bike", "bicycle", "scooter", "van", "truck"].map((x) => opt(x, x[0].toUpperCase() + x.slice(1), (r?.vehicle || "bike") === x))), is_active: h("input", { type: "checkbox", checked: r ? r.is_active : true }) };
  const btn = h("button", { class: "btn primary", type: "submit" }, r ? "Save changes" : "Add rider"), m = modal(r ? "Edit Rider" : "Add Rider", h("form", { class: "form", onsubmit: (e) => {
    e.preventDefault();
    run(btn, box, errs, async () => {
      const body = { full_name: v.full_name.value, phone: v.phone.value, city: v.city.value, vehicle: v.vehicle.value, is_active: v.is_active.checked };
      await api(r ? `/admin/riders/${r.id}` : "/admin/riders", { method: r ? "PUT" : "POST", body }); m.close(); toast("Rider saved"); done?.();
    });
  } }, box, fld("Full name", v.full_name, errs, "full_name"), h("div", { class: "two" }, fld("Phone", v.phone, errs, "phone"), fld("City", v.city, errs, "city")), fld("Vehicle", v.vehicle, errs, "vehicle"),
    h("label", { class: "check" }, v.is_active, "Active (can be assigned to parcels)"), h("div", { class: "actions" }, btn)));
}

function openProviderForm(p, done) {
  const errs = {}, box = FORM_BOX(), v = { name: h("input", { value: p?.name || "" }), phone: h("input", { type: "tel", value: p?.phone || "" }), website: h("input", { placeholder: "https://", value: p?.website || "" }), is_active: h("input", { type: "checkbox", checked: p ? p.is_active : true }) };
  const btn = h("button", { class: "btn primary", type: "submit" }, p ? "Save changes" : "Add provider"), m = modal(p ? "Edit Courier Provider" : "Add Courier Provider", h("form", { class: "form", onsubmit: (e) => {
    e.preventDefault();
    run(btn, box, errs, async () => {
      await api(p ? `/admin/providers/${p.id}` : "/admin/providers", { method: p ? "PUT" : "POST", body: { name: v.name.value, phone: v.phone.value, website: v.website.value, is_active: v.is_active.checked } });
      m.close(); toast("Provider saved"); done?.();
    });
  } }, box, fld("Name", v.name, errs, "name"), h("div", { class: "two" }, fld("Phone", v.phone, errs, "phone"), fld("Website", v.website, errs, "website")), h("label", { class: "check" }, v.is_active, "Active"), h("div", { class: "actions" }, btn)));
}

function openAreaForm(a, done) {
  const errs = {}, box = FORM_BOX(), v = { city: h("input", { value: a?.city || "" }), region: h("input", { value: a?.region || "" }), is_active: h("input", { type: "checkbox", checked: a ? a.is_active : true }) };
  const btn = h("button", { class: "btn primary", type: "submit" }, a ? "Save changes" : "Add area"), m = modal(a ? "Edit Service Area" : "Add Service Area", h("form", { class: "form", onsubmit: (e) => {
    e.preventDefault();
    run(btn, box, errs, async () => { await api(a ? `/admin/areas/${a.id}` : "/admin/areas", { method: a ? "PUT" : "POST", body: { city: v.city.value, region: v.region.value, is_active: v.is_active.checked } }); m.close(); toast("Service area saved"); done?.(); });
  } }, box, fld("City", v.city, errs, "city"), fld("Region / division (optional)", v.region, errs, "region"), h("label", { class: "check" }, v.is_active, "Active"), h("div", { class: "actions" }, btn)));
}

function openBookingForm(done) {
  const errs = {}, box = FORM_BOX(), quoteBox = h("div", { class: "form-ok", hidden: true }), mk = (type = "text", extra = {}) => h("input", { type, ...extra });
  const f = { sender_name: mk(), sender_phone: mk("tel"), pickup_address: mk(), pickup_city: mk(), recipient_name: mk(), recipient_phone: mk("tel"), delivery_address: mk(), delivery_city: mk(),
    weight_kg: mk("number", { step: "0.01", min: "0.01" }), length_cm: mk("number", { min: 1 }), width_cm: mk("number", { min: 1 }), height_cm: mk("number", { min: 1 }), declared_value: mk("number", { min: 0, step: "0.01" }), description: mk() };
  const zone = h("select", {}, ZONES.map(([k, l]) => opt(k, l))), service = h("select", {}, SERVICES.map(([k, l]) => opt(k, l))), fragile = h("input", { type: "checkbox" });
  const cq = h("input", { type: "search", placeholder: "Search customers by name, email or phone" }), cs = h("select", {}, opt("", "Search above, then choose…")); let people = [];
  const loadPeople = debounce(async () => {
    const r = await api(`/admin/customers?page_size=20&q=${encodeURIComponent(cq.value)}`); people = r.items;
    cs.replaceChildren(...(people.length ? people.map((p) => opt(p.id, `${p.full_name} · ${p.email}`)) : [opt("", "No customers found")])); fillSender();
  });
  const fillSender = () => { const p = people.find((x) => String(x.id) === cs.value); if (p) { if (!f.sender_name.value) f.sender_name.value = p.full_name; if (!f.sender_phone.value) f.sender_phone.value = p.phone; } };
  cq.addEventListener("input", loadPeople); cs.addEventListener("change", fillSender); loadPeople();
  const num = (el) => (el.value.trim() === "" ? undefined : Number(el.value)), str = (el) => el.value.trim();
  const body = () => ({ user_id: Number(cs.value) || undefined, sender_name: str(f.sender_name), sender_phone: str(f.sender_phone), pickup_address: str(f.pickup_address), pickup_city: str(f.pickup_city), recipient_name: str(f.recipient_name),
    recipient_phone: str(f.recipient_phone), delivery_address: str(f.delivery_address), delivery_city: str(f.delivery_city), zone: zone.value, service: service.value, weight_kg: str(f.weight_kg),
    length_cm: num(f.length_cm), width_cm: num(f.width_cm), height_cm: num(f.height_cm), declared_value: str(f.declared_value) || "0", fragile: fragile.checked, description: str(f.description) || null });
  const qbtn = h("button", { class: "btn", type: "button", onclick: () => run(qbtn, box, errs, async () => {
    const b = body(), q = await api("/pricing/quote", { method: "POST", auth: false, body: { zone: b.zone, service: b.service, weight_kg: b.weight_kg, length_cm: b.length_cm, width_cm: b.width_cm, height_cm: b.height_cm, declared_value: b.declared_value, fragile: b.fragile } });
    quoteBox.hidden = false; quoteBox.textContent = `Estimated price ${money(q.total, q.currency)} · ${q.chargeable_weight_kg} kg chargeable · ETA ${q.eta_max_days === 0 ? "same day" : `${q.eta_min_days}–${q.eta_max_days} day(s)`}`;
  }) }, "Get quote"), btn = h("button", { class: "btn primary", type: "submit" }, "Create booking");
  const m = modal("Create Booking", h("form", { class: "form", onsubmit: (e) => {
    e.preventDefault();
    run(btn, box, errs, async () => {
      if (!cs.value) throw new ApiError("Choose the customer this booking belongs to.", 422);
      const p = await api("/admin/bookings", { method: "POST", body: body() }); m.close(); toast(`Booking ${p.tracking_number} created`); done?.();
    });
  } }, box, h("div", { class: "fld" }, h("label", {}, "Customer"), cq, h("div", { style: "height:8px" }), cs),
    h("div", { class: "two" }, fld("Sender name", f.sender_name, errs, "sender_name"), fld("Sender phone", f.sender_phone, errs, "sender_phone")),
    h("div", { class: "two" }, fld("Pickup address", f.pickup_address, errs, "pickup_address"), fld("Pickup city", f.pickup_city, errs, "pickup_city")),
    h("div", { class: "two" }, fld("Recipient name", f.recipient_name, errs, "recipient_name"), fld("Recipient phone", f.recipient_phone, errs, "recipient_phone")),
    h("div", { class: "two" }, fld("Delivery address", f.delivery_address, errs, "delivery_address"), fld("Delivery city", f.delivery_city, errs, "delivery_city")),
    h("div", { class: "three" }, fld("Zone", zone, errs, "zone"), fld("Service", service, errs, "service"), fld("Weight (kg)", f.weight_kg, errs, "weight_kg")),
    h("div", { class: "three" }, fld("Length (cm)", f.length_cm, errs, "length_cm"), fld("Width (cm)", f.width_cm, errs, "width_cm"), fld("Height (cm)", f.height_cm, errs, "height_cm")),
    h("div", { class: "two" }, fld("Declared value", f.declared_value, errs, "declared_value"), fld("Description (optional)", f.description, errs, "description")),
    h("label", { class: "check" }, fragile, "Fragile handling"), quoteBox, h("div", { class: "actions" }, qbtn, btn)), { wide: true });
}

async function openParcel(id, changed) {
  const body = h("div", {}, h("div", { class: "empty" }, "Loading…")), m = modal("Parcel details", body, { wide: true });
  async function paint() {
    const [p, riders, provs] = await Promise.all([api(`/admin/parcels/${id}`), api("/admin/riders"), api("/admin/providers")]);
    const closed = ["delivered", "cancelled"].includes(p.status), errs = {}, box = FORM_BOX();
    const flow = ["booked", "picked_up", "in_transit", "out_for_delivery", "delivered"], next = flow.slice(flow.indexOf(p.status) + 1).concat("cancelled");
    const stSel = h("select", {}, opt("", "Keep current status"), next.map((x) => opt(x, STATUS[x]))), note = h("input", { placeholder: "Note shown on the tracking timeline (optional)" }), loc = h("input", { placeholder: "Location (optional)" });
    const rSel = h("select", {}, opt("", "Unassigned"), riders.items.filter((r) => r.is_active || r.id === p.rider?.id).map((r) => opt(r.id, r.full_name + (r.city ? ` · ${r.city}` : ""), r.id === p.rider?.id)));
    const pSel = h("select", {}, opt("", "None"), provs.items.filter((x) => x.is_active || x.id === p.provider?.id).map((x) => opt(x.id, x.name, x.id === p.provider?.id)));
    const btn = h("button", { class: "btn primary", type: "submit" }, "Save changes");
    const kv = (k, val) => h("div", {}, h("small", {}, k), h("span", {}, val ?? "–"));
    body.replaceChildren(
      h("div", { class: "card-head" }, h("div", {}, h("b", { class: "mono", style: "font-size:17px" }, p.tracking_number), h("div", { class: "muted" }, `Booked ${dLong(p.created_at)}`)), pill(p.status)),
      h("div", { class: "kv" }, kv("Customer", `${p.customer_name} · ${p.customer_email}`), kv("Price", money(p.price_total)), kv("Sender", `${p.sender_name} · ${p.sender_phone}`), kv("Recipient", `${p.recipient_name} · ${p.recipient_phone}`),
        kv("Pickup", `${p.pickup_address}, ${p.pickup_city}`), kv("Delivery", `${p.delivery_address}, ${p.delivery_city}`), kv("Service", `${p.zone} · ${p.service.replace("_", " ")}`),
        kv("Weight", `${p.weight_kg} kg (chargeable ${p.chargeable_weight_kg} kg)`), kv("Declared value", money(p.declared_value)), kv("ETA", etaLabel(p.eta)), p.description && kv("Contents", p.description), p.fragile && kv("Handling", "Fragile")),
      h("div", { class: "muted", style: "margin-bottom:6px" }, p.price_breakdown.map((l) => `${l.label}: ${money(l.amount)}`).join("  ·  ")), h("hr"),
      h("h3", { style: "margin-bottom:10px" }, "Timeline"), h("ul", { class: "timeline" }, [...p.events].reverse().map((e) => h("li", {}, h("div", {}, h("b", {}, STATUS[e.status]), " — ", e.note, h("small", {}, `${dLong(e.created_at)}${e.location ? ` · ${e.location}` : ""}`))))),
      closed ? h("p", { class: "muted" }, "This parcel is closed; it can no longer be changed.") : h("form", { class: "form", onsubmit: (e) => {
        e.preventDefault();
        run(btn, box, errs, async () => {
          const patch = {};
          if (stSel.value) { patch.status = stSel.value; if (note.value.trim()) patch.note = note.value.trim(); if (loc.value.trim()) patch.location = loc.value.trim(); }
          if ((rSel.value || null) !== (p.rider ? String(p.rider.id) : null)) patch.rider_id = rSel.value ? Number(rSel.value) : null;
          if ((pSel.value || null) !== (p.provider ? String(p.provider.id) : null)) patch.provider_id = pSel.value ? Number(pSel.value) : null;
          if (!Object.keys(patch).length) throw new ApiError("Nothing to save yet.", 0);
          await api(`/admin/parcels/${id}`, { method: "PATCH", body: patch }); toast("Parcel updated"); changed?.(); await paint();
        });
      } }, h("h3", {}, "Update parcel"), box, h("div", { class: "two" }, fld("Rider", rSel), fld("Courier provider", pSel)), h("div", { class: "two" }, fld("New status", stSel), fld("Location", loc)), fld("Note", note), h("div", { class: "actions" }, btn)));
  }
  try { await paint(); } catch (e) { body.replaceChildren(h("div", { class: "form-err" }, e.message)); }
  return m;
}

/* ---------- pages ---------- */
let clockTimer;
PAGES.dashboard = async (ctx) => {
  clearInterval(clockTimer);
  const d = await api("/admin/dashboard"); if (ctx.stale()) return; CURRENCY = d.currency;
  const dateEl = h("span", {}), timeEl = h("span", {}), tick = () => { const n = new Date(); dateEl.textContent = n.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); timeEl.textContent = n.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); };
  tick(); clockTimer = setInterval(tick, 20000);
  const statCard = (key, label, ic, color) => {
    const st = d.stats[key], t = st.trend;
    return h("div", { class: "card stat" }, h("div", { class: "ico", style: `background:${color}` }, icon(ic)), h("div", {}, h("div", { class: "lbl" }, label), h("div", { class: "val num" }, st.value.toLocaleString()),
      h("div", { class: "tr" }, t == null ? "No change vs. last 7 days" : [h("b", { class: t >= 0 ? "up" : "down" }, `${t >= 0 ? "↑" : "↓"} ${Math.abs(t)}%`), "vs. last 7 days"])));
  };
  const labels = d.chart.map((x) => dShort(x.date));
  const chartCard = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Parcel Overview"), h("div", { class: "legend" }, [["Delivered", "#14c38e"], ["In Transit", "#3b82f6"], ["Pending", "#f5a524"]].map(([n, c]) => h("span", {}, h("i", { style: `background:${c}` }), n)))),
    lineChart(labels, [{ name: "Delivered", color: "#14c38e", values: d.chart.map((x) => x.delivered) }, { name: "In Transit", color: "#3b82f6", values: d.chart.map((x) => x.in_transit) }, { name: "Pending", color: "#f5a524", values: d.chart.map((x) => x.pending) }]));
  const live = d.live, liveCard = h("section", { class: "card live" }, h("div", { class: "card-head" }, h("h2", {}, "Live Tracking"), h("a", { class: "link", href: "#/parcels?status=active" }, "View All", icon("right", 14))),
    live ? [liveMap(live), h("div", { class: "live-foot" }, h("div", {}, h("div", {}, h("span", { class: "dot" }), h("b", {}, live.status === "out_for_delivery" ? "Out for delivery" : live.status === "picked_up" ? "Picked up" : "On the way")), h("small", { class: "muted" }, live.rider ? `Rider: ${live.rider}` : "No rider assigned")),
      h("div", { style: "text-align:right" }, h("small", { class: "muted" }, "Tracking No."), h("div", { class: "mono", style: "color:var(--blue-2)" }, live.tracking_number)))] : h("div", { class: "empty" }, "No shipments are on the road right now."));
  const recent = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Recent Parcels"), h("a", { class: "link", href: "#/parcels" }, "View All", icon("right", 14))),
    table([{ h: "Tracking No.", r: (p) => h("span", { class: "mono", style: "color:var(--blue-2)" }, p.tracking_number) }, { h: "Customer", r: (p) => p.customer_name }, { h: "From → To", r: (p) => `${p.pickup_city} → ${p.delivery_city}` },
      { h: "Status", r: (p) => pill(p.status) }, { h: "ETA", r: (p) => etaLabel(p.eta) }, { h: "Action", r: (p) => h("button", { class: "btn sm", onclick: () => openParcel(p.id, route) }, "View") }], d.recent_parcels, "No parcels yet."));
  const tones = ["#14c38e", "#3b82f6", "#8b4bf0", "#64748b"];
  const provCard = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Top Courier Providers"), h("a", { class: "link", href: "#/providers" }, "View All", icon("right", 14))),
    d.providers.length ? h("div", { class: "prov" }, d.providers.map((p, i) => h("div", { class: "prov-row" }, h("div", { class: "logo-tile", style: `background:${p.name === "Others" ? "#2a3b5c" : hue(p.name)}` }, p.name === "Others" ? "•••" : initials(p.name)),
      h("div", {}, h("div", { class: "bar-top" }, h("span", {}, p.name), h("b", { class: "num" }, `${p.share}%`)), h("div", { class: "bar" }, h("i", { style: `width:${p.share}%;background:${tones[i] || tones[3]}` })))))) : h("div", { class: "empty" }, "No parcels are assigned to a courier provider yet."));
  const actIc = { booking: "calendar", delivered: "check", rider: "bike", customer: "user", status: "clock" };
  const quick = h("section", { class: "card" }, h("h2", { style: "margin-bottom:14px" }, "Quick Actions"), h("div", { class: "qa" },
    h("button", { class: "primary", onclick: () => openBookingForm(route) }, icon("plus"), "Create Booking"), h("button", { onclick: () => openCustomerForm(route) }, icon("user"), "Add Customer"), h("button", { onclick: () => openRiderForm(null, route) }, icon("bike"), "Add Rider"),
    h("button", { onclick: () => { location.hash = "#/pricing"; } }, icon("tag"), "Manage Pricing"), h("button", { onclick: () => { location.hash = "#/areas"; } }, icon("pin"), "Service Areas")));
  const acts = h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Recent Activities"), h("a", { class: "link", href: "#/notifications" }, "View All", icon("right", 14))),
    d.activities.length ? h("div", { class: "acts" }, d.activities.map((a) => h("div", { class: "act" }, h("div", { class: `ai ${a.kind}` }, icon(actIc[a.kind] || "clock", 18)), h("div", {}, h("b", {}, a.title), h("small", {}, h("span", {}, a.detail || ""), h("span", {}, ago(a.created_at))))))) : h("div", { class: "empty" }, "Nothing has happened yet."));
  ctx.el.replaceChildren(
    h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Dashboard"), h("p", {}, `Welcome back, ${state.user.full_name}! Here's what's happening with your courier service.`)), h("div", { class: "clock" }, h("span", {}, icon("calendar", 18), dateEl), h("span", {}, icon("clock", 18), timeEl))),
    h("div", { class: "dash" }, h("div", { class: "col" }, h("div", { class: "stats" }, statCard("total_parcels", "Total Parcels", "box", "#3b6cff"), statCard("total_bookings", "Total Bookings", "calendar", "#10b981"), statCard("active_customers", "Active Customers", "user", "#8b3ff0"), statCard("active_riders", "Active Riders", "bike", "#f59e0b")),
      h("div", { class: "row2" }, chartCard, liveCard), h("div", { class: "row3" }, recent, provCard)), h("div", { class: "col side-col" }, quick, acts)));
};

function parcelsPage(kind) {
  return async (ctx) => {
    const st = { q: ctx.params.get("q") || "", status: ctx.params.get("status") || "", page: 1 }, size = 10, isBooking = kind === "bookings", box = h("div"), listEl = h("div");
    const qIn = h("input", { type: "search", class: "grow", placeholder: "Search tracking no., customer, recipient or city", value: st.q }), sSel = h("select", { "aria-label": "Status" }, opt("", "All statuses"), opt("active", "On the road"), Object.entries(STATUS).map(([k, l]) => opt(k, l, k === st.status)));
    if (st.status === "active") sSel.value = "active";
    async function load() {
      const qs = new URLSearchParams({ page: st.page, page_size: size }); if (st.q) qs.set("q", st.q); if (st.status) qs.set("status", st.status);
      const r = await api(`/admin/parcels?${qs}`); if (ctx.stale()) return;
      const view = { h: "Action", r: (p) => h("button", { class: "btn sm", onclick: () => openParcel(p.id, load) }, "View") }, trk = { h: "Tracking No.", r: (p) => h("span", { class: "mono", style: "color:var(--blue-2)" }, p.tracking_number) };
      const cols = isBooking ? [trk, { h: "Customer", r: (p) => p.customer_name }, { h: "Recipient", r: (p) => p.recipient_name }, { h: "Service", r: (p) => `${p.zone} · ${p.service.replace("_", " ")}` }, { h: "Route", r: (p) => `${p.pickup_city} → ${p.delivery_city}` }, { h: "Amount", r: (p) => h("span", { class: "num" }, money(p.price_total)) }, { h: "Booked", r: (p) => dLong(p.created_at) }, { h: "Status", r: (p) => pill(p.status) }, view]
        : [trk, { h: "Customer", r: (p) => p.customer_name }, { h: "From → To", r: (p) => `${p.pickup_city} → ${p.delivery_city}` }, { h: "Status", r: (p) => pill(p.status) }, { h: "Rider", r: (p) => p.rider?.name || "–" }, { h: "Provider", r: (p) => p.provider?.name || "–" }, { h: "ETA", r: (p) => etaLabel(p.eta) }, view];
      listEl.replaceChildren(table(cols, r.items, "No matching parcels."), pager(st.page, size, r.total, (n) => { st.page = n; load(); }));
    }
    const apply = debounce(() => { st.q = qIn.value.trim(); st.status = sSel.value; st.page = 1; load(); }); qIn.addEventListener("input", apply); sSel.addEventListener("change", apply);
    const exp = h("button", { class: "btn", onclick: async () => { exp.disabled = true; try { const qs = new URLSearchParams(); if (st.q) qs.set("q", st.q); if (st.status) qs.set("status", st.status); download(await api(`/admin/parcels/export.csv?${qs}`, { blob: true }), "zento-parcels.csv"); } catch (e) { toast(e.message, true); } exp.disabled = false; } }, icon("download", 16), "Export CSV");
    ctx.el.replaceChildren(pageHead(isBooking ? "Bookings" : "Parcels", isBooking ? "Every booking with its price and customer." : "Track, assign and update parcels.", exp, isBooking && h("button", { class: "btn primary", onclick: () => openBookingForm(load) }, icon("plus", 16), "Create Booking")),
      h("div", { class: "card" }, h("div", { class: "toolbar" }, qIn, sSel), listEl));
    await load();
  };
}
PAGES.parcels = parcelsPage("parcels"); PAGES.bookings = parcelsPage("bookings");

PAGES.customers = async (ctx) => {
  const st = { q: "", page: 1 }, size = 10, listEl = h("div"), qIn = h("input", { type: "search", class: "grow", placeholder: "Search by name, email or phone" });
  async function load() {
    const r = await api(`/admin/customers?page=${st.page}&page_size=${size}&q=${encodeURIComponent(st.q)}`); if (ctx.stale()) return;
    listEl.replaceChildren(table([{ h: "Name", r: (c) => c.full_name }, { h: "Email", r: (c) => c.email }, { h: "Phone", r: (c) => c.phone }, { h: "Parcels", r: (c) => c.parcels }, { h: "Total spent", r: (c) => h("span", { class: "num" }, money(c.total_spent)) },
      { h: "Joined", r: (c) => dShort(c.created_at.slice(0, 10)) }, { h: "Status", r: (c) => h("span", { class: `pill ${c.is_active ? "on" : "off"}` }, c.is_active ? "Active" : "Suspended") },
      { h: "Action", r: (c) => h("button", { class: "btn sm" + (c.is_active ? " danger" : ""), onclick: async () => { try { await api(`/admin/customers/${c.id}`, { method: "PATCH", body: { is_active: !c.is_active } }); toast(c.is_active ? "Customer suspended" : "Customer reactivated"); load(); } catch (e) { toast(e.message, true); } } }, c.is_active ? "Suspend" : "Activate") }], r.items, "No customers found."),
      pager(st.page, size, r.total, (n) => { st.page = n; load(); }));
  }
  qIn.addEventListener("input", debounce(() => { st.q = qIn.value.trim(); st.page = 1; load(); }));
  ctx.el.replaceChildren(pageHead("Customers", "People who have booked with ZENTO COURIER.", h("button", { class: "btn primary", onclick: () => openCustomerForm(load) }, icon("plus", 16), "Add Customer")), h("div", { class: "card" }, h("div", { class: "toolbar" }, qIn), listEl));
  await load();
};

function simpleList(title, sub, addLabel, endpoint, cols, openForm, noun) {
  return async (ctx) => {
    const listEl = h("div"), note = noun.note && h("p", { class: "muted", style: "margin:0 0 12px" }, noun.note);
    async function load() {
      const r = await api(`/admin/${endpoint}`); if (ctx.stale()) return;
      const rowActions = { h: "Actions", r: (x) => h("div", { class: "toolbar", style: "margin:0;flex-wrap:nowrap" }, h("button", { class: "btn sm", onclick: () => openForm(x, load) }, "Edit"),
        h("button", { class: "btn sm danger", onclick: async () => { if (!confirm(`Delete ${noun.name(x)}? This cannot be undone.`)) return; try { await api(`/admin/${endpoint}/${x.id}`, { method: "DELETE" }); toast("Deleted"); load(); } catch (e) { toast(e.message, true); } } }, "Delete")) };
      listEl.replaceChildren(table([...cols, { h: "Status", r: (x) => h("span", { class: `pill ${x.is_active ? "on" : "off"}` }, x.is_active ? "Active" : "Inactive") }, rowActions], r.items, noun.empty));
    }
    ctx.el.replaceChildren(pageHead(title, sub, h("button", { class: "btn primary", onclick: () => openForm(null, load) }, icon("plus", 16), addLabel)), h("div", { class: "card" }, note, listEl));
    await load();
  };
}
PAGES.riders = simpleList("Riders", "Delivery riders and their workload.", "Add Rider", "riders", [{ h: "Name", r: (r) => r.full_name }, { h: "Phone", r: (r) => r.phone }, { h: "Vehicle", r: (r) => r.vehicle }, { h: "City", r: (r) => r.city || "–" }, { h: "Open jobs", r: (r) => r.active_deliveries }, { h: "Delivered", r: (r) => r.delivered }], openRiderForm, { name: (x) => x.full_name, empty: "No riders yet. Add your first rider." });
PAGES.providers = simpleList("Courier Providers", "Partner couriers you hand parcels to.", "Add Provider", "providers", [{ h: "Provider", r: (p) => h("span", { style: "display:inline-flex;align-items:center;gap:10px" }, h("span", { class: "logo-tile", style: `width:32px;height:32px;font-size:13px;background:${hue(p.name)}` }, initials(p.name)), p.name) }, { h: "Phone", r: (p) => p.phone || "–" },
  { h: "Website", r: (p) => (p.website && /^https?:\/\//.test(p.website) ? h("a", { href: p.website, target: "_blank", rel: "noopener noreferrer" }, p.website.replace(/^https?:\/\//, "")) : "–") }, { h: "Parcels", r: (p) => p.parcels }], openProviderForm, { name: (x) => x.name, empty: "No courier providers yet." });
PAGES.areas = simpleList("Service Areas", "Cities where ZENTO COURIER delivers.", "Add Area", "areas", [{ h: "City", r: (a) => a.city }, { h: "Region", r: (a) => a.region || "–" }, { h: "Parcels delivered to", r: (a) => a.parcels }], openAreaForm,
  { name: (x) => x.city, empty: "No service areas yet.", note: "This list is for your team's reference. Booking does not yet block cities that are not listed here." });

PAGES.pricing = async (ctx) => {
  const p = await api("/admin/pricing"); if (ctx.stale()) return; const cur = p.currency, errs = {}, box = FORM_BOX(), out = h("div", { class: "form-ok", hidden: true });
  const zone = h("select", {}, ZONES.map(([k, l]) => opt(k, l))), service = h("select", {}, SERVICES.map(([k, l]) => opt(k, l))), w = h("input", { type: "number", step: "0.5", min: "0.1", value: "1" }), dv = h("input", { type: "number", min: "0", value: "0" }), fr = h("input", { type: "checkbox" }), btn = h("button", { class: "btn primary", type: "submit" }, "Calculate");
  const calc = h("form", { class: "form", onsubmit: (e) => { e.preventDefault(); run(btn, box, errs, async () => {
    const q = await api("/pricing/quote", { method: "POST", auth: false, body: { zone: zone.value, service: service.value, weight_kg: w.value, declared_value: dv.value || "0", fragile: fr.checked } });
    out.hidden = false; out.replaceChildren(...q.lines.map((l) => h("div", {}, `${l.label}: ${money(l.amount, cur)}`)), h("b", {}, `Total ${money(q.total, cur)}`));
  }); } }, box, h("div", { class: "two" }, fld("Zone", zone), fld("Service", service)), h("div", { class: "two" }, fld("Weight (kg)", w), fld("Declared value", dv)), h("label", { class: "check" }, fr, "Fragile"), out, h("div", { class: "actions" }, btn));
  const zl = Object.fromEntries(p.zones.map((z) => [z.id, z.label])), sl = Object.fromEntries(p.services.map((x) => [x.id, x.label]));
  ctx.el.replaceChildren(pageHead("Delivery Pricing", "Current rates used for every booking."),
    h("div", { class: "card", style: "margin-bottom:16px" }, h("p", { class: "muted", style: "margin:0" }, "Rates are defined in app/pricing.py on the server, so they are shown here read-only. Change them there (and update the tests), then redeploy.")),
    h("div", { class: "cards-3" }, p.zones.map((z) => h("div", { class: "card" }, h("span", { class: "muted" }, `${z.label} · ${z.description}`), h("b", { class: "big num" }, money(z.base, cur)), h("span", { class: "muted" }, `first ${p.included_kg} kg, then ${money(z.per_kg, cur)} per kg`))),
      p.services.map((x) => h("div", { class: "card" }, h("span", { class: "muted" }, `${x.label} · ${x.description}`), h("b", { class: "big num" }, `×${x.multiplier}`), h("span", { class: "muted" }, "applied to base and weight charges"))),
      h("div", { class: "card" }, h("span", { class: "muted" }, "Extras"), h("div", { style: "margin-top:6px" }, `Fragile handling: ${money(p.fees.fragile, cur)}`), h("div", {}, `Insurance: ${Number(p.fees.insurance_rate) * 100}% of declared value (min ${money(p.fees.insurance_min, cur)})`), h("div", { class: "muted" }, `Max ${p.limits.max_weight_kg} kg · ${p.limits.max_dimension_cm} cm per side · value ${money(p.limits.max_declared_value, cur)}`))),
    h("div", { class: "row2", style: "grid-template-columns:1fr 1fr" }, h("section", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "Delivery times"), table([{ h: "Zone", r: (e) => zl[e.zone] }, { h: "Service", r: (e) => sl[e.service] }, { h: "Days", r: (e) => (e.max_days === 0 ? "Same day" : e.min_days === e.max_days ? e.min_days : `${e.min_days}–${e.max_days}`) }], p.eta)),
      h("section", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "Price calculator"), calc)));
};

PAGES.reports = async (ctx) => {
  const days = Number(ctx.params.get("days")) || 30, r = await api(`/admin/reports?days=${days}`); if (ctx.stale()) return; const cur = r.currency, labels = r.daily.map((x) => dShort(x.date));
  const sel = h("select", { "aria-label": "Range", onchange: () => { location.hash = `#/reports?days=${sel.value}`; } }, [7, 30, 90].map((n) => opt(n, `Last ${n} days`, n === days)));
  const exp = h("button", { class: "btn", onclick: () => download(new Blob([["Date,Parcels,Delivered,Revenue", ...r.daily.map((x) => `${x.date},${x.parcels},${x.delivered},${x.revenue}`)].join("\n")], { type: "text/csv" }), `zento-report-${days}d.csv`) }, icon("download", 16), "Export CSV");
  const stat = (l, v) => h("div", { class: "card" }, h("span", { class: "muted" }, l), h("b", { class: "big num" }, v)), brk = (title, rows) => h("section", { class: "card" }, h("h2", { style: "margin-bottom:10px" }, title), table([{ h: "Name", r: (x) => x.name }, { h: "Parcels", r: (x) => x.parcels }, { h: "Revenue", r: (x) => money(x.revenue, cur) }], rows, "No data in this range."));
  ctx.el.replaceChildren(pageHead("Reports", "Performance for the selected period.", sel, exp),
    h("div", { class: "cards-3" }, stat("Parcels booked", r.totals.parcels), stat("Revenue (excl. cancelled)", money(r.totals.revenue, cur)), stat("Delivered", r.totals.delivered), stat("Delivery rate", `${r.totals.delivery_rate}%`), stat("Cancelled", r.totals.cancelled)),
    h("div", { class: "card", style: "margin-bottom:16px" }, h("h2", { style: "margin-bottom:10px" }, "Parcels per day"), barChart(labels, r.daily.map((x) => x.parcels), "#3b82f6")),
    h("div", { class: "card", style: "margin-bottom:16px" }, h("h2", { style: "margin-bottom:10px" }, `Revenue per day (${cur})`), barChart(labels, r.daily.map((x) => Number(x.revenue)), "#14c38e", (v) => Math.round(v))),
    h("div", { class: "cards-3" }, brk("By zone", r.by_zone.map((x) => ({ ...x, name: x.name }))), brk("By service", r.by_service.map((x) => ({ ...x, name: x.name.replace("_", " ") }))),
      h("section", { class: "card" }, h("h2", { style: "margin-bottom:10px" }, "By status"), table([{ h: "Status", r: (x) => pill(x[0]) }, { h: "Parcels", r: (x) => x[1] }], Object.entries(r.by_status), "No data in this range."))));
};

PAGES.notifications = async (ctx) => {
  const { items } = await api("/admin/notifications"); if (ctx.stale()) return;
  const seen = Number(localStorage.getItem(SEEN_KEY) || 0), ic = { booking: "calendar", delivered: "check", rider: "bike", customer: "user", status: "clock" };
  try { localStorage.setItem(SEEN_KEY, String(Date.now())); } catch { /* storage blocked */ }
  state.unread = 0; updateBadges();
  ctx.el.replaceChildren(pageHead("Notifications", "Latest bookings, sign-ups and staff actions."), h("div", { class: "card" }, items.length ? h("div", { class: "acts" }, items.map((a) => h("div", { class: "act" }, h("div", { class: `ai ${a.kind}` }, icon(ic[a.kind] || "clock", 18)),
    h("div", {}, h("b", {}, a.title, new Date(a.created_at).getTime() > seen && h("span", { class: "pill on", style: "margin-left:8px" }, "New")), h("small", {}, h("span", {}, a.detail || ""), h("span", {}, ago(a.created_at))))))) : h("div", { class: "empty" }, "No notifications yet.")));
};

PAGES.settings = async (ctx) => {
  const u = state.user, errs = {}, box = FORM_BOX(), ok = h("div", { class: "form-ok", hidden: true }), cur = h("input", { type: "password", autocomplete: "current-password" }), nw = h("input", { type: "password", autocomplete: "new-password" }), btn = h("button", { class: "btn primary", type: "submit" }, "Change password");
  const form = h("form", { class: "form", onsubmit: (e) => { e.preventDefault(); ok.hidden = true; run(btn, box, errs, async () => { await api("/admin/change-password", { method: "POST", body: { current_password: cur.value, new_password: nw.value } }); cur.value = nw.value = ""; ok.hidden = false; ok.textContent = "Password updated."; }); } },
    box, ok, fld("Current password", cur, errs, "current_password"), fld("New password", nw, errs, "new_password"), h("div", { class: "actions" }, btn));
  ctx.el.replaceChildren(pageHead("Settings", "Your admin account."), h("div", { class: "row2", style: "grid-template-columns:1fr 1fr" },
    h("section", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "Profile"), h("div", { class: "kv" }, h("div", {}, h("small", {}, "Name"), h("span", {}, u.full_name)), h("div", {}, h("small", {}, "Email"), h("span", {}, u.email)), h("div", {}, h("small", {}, "Phone"), h("span", {}, u.phone)), h("div", {}, h("small", {}, "Role"), h("span", {}, "Admin"))),
      h("button", { class: "btn danger", onclick: logout }, icon("logout", 16), "Sign out")), h("section", { class: "card" }, h("h2", { style: "margin-bottom:12px" }, "Change password"), form)));
};

/* ---------- boot ---------- */
let pollTimer;
function start() { shell(); if (!location.hash) location.hash = "#/dashboard"; route(); pollNotifications(); clearInterval(pollTimer); pollTimer = setInterval(pollNotifications, 60000); }
(async () => {
  if (!getToken()) return renderLogin();
  try { const u = await api("/auth/me"); if (!u.is_admin) { setToken(null); return renderLogin("This account does not have admin access."); } state.user = u; start(); }
  catch (e) { if (!state.user) renderLogin(e.status === 401 ? "" : e.message); }
})();
