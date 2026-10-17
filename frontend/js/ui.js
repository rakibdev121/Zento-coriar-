import { getUser, getToken, signOut } from "./api.js";

/** Tiny DOM builder: h("div", {class: "x", onclick: fn}, "text", childNode) */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  return el;
}

export const STATUS_LABEL = {
  booked: "Booked", picked_up: "Picked up", in_transit: "In transit",
  out_for_delivery: "Out for delivery", delivered: "Delivered", cancelled: "Cancelled",
};
export const statusBadge = (s) => h("span", { class: `badge ${s}` }, STATUS_LABEL[s] || s);

export function money(amount, currency = "USD") {
  const n = Number(amount);
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(n); } catch { return `${currency} ${n.toFixed(2)}`; }
}
export const fmtDateTime = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
export const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
export function etaText(min, max) {
  if (max === 0) return "Delivered today";
  if (min === max) return min === 1 ? "Delivered next day" : `Delivered in ${min} days`;
  return `Delivered in ${min}\u2013${max} days`;
}

const LOGO = `<svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true"><circle cx="5" cy="21" r="3.2" fill="currentColor"/><path d="M5 21 C 5 8, 23 20, 23 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M18.5 7 H23.5 V12" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

/** Renders the shared header and footer. `active` is the file name of the current page. */
export function renderChrome(active) {
  const user = getUser(), signedIn = !!getToken();
  const link = (href, label) => h("a", { href, "aria-current": href === active ? "page" : null }, label);
  const nav = h("nav", { class: "nav", id: "site-nav", "aria-label": "Main" },
    link("pricing.html", "Prices"), link("track.html", "Track a parcel"),
    signedIn ? [link("book.html", "Book a parcel"), link("dashboard.html", "My parcels"),
      h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: signOut }, "Sign out")]
      : [link("login.html", "Sign in"), h("a", { class: "btn btn-primary btn-sm", href: "register.html" }, "Create account")]);
  const logo = h("a", { class: "logo", href: "index.html", "aria-label": "ZENTO COURIER home" });
  logo.insertAdjacentHTML("afterbegin", LOGO);
  logo.append("ZENTO", h("small", {}, "COURIER"));
  const toggle = h("button", { class: "btn btn-ghost btn-sm menu-toggle", type: "button", "aria-expanded": "false", "aria-controls": "site-nav",
    onclick: (e) => { const open = nav.classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(open)); } }, "Menu");
  document.getElementById("site-header")?.replaceChildren(h("div", { class: "shell" }, logo, toggle, nav));
  document.getElementById("site-footer")?.replaceChildren(h("div", { class: "shell" },
    h("span", {}, `\u00A9 ${new Date().getFullYear()} ZENTO COURIER`),
    h("span", {}, user ? `Signed in as ${user.email}` : "Parcel delivery you can follow end to end")));
}

export function toast(message) {
  document.querySelector(".toast")?.remove();
  const t = h("div", { class: "toast", role: "status" }, message);
  document.body.append(t);
  setTimeout(() => t.remove(), 4000);
}

export function setBusy(button, busy, busyLabel = "Working\u2026") {
  if (busy) { button.dataset.label = button.textContent; button.textContent = busyLabel; button.setAttribute("aria-busy", "true"); button.disabled = true; }
  else { button.textContent = button.dataset.label || button.textContent; button.removeAttribute("aria-busy"); button.disabled = false; }
}

export function clearErrors(form) {
  form.querySelectorAll(".err").forEach((e) => (e.textContent = ""));
  form.querySelectorAll("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
  const banner = form.querySelector(".form-error"); if (banner) banner.hidden = true;
}

/** Show API field errors under their inputs; anything unmatched goes in the form banner. */
export function showErrors(form, error) {
  const banner = form.querySelector(".form-error");
  const unmatched = [];
  let first = null;
  for (const { field, message } of error.fieldErrors || []) {
    const slot = field && form.querySelector(`.err[data-for="${field}"]`);
    const input = field && form.elements[field];
    if (slot) {
      slot.textContent = message;
      if (input && input.setAttribute) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", slot.id || (slot.id = `err-${field}`)); first ||= input; }
    } else unmatched.push(message);
  }
  if (banner) {
    banner.textContent = unmatched.length ? unmatched.join(" ") : (error.fieldErrors?.length ? "Fix the highlighted fields and try again." : error.message);
    banner.hidden = false;
  }
  (first || banner)?.focus?.();
  if (!first && banner) { banner.setAttribute("tabindex", "-1"); banner.focus(); }
}

export function formData(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    if (el.type === "radio") { if (el.checked) out[el.name] = el.value; }
    else if (el.type === "checkbox") out[el.name] = el.checked;
    else out[el.name] = el.value.trim();
  }
  return out;
}

/** Labelled input with an error slot the API validation errors can target by field name. */
export function field({ name, label, type = "text", autocomplete, hint, required = true, attrs = {} }) {
  const id = `f-${name}`;
  return h("div", { class: "field" },
    h("label", { for: id }, label),
    h("input", { id, name, type, autocomplete, required, ...attrs }),
    hint ? h("p", { class: "hint" }, hint) : null,
    h("p", { class: "err", "data-for": name, id: `err-${name}`, role: "alert" }));
}

/** Vertical route timeline used on the public tracking page, the dashboard and the home sample. */
export function renderTimeline(events, status) {
  const last = events.length - 1;
  return h("ol", { class: "route" }, events.map((e, i) => {
    const state = i < last ? "done" : status === "delivered" ? "done" : status === "cancelled" ? "cancelled" : "now";
    return h("li", { class: state }, h("b", {}, e.note), h("small", {}, [fmtDateTime(e.created_at), e.location ? ` \u00B7 ${e.location}` : ""].join("")));
  }));
}
