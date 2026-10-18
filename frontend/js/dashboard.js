import { api, requireAuth, getUser, downloadFile } from "./api.js";
import { renderChrome, h, money, fmtDate, statusBadge, STATUS_LABEL, renderTimeline, toast } from "./ui.js";

if (!requireAuth()) await new Promise(() => {}); // redirecting to sign in; stop this module quietly
renderChrome("dashboard.html");

const PAGE_SIZE = 10;
const state = { page: 1, status: "", currency: "BDT" };
const els = { stats: document.getElementById("stats"), list: document.getElementById("list"), pager: document.getElementById("pager"),
  filter: document.getElementById("filter"), detail: document.getElementById("detail") };

const first = (getUser()?.full_name || "").split(" ")[0];
document.getElementById("greeting").textContent = first ? `Hello, ${first}` : "My parcels";
for (const [v, label] of Object.entries(STATUS_LABEL)) els.filter.append(h("option", { value: v }, label));

function handle(err) {
  if (err.status === 401) { location.replace(`login.html?next=${encodeURIComponent("dashboard.html")}`); return; }
  els.list.replaceChildren(h("div", { class: "form-error" }, err.message, " ", h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: loadAll }, "Try again")));
}

async function loadSummary() {
  const s = await api("/dashboard/summary");
  state.currency = s.currency;
  const stat = (v, l) => h("div", { class: "stat" }, h("b", { class: "num" }, v), h("span", {}, l));
  els.stats.replaceChildren(stat(s.total_parcels, "Total parcels"), stat(s.in_progress, "In progress"), stat(s.delivered, "Delivered"), stat(money(s.total_spent, s.currency), "Spent (excl. cancelled)"));
}

async function loadList() {
  els.list.replaceChildren(h("div", { class: "skeleton", style: "height:160px" }));
  const q = new URLSearchParams({ page: state.page, page_size: PAGE_SIZE });
  if (state.status) q.set("status", state.status);
  const data = await api(`/parcels?${q}`);
  if (!data.items.length) {
    els.list.replaceChildren(h("div", { class: "card empty-state" },
      h("h3", {}, state.status ? "No parcels with this status" : "You have not booked a parcel yet"),
      h("p", { class: "muted" }, state.status ? "Try another status." : "Book your first pickup and it will show up here."),
      state.status ? null : h("a", { class: "btn btn-primary", href: "book.html" }, "Book a parcel")));
    els.pager.replaceChildren();
    return;
  }
  els.list.replaceChildren(h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Tracking number", "Route", "Recipient", "Booked", "Status", "Price", ""].map((t, i) => h("th", { class: i === 5 ? "right" : "" }, t)))),
    h("tbody", {}, data.items.map((p) => h("tr", {},
      h("td", {}, h("span", { class: "tracking-no" }, p.tracking_number)),
      h("td", {}, `${p.pickup_city} \u2192 ${p.delivery_city}`),
      h("td", {}, p.recipient_name),
      h("td", {}, fmtDate(p.created_at)),
      h("td", {}, statusBadge(p.status)),
      h("td", { class: "right num" }, money(p.price_total, state.currency)),
      h("td", { class: "right" }, h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => openDetail(p.id) }, "Details"))))))));
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  els.pager.replaceChildren(
    h("button", { class: "btn btn-ghost btn-sm", type: "button", disabled: state.page <= 1, onclick: () => go(state.page - 1) }, "Previous"),
    h("span", { class: "muted" }, `Page ${state.page} of ${pages} (${data.total} parcels)`),
    h("button", { class: "btn btn-ghost btn-sm", type: "button", disabled: state.page >= pages, onclick: () => go(state.page + 1) }, "Next"));
}

const go = (page) => { state.page = page; loadList().catch(handle); };
async function loadAll() { try { await Promise.all([loadSummary(), loadList()]); } catch (e) { handle(e); } }

async function openDetail(id) {
  try {
    const p = await api(`/parcels/${id}`);
    const kv = (k, v) => [h("dt", {}, k), h("dd", {}, v)];
    const size = p.length_cm ? `${p.length_cm} \u00D7 ${p.width_cm} \u00D7 ${p.height_cm} cm` : "Not given";
    els.detail.replaceChildren(h("div", { class: "dialog-body" },
      h("div", { class: "dialog-head" }, h("div", {}, h("h2", { id: "detail-title", style: "margin:0 0 .3rem;font-size:1.4rem" }, p.tracking_number), statusBadge(p.status)),
        h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => els.detail.close() }, "Close")),
      h("dl", { class: "kv" },
        ...kv("From", `${p.sender_name}, ${p.pickup_address}, ${p.pickup_city}`),
        ...kv("To", `${p.recipient_name}, ${p.delivery_address}, ${p.delivery_city}`),
        ...kv("Service", `${p.zone} \u00B7 ${p.service.replace("_", " ")}`),
        ...kv("Weight", `${Number(p.weight_kg)} kg (charged ${Number(p.chargeable_weight_kg)} kg)`),
        ...kv("Size", size), ...kv("Fragile", p.fragile ? "Yes" : "No"),
        ...kv("Insured for", money(p.declared_value, state.currency)),
        ...(p.description ? kv("Contents", p.description) : []),
        ...(Number(p.cod_amount) > 0 ? kv("Cash on delivery", money(p.cod_amount)) : []),
        ...kv("Total", money(p.price_total, state.currency))),
      h("h3", {}, "Progress"), renderTimeline(p.events, p.status),
      h("div", { style: "margin-top:1.25rem;display:flex;gap:.6rem;flex-wrap:wrap" },
        h("button", { class: "btn btn-ghost", type: "button", onclick: (e) => savePdf(p, e.currentTarget) }, "Download PDF"),
        p.status === "booked" ? h("button", { class: "btn btn-danger", type: "button", onclick: (e) => cancel(p, e.currentTarget) }, "Cancel this booking") : null)));
    els.detail.showModal();
  } catch (err) { err.status === 401 ? handle(err) : toast(err.message); }
}

async function savePdf(p, btn) {
  btn.disabled = true;
  try { await downloadFile(`/parcels/${p.id}/pdf`, `${p.tracking_number}.pdf`); } catch (err) { toast(err.message); } finally { btn.disabled = false; }
}

async function cancel(p, btn) {
  if (!confirm(`Cancel ${p.tracking_number}? The price goes back to your wallet.`)) return;
  btn.disabled = true;
  try {
    await api(`/parcels/${p.id}/cancel`, { method: "POST" });
    els.detail.close();
    toast("Booking cancelled. The price is back in your wallet.");
    loadAll();
  } catch (err) { btn.disabled = false; toast(err.message); }
}

els.filter.addEventListener("change", () => { state.status = els.filter.value; go(1); });
loadAll();
