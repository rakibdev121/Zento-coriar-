// ZENTO COURIER rider app. Vanilla ES module, no build step. All server data is rendered through textContent / DOM nodes (never innerHTML).
const TOKEN_KEY = "zento.rider.token";
const $app = document.getElementById("app");
const state = { me: null, dash: null, tab: "home", orders: "requests", currency: "BDT", rate: 20, photo: null, timer: null, rid: 0 };

/* ---------- DOM + icons ---------- */
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
const NS = "http://www.w3.org/2000/svg";
const PATHS = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10", box: "M21 8l-9-5-9 5v8l9 5 9-5V8zM3 8l9 5 9-5M12 13v8",
  bike: "M5.5 18a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM18.5 18a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM12 18l-3-7h6l3 7M9 11l-1-3H6",
  wallet: "M3 7a2 2 0 012-2h12v4M3 7v11a2 2 0 002 2h14a1 1 0 001-1v-9a1 1 0 00-1-1H5a2 2 0 01-2-2zM16 14.5h.01", user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  pin: "M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11zM12 12a2.5 2.5 0 100-5 2.5 2.5 0 000 5z", phone: "M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z",
  chart: "M4 20V10M10 20V4M16 20v-8M22 20H2", flame: "M12 3c1 4 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z",
  right: "M9 6l6 6-6 6", logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9", check: "M5 12l5 5L20 7", clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
};
const icon = (n, cls = "") => { const s = document.createElementNS(NS, "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", "ic " + cls); s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path"); p.setAttribute("d", PATHS[n]); s.append(p); return s; };

/* ---------- formatting ---------- */
/** Money is always shown in taka: \u09F3 1,234.50 */
function money(v) {
  const n = Number(v) || 0;
  return "\u09F3" + n.toLocaleString("en-US", { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 });
}
const initials = (n) => (n || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
const STATUS = { booked: "Go to pickup", picked_up: "Picked up", in_transit: "In transit", out_for_delivery: "Out for delivery", delivered: "Delivered", cancelled: "Cancelled" };
function pill(p) {
  if (p.rider_response === "pending" && !["delivered", "cancelled"].includes(p.status)) return h("span", { class: "pill new" }, "New request");
  return h("span", { class: "pill" + (p.status === "delivered" ? " good" : p.status === "cancelled" ? " bad" : "") }, STATUS[p.status] || p.status);
}
function greeting() { const hr = new Date().getHours(); return hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening"; }
const fmtWhen = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "");

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
  if (res.ok) return blob ? res.blob() : res.json();
  let data = null; try { data = await res.json(); } catch { /* no body */ }
  if (res.status === 401 && auth && getToken()) { setToken(null); stop(); renderAuth("Your session has expired. Sign in again."); }
  throw new ApiError(typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.", res.status, Array.isArray(data?.errors) ? data.errors : []);
}
const stop = () => { clearInterval(state.timer); state.timer = null; };
function signOut(message) { setToken(null); stop(); if (state.photo) URL.revokeObjectURL(state.photo); Object.assign(state, { me: null, dash: null, photo: null, tab: "home" }); renderAuth(message); }

/* ---------- small UI helpers ---------- */
function toast(msg, bad = false) {
  document.querySelector(".toast")?.remove();
  const t = h("div", { class: "toast" + (bad ? " bad" : ""), role: "status" }, msg); document.body.append(t); setTimeout(() => t.remove(), 3500);
}
function setBusy(btn, busy, label = "Working\u2026") {
  if (busy) { btn.dataset.label = btn.textContent; btn.textContent = label; btn.disabled = true; } else { btn.textContent = btn.dataset.label || btn.textContent; btn.disabled = false; }
}
function fld(label, input, errs, name, hint) {
  const slot = h("div", { class: "err", role: "alert" }); if (errs && name) errs[name] = slot;
  return h("div", { class: "field" }, h("label", {}, label), input, hint && h("div", { class: "hint" }, hint), slot);
}
function showErrors(banner, errs, e) {
  Object.values(errs).forEach((s) => (s.textContent = ""));
  const rest = [];
  for (const fe of e.fieldErrors || []) { const slot = errs[(fe.field || "").split(".")[0]]; if (slot) slot.textContent = fe.message; else rest.push(fe.message); }
  banner.textContent = e.fieldErrors?.length ? (rest.join(" ") || "Fix the highlighted fields and try again.") : e.message; banner.hidden = false;
}
function fileToDataUrl(file, max = 1000) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.width * k)); c.height = Math.max(1, Math.round(img.height * k));
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url); resolve(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file is not an image we can read.")); };
    img.src = url;
  });
}
function imagePicker(capture) {
  const thumb = h("div", { class: "thumb" }, icon("user")), state_ = { value: "" };
  const input = h("input", { type: "file", accept: "image/*", capture: capture || null, onchange: async () => {
    const f = input.files?.[0]; if (!f) return;
    try { state_.value = await fileToDataUrl(f); const im = h("img", { alt: "Preview", src: state_.value }); thumb.replaceChildren(im); }
    catch (e) { state_.value = ""; toast(e.message, true); }
  } });
  return { node: h("div", { class: "pick" }, thumb, input), get value() { return state_.value; } };
}

/* ---------- auth screens ---------- */
function renderAuth(message, mode = "signin") {
  stop();
  const brand = h("div", {}, h("h1", { class: "brand" }, "ZENTO", h("small", {}, "Rider")), h("p", { class: "muted", style: "margin:0 0 16px" }, "Deliver parcels. Earn commission on every delivery."));
  const seg = h("div", { class: "seg" }, h("button", { class: mode === "signin" ? "on" : "", onclick: () => renderAuth(null, "signin") }, "Sign in"), h("button", { class: mode === "apply" ? "on" : "", onclick: () => renderAuth(null, "apply") }, "Apply as rider"));
  const banner = h("div", { class: "banner", role: "alert", hidden: !message }, message || ""), errs = {};
  const body = mode === "signin" ? signInForm(banner, errs) : applyForm(banner, errs);
  $app.replaceChildren(h("div", { class: "auth" }, brand, seg, banner, body));
}
function signInForm(banner, errs) {
  const email = h("input", { type: "email", autocomplete: "email", required: true }), pass = h("input", { type: "password", autocomplete: "current-password", required: true });
  const btn = h("button", { class: "btn", type: "submit" }, "Sign in");
  return h("form", { onsubmit: async (e) => {
    e.preventDefault(); banner.hidden = true; setBusy(btn, true, "Signing in\u2026");
    try { const r = await api("/auth/login", { method: "POST", auth: false, body: { email: email.value.trim(), password: pass.value } }); setToken(r.access_token); await boot(); }
    catch (err) { showErrors(banner, errs, err); setBusy(btn, false); }
  } }, fld("Email", email, errs, "email"), fld("Password", pass, errs, "password"), btn);
}
function applyForm(banner, errs) {
  const v = { full_name: h("input", { autocomplete: "name", required: true }), phone: h("input", { type: "tel", autocomplete: "tel", required: true, placeholder: "+8801XXXXXXXXX" }),
    city: h("input", { required: true }), vehicle: h("select", {}, ["bike", "bicycle", "scooter", "van", "truck"].map((x) => h("option", { value: x }, x[0].toUpperCase() + x.slice(1)))),
    id_type: h("select", {}, h("option", { value: "nid" }, "National ID (NID)"), h("option", { value: "passport" }, "Passport")), id_number: h("input", { required: true, autocomplete: "off" }),
    email: h("input", { type: "email", autocomplete: "email", required: true }), password: h("input", { type: "password", autocomplete: "new-password", required: true, minlength: "8" }) };
  const photo = imagePicker("user"), idDoc = imagePicker(), btn = h("button", { class: "btn", type: "submit" }, "Submit application");
  return h("form", { onsubmit: async (e) => {
    e.preventDefault(); banner.hidden = true;
    if (!photo.value || !idDoc.value) { errs.photo.textContent = photo.value ? "" : "Add your photo."; errs.id_document.textContent = idDoc.value ? "" : "Add a photo of your NID or passport."; return; }
    setBusy(btn, true, "Submitting\u2026");
    try {
      const body = Object.fromEntries(Object.entries(v).map(([k, el]) => [k, k === "password" ? el.value : el.value.trim()])); body.photo = photo.value; body.id_document = idDoc.value;
      const r = await api("/rider/apply", { method: "POST", auth: false, body }); setToken(r.access_token); await boot();
    } catch (err) { showErrors(banner, errs, err); setBusy(btn, false); }
  } }, fld("Full name", v.full_name, errs, "full_name"), fld("Phone", v.phone, errs, "phone"),
  h("div", { class: "two" }, fld("City", v.city, errs, "city"), fld("Vehicle", v.vehicle, errs, "vehicle")),
  fld("Your photo", photo.node, errs, "photo", "A clear photo of your face."),
  h("div", { class: "two" }, fld("ID type", v.id_type, errs, "id_type"), fld("ID number", v.id_number, errs, "id_number")),
  fld("NID / passport photo", idDoc.node, errs, "id_document", "The page with your name and number."),
  fld("Email", v.email, errs, "email"), fld("Password", v.password, errs, "password", "8+ characters with letters and numbers."), btn);
}
function renderGate() {
  const m = state.me, rejected = m.status === "rejected", off = m.status === "approved" && !m.is_active;
  const msg = rejected ? "Your application was not approved." : off ? "Your rider account is switched off. Contact ZENTO COURIER." : "Your application is with our team. You can start delivering as soon as it is approved.";
  $app.replaceChildren(h("div", { class: "auth" }, h("h1", { class: "brand" }, "ZENTO", h("small", {}, "Rider")),
    h("div", { class: "card", style: "margin-top:18px;text-align:center" }, h("div", { class: "badge-ic", style: "margin:0 auto 12px" }, icon(rejected ? "clock" : "check")),
      h("h2", { style: "margin:0 0 6px" }, rejected ? "Not approved" : off ? "Account off" : "Application under review"), h("p", { class: "muted" }, msg),
      rejected && m.reject_reason ? h("p", {}, `Reason: ${m.reject_reason}`) : null,
      h("div", { class: "kv", style: "text-align:left;margin:14px 0" }, h("div", {}, h("span", {}, "Name"), h("span", {}, m.full_name)), h("div", {}, h("span", {}, "Phone"), h("span", {}, m.phone)), h("div", {}, h("span", {}, "Email"), h("span", {}, m.email || "\u2013"))),
      h("div", { class: "two" }, h("button", { class: "btn sm", onclick: () => boot() }, "Check status"), h("button", { class: "btn sm ghost", onclick: () => signOut() }, "Sign out")))));
}

/* ---------- boot ---------- */
async function boot(message) {
  if (!getToken()) return renderAuth(message);
  try { state.me = await api("/rider/me"); }
  catch (e) { if (e.status === 401) return; if (e.status === 403) return signOut(e.message); return $app.replaceChildren(h("div", { class: "auth" }, h("div", { class: "banner" }, e.message), h("button", { class: "btn", onclick: () => boot() }, "Try again"))); }
  if (state.me.status !== "approved" || !state.me.is_active) return renderGate();
  if (!state.photo) { try { state.photo = URL.createObjectURL(await api("/rider/photo", { blob: true })); } catch { /* initials are shown instead */ } }
  renderApp();
}

/* ---------- app shell ---------- */
const avatar = (cls = "") => (state.photo ? h("img", { class: `avatar ${cls}`, src: state.photo, alt: "" }) : h("div", { class: `avatar ${cls}` }, initials(state.me.full_name)));
function renderApp() {
  const view = h("div", { class: "view" }); state.view = view;
  const tabBtn = (id, label, ic, cls = "") => h("button", { class: `${cls} ${state.tab === id ? "on" : ""}`.trim(), "data-tab": id, onclick: () => (id === "go" ? go() : show(id)) },
    id === "go" ? h("span", { class: "disc" }, icon(ic)) : icon(ic), label);
  $app.replaceChildren(h("div", { class: "app" }, view), h("div", { class: "nav" }, h("nav", { "aria-label": "Main" }, tabBtn("home", "Home", "home"), tabBtn("orders", "Orders", "box"), tabBtn("go", "Go", "bike", "go"), tabBtn("earnings", "Wallet", "wallet"), tabBtn("profile", "Profile", "user"))));
  show(state.tab);
  stop(); state.timer = setInterval(() => { if (!document.hidden && !document.querySelector(".sheet-ov") && ["home", "orders"].includes(state.tab)) show(state.tab, true); }, 30000);
}
function go() { if (state.dash?.active?.length) openSheet(state.dash.active[0]); else { state.orders = "requests"; show("orders"); } }
const VIEWS = { home: homeView, orders: ordersView, earnings: earningsView, profile: profileView };
async function show(tab, silent = false) {
  state.tab = tab; const rid = ++state.rid;
  document.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  if (!silent) state.view.replaceChildren(h("div", { class: "skel" }), h("div", { class: "skel" }));
  try { const node = await VIEWS[tab](); if (rid === state.rid) state.view.replaceChildren(...node); }
  catch (e) { if (rid === state.rid && e.status !== 401) { if (e.status === 403) return boot(); if (!silent) state.view.replaceChildren(h("div", { class: "banner" }, e.message), h("button", { class: "btn ghost", onclick: () => show(tab) }, "Try again")); } }
}
const refresh = () => show(state.tab, true);

/* ---------- parcel helpers ---------- */
const nextAction = (p) => (p.rider_response === "pending" ? null : ({ booked: { label: "Confirm Pickup", status: "picked_up" }, picked_up: { label: "Start Delivery", status: "out_for_delivery" },
  in_transit: { label: "Start Delivery", status: "out_for_delivery" }, out_for_delivery: { label: "Mark Delivered", status: "delivered" } })[p.status] || null);
async function advance(p, btn) {
  const a = nextAction(p); if (!a) return;
  if (a.status === "delivered" && !confirm(`Mark ${p.tracking_number} as delivered?`)) return;
  setBusy(btn, true);
  try { const r = await api(`/rider/parcels/${p.id}/status`, { method: "POST", body: { status: a.status } }); closeSheet(); toast(a.status === "delivered" ? `Delivered! You earned ${money(r.commission)}` : "Status updated"); refresh(); }
  catch (e) { toast(e.message, true); setBusy(btn, false); }
}
async function respond(p, action, btn) {
  let reason = null;
  if (action === "reject") { reason = prompt("Why are you rejecting this parcel? (optional)"); if (reason === null) return; }
  setBusy(btn, true);
  try { await api(`/rider/parcels/${p.id}/respond`, { method: "POST", body: { action, reason: reason || null } }); closeSheet(); toast(action === "accept" ? "Parcel accepted" : "Parcel rejected"); refresh(); }
  catch (e) { toast(e.message, true); setBusy(btn, false); }
}
const stop_ = (ic, title, line, city) => h("div", { class: "stop" }, h("div", { class: "badge-ic" + (ic === "pin" ? " dark" : "") }, icon(ic)), h("div", {}, h("b", {}, title), h("span", {}, line), h("small", {}, city)));
const phoneLink = (n) => h("a", { href: `tel:${String(n).replace(/[^\d+]/g, "")}` }, n);

/* ---------- bottom sheet ---------- */
function closeSheet() { document.querySelector(".sheet-ov")?.remove(); }
function openSheet(p) {
  closeSheet();
  const open = !["delivered", "cancelled"].includes(p.status), a = nextAction(p), c = p.contact;
  const kv = (k, v) => h("div", {}, h("span", {}, k), h("span", {}, v));
  const actions = h("div", { class: "actions" });
  if (open && p.rider_response === "pending") {
    const acc = h("button", { class: "btn", onclick: () => respond(p, "accept", acc) }, "Accept parcel"), rej = h("button", { class: "btn danger", onclick: () => respond(p, "reject", rej) }, "Reject");
    actions.append(acc, rej);
  } else if (open && a) { const b = h("button", { class: "btn", onclick: () => advance(p, b) }, a.label); actions.append(b); }
  const ov = h("div", { class: "sheet-ov", onclick: (e) => { if (e.target === ov) closeSheet(); } }, h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": `Parcel ${p.tracking_number}` },
    h("div", { class: "grab" }), h("div", { class: "row", style: "justify-content:space-between" }, h("h2", { class: "mono" }, p.tracking_number), pill(p)),
    h("div", { class: "route" }, stop_("box", "Pickup", p.pickup_address, p.pickup_city), stop_("pin", "Drop", p.delivery_address, p.delivery_city)),
    h("div", { class: "kv" }, kv("Service", `${p.zone} \u00B7 ${p.service.replace("_", " ")}`), kv("Weight", `${Number(p.weight_kg)} kg`), p.fragile && kv("Handling", "Fragile"), p.description && kv("Contents", p.description),
      kv("Parcel value", money(p.price_total)), Number(p.cod_amount) > 0 && kv("Collect cash (COD)", h("b", { style: "color:#ff8a1f" }, money(p.cod_amount))), kv(`Your commission (${state.rate}%)`, money(p.commission)),
      c && kv("Sender", h("span", {}, c.sender_name, " \u00B7 ", phoneLink(c.sender_phone))), c && kv("Recipient", h("span", {}, c.recipient_name, " \u00B7 ", phoneLink(c.recipient_phone))),
      !c && open && kv("Contacts", "Shown after you accept"), p.delivered_at && kv("Delivered", fmtWhen(p.delivered_at))),
    actions, h("div", { class: "actions" }, h("button", { class: "btn ghost", onclick: closeSheet }, "Close"))));
  document.body.append(ov);
}

/* ---------- views ---------- */
async function homeView() {
  const d = await api("/rider/dashboard"); state.dash = d; state.currency = d.currency; state.rate = d.rate_percent;
  const first = state.me.full_name.split(" ")[0], act = d.active[0];
  const wallet = h("div", { class: "card wallet" }, icon("wallet", "deco"), h("div", { class: "lbl" }, icon("wallet"), "My Wallet"), h("div", { class: "small" }, "Wallet balance"), h("div", { class: "amt num" }, money(d.wallet.balance)),
    h("div", { class: "note" }, Number(d.wallet.cod_due) > 0 ? `COD cash to hand in: ${money(d.wallet.cod_due)}. You can withdraw ${money(d.wallet.withdrawable)}` : `You earn ${d.rate_percent}% of every delivered parcel`));
  const goal = h("div", { class: "card" }, h("div", { class: "row" }, h("div", { class: "badge-ic" }, icon("chart")), h("div", {}, h("div", { class: "muted" }, "Today's Earnings"), h("div", { class: "big num" }, money(d.today), " ", h("small", {}, `/ ${money(d.goal)}`))),
    h("div", { class: "goal" }, `${d.goal_percent}%`, h("small", {}, "Goal"))),
    h("div", { class: "bar" }, h("i", { style: `width:${d.goal_percent}%` }), h("b", { style: `left:${d.goal_percent}%` })),
    h("div", { class: "sub" }, h("span", {}, d.goal_percent >= 100 ? "Goal reached. Great work!" : "Keep going! You're doing great."), d.streak ? h("span", { class: "streak" }, icon("flame"), `${d.streak} day streak`) : h("span", {}, "Deliver today to start a streak")));
  const active = act ? h("div", { class: "card active" }, h("div", { class: "kicker" }, h("span", { class: "streak" }, icon("flame"), "Active order"), pill(act)),
    h("p", { class: "tn mono" }, act.tracking_number), h("div", { class: "route" }, stop_("box", "Pickup location", act.pickup_address, act.pickup_city), stop_("pin", "Drop location", act.delivery_address, act.delivery_city)),
    (() => { const a = nextAction(act), b = h("button", { class: "btn", onclick: () => advance(act, b) }, a?.label || "View details"); if (!a) b.onclick = () => openSheet(act); return b; })(),
    h("div", { class: "sub", style: "margin-top:10px" }, h("button", { class: "btn sm ghost", onclick: () => openSheet(act) }, "Details"), d.active.length > 1 ? h("button", { class: "btn sm ghost", onclick: () => { state.orders = "active"; show("orders"); } }, `+${d.active.length - 1} more active`) : h("span", {}, `Commission ${money(act.commission)}`)))
    : h("div", { class: "card empty" }, h("b", {}, "No active order"), h("div", {}, d.requests.length ? "Accept a request below to get started." : "New parcels will appear here when admin assigns them to you."));
  const reqs = d.requests.length ? h("div", { class: "card list" }, d.requests.slice(0, 4).map((p) => h("button", { class: "item", onclick: () => openSheet(p) }, h("div", { class: "badge-ic" }, icon("box")),
    h("div", { class: "grow" }, h("b", { class: "mono" }, p.tracking_number), h("small", {}, `${p.pickup_city} \u2192 ${p.delivery_city}`)), h("div", { class: "amt-sm num" }, money(p.commission), h("small", {}, "you earn")), icon("right")))) : null;
  return [h("div", { class: "top" }, avatar(), h("div", {}, h("div", { class: "hello" }, `${greeting()}, ${first}!`), h("h1", { class: "title" }, "Let's Deliver")), h("div", { class: "chip" }, icon("pin"), state.me.city || "Rider")),
    wallet, goal, active, h("div", { class: "section" }, h("span", {}, `New Requests${d.requests.length ? ` (${d.requests.length})` : ""}`), d.requests.length ? h("button", { onclick: () => { state.orders = "requests"; show("orders"); } }, "View All", icon("right")) : null), reqs || h("div", { class: "card empty" }, "No new requests right now.")].filter(Boolean);
}
async function ordersView() {
  const tabs = [["requests", "Requests"], ["active", "Active"], ["history", "History"]];
  const r = await api(`/rider/parcels?tab=${state.orders}`);
  const seg = h("div", { class: "seg" }, tabs.map(([k, l]) => h("button", { class: state.orders === k ? "on" : "", onclick: () => { state.orders = k; show("orders"); } }, l)));
  const empty = { requests: "No new requests.", active: "No active deliveries.", history: "No finished deliveries yet." }[state.orders];
  const list = r.items.length ? h("div", { class: "card list" }, r.items.map((p) => h("button", { class: "item", onclick: () => openSheet(p) }, h("div", { class: "badge-ic" }, icon("box")),
    h("div", { class: "grow" }, h("b", { class: "mono" }, p.tracking_number), h("small", {}, `${p.pickup_city} \u2192 ${p.delivery_city}`), h("div", { style: "margin-top:6px" }, pill(p), Number(p.cod_amount) > 0 ? h("span", { class: "pill cod" }, `COD ${money(p.cod_amount)}`) : null)), h("div", { class: "amt-sm num" }, money(p.commission), h("small", {}, p.status === "delivered" ? "earned" : "you earn"))))) : h("div", { class: "card empty" }, empty);
  return [h("h1", { class: "title", style: "margin-bottom:12px" }, "Orders"), seg, list];
}
/* ---------- wallet: withdraw and COD hand-in ---------- */
const METHODS = { bkash: "bKash", nagad: "Nagad", rocket: "Rocket", bank: "Bank", cash: "Cash (office)" };
const KINDS = { deposit: "Deposit", booking: "Booking", refund: "Refund", cod: "COD received", commission: "Commission", withdrawal: "Withdrawal", withdrawal_refund: "Withdrawal returned", adjustment: "Adjustment" };
function openMoneySheet(kind, w) {
  closeSheet();
  const handIn = kind === "cod_deposit", errs = {}, banner = h("div", { class: "form-err", hidden: true });
  const amount = h("input", { type: "number", inputmode: "decimal", step: "0.01", min: "1", value: handIn ? Math.max(0, Number(w.cod_due) - Number(w.pending_cod_deposit)) || "" : "" });
  const method = h("select", {}, (handIn ? ["cash", "bkash", "nagad", "rocket", "bank"] : ["bkash", "nagad", "rocket", "bank"]).map((k) => h("option", { value: k }, METHODS[k])));
  const account = h("input", { placeholder: handIn ? "office (for cash) or your bKash/Nagad number" : "01XXXXXXXXX", value: handIn ? "office" : "", maxlength: "40" });
  const reference = h("input", { placeholder: "Transaction ID (not needed for cash)", maxlength: "60" });
  method.addEventListener("change", () => { if (handIn) account.value = method.value === "cash" ? "office" : ""; });
  const go = h("button", { class: "btn", type: "submit" }, handIn ? "Send hand-in request" : "Request withdrawal");
  const ov = h("div", { class: "sheet-ov", onclick: (e) => { if (e.target === ov) closeSheet(); } }, h("form", { class: "sheet", novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); banner.hidden = true; setBusy(go, true, "Sending\u2026");
    try {
      await api(handIn ? "/wallet/cod-deposit" : "/wallet/withdraw", { method: "POST", body: { amount: amount.value, method: method.value, account: account.value, reference: reference.value || null } });
      closeSheet(); toast(handIn ? "Sent. Your limit opens when the admin accepts the cash." : "Withdrawal requested. It is on hold until paid."); refresh();
    } catch (err) { showErrors(banner, errs, err); setBusy(go, false); }
  } }, h("div", { class: "grab" }), h("h2", {}, handIn ? "Hand in COD cash" : "Withdraw money"),
    h("p", { class: "muted" }, handIn ? `You owe ${money(w.cod_due)} of customers' COD money. Give it to the ZENTO office or send it by bKash/Nagad, then report it here.` : `You can withdraw up to ${money(w.withdrawable)}.`),
    banner, fld("Amount (\u09F3)", amount, errs, "amount"), fld(handIn ? "How did you hand it in?" : "Send my money to", method, errs, "method"),
    fld(handIn ? "Account" : "My bKash / Nagad / Rocket number or bank account", account, errs, "account"), fld("Transaction ID", reference, errs, "reference"),
    h("div", { class: "actions" }, go, h("button", { class: "btn ghost", type: "button", onclick: closeSheet }, "Close"))));
  document.body.append(ov);
}

async function earningsView() {
  const [e, w] = await Promise.all([api("/rider/earnings"), api("/wallet")]); state.currency = e.currency; state.rate = e.rate_percent;
  const due = Number(w.cod_due) > 0;
  const walletCard = h("div", { class: "card wallet" }, icon("wallet", "deco"), h("div", { class: "lbl" }, icon("wallet"), "My Wallet"), h("div", { class: "amt num" }, money(w.balance)),
    h("div", { class: "note" }, `Withdrawable now: ${money(w.withdrawable)}`));
  const lockNote = due ? h("div", { class: "card warn" }, h("b", {}, `Hand in ${money(w.cod_due)} COD cash first`),
    h("div", {}, `You collected this money from receivers. ${money(w.locked)} of your wallet is locked until the admin accepts it.` + (Number(w.pending_cod_deposit) > 0 ? ` ${money(w.pending_cod_deposit)} is waiting for approval.` : ""))) : null;
  const buttons = h("div", { class: "tiles" }, h("button", { class: "btn", onclick: () => openMoneySheet("withdraw", w) }, "Withdraw"),
    due ? h("button", { class: "btn ghost", onclick: () => openMoneySheet("cod_deposit", w) }, "Hand in COD") : h("button", { class: "btn ghost", onclick: () => toast("You have no COD cash to hand in.") }, "Hand in COD"));
  const reqs = w.requests.slice(0, 8), hist = w.transactions.slice(0, 15);
  const reqList = reqs.length ? h("div", { class: "card list" }, reqs.map((r) => h("div", { class: "item" }, h("div", { class: "grow" }, h("b", {}, `${{ withdraw: "Withdrawal", cod_deposit: "COD hand-in", deposit: "Deposit" }[r.kind] || r.kind} \u00B7 ${money(r.amount)}`),
    h("small", {}, `${METHODS[r.method] || r.method} \u00B7 ${fmtWhen(r.created_at)}${r.admin_note ? ` \u00B7 ${r.admin_note}` : ""}`)), h("span", { class: "pill" + (r.status === "approved" ? " good" : r.status === "rejected" ? " bad" : "") }, r.status)))) : null;
  const txnList = hist.length ? h("div", { class: "card list" }, hist.map((t) => h("div", { class: "item" }, h("div", { class: "grow" }, h("b", {}, KINDS[t.kind] || t.kind), h("small", {}, `${t.note || ""} ${fmtWhen(t.created_at)}`.trim())),
    h("div", { class: "amt-sm num" }, `${Number(t.amount) < 0 ? "-" : "+"}${money(Math.abs(t.amount))}`, h("small", {}, money(t.balance_after)))))) : null;
  const tile = (l, v, hot) => h("div", { class: "tile" + (hot ? " hot" : "") }, h("small", {}, l), h("b", { class: "num" }, money(v)));
  return [h("h1", { class: "title", style: "margin-bottom:12px" }, "Wallet"), walletCard, lockNote, buttons, reqs.length ? h("div", { class: "section" }, h("span", {}, "Withdrawal and hand-in requests")) : null, reqList,
    h("div", { class: "section" }, h("span", {}, "Earnings")), h("div", { class: "tiles" }, tile("Today", e.today, true), tile("Last 7 days", e.week), tile("This month", e.month), tile("All time", e.total)),
    h("p", { class: "muted" }, `You earn ${e.rate_percent}% of the parcel price on every delivery. ${e.delivered} deliveries so far.`), h("div", { class: "section" }, h("span", {}, "Delivered parcels")),
    e.items.length ? h("div", { class: "card list" }, e.items.map((i) => h("div", { class: "item" }, h("div", { class: "badge-ic dark" }, icon("check")), h("div", { class: "grow" }, h("b", { class: "mono" }, i.tracking_number), h("small", {}, fmtWhen(i.delivered_at))),
      h("div", { class: "amt-sm num" }, `+${money(i.commission)}`, h("small", {}, `of ${money(i.price_total)}`))))) : h("div", { class: "card empty" }, "Your commissions will show up here after your first delivery."),
    txnList ? h("div", { class: "section" }, h("span", {}, "Wallet history")) : null, txnList].filter(Boolean);
}
async function profileView() {
  const m = state.me = await api("/rider/me"), kv = (k, v) => h("div", {}, h("span", {}, k), h("span", {}, v || "\u2013"));
  return [h("div", { style: "text-align:center;margin:10px 0 16px" }, avatar("lg"), h("h1", { class: "title", style: "font-size:24px" }, m.full_name), h("span", { class: "pill good" }, "Approved rider")),
    h("div", { class: "card kv" }, kv("Phone", m.phone), kv("Email", m.email), kv("Vehicle", m.vehicle && m.vehicle[0].toUpperCase() + m.vehicle.slice(1)), kv("City", m.city), kv(m.id_type === "passport" ? "Passport" : "NID", m.id_number_masked)),
    h("button", { class: "btn ghost", onclick: () => signOut() }, icon("logout"), "Sign out")];
}

boot();
