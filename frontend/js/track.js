import { api } from "./api.js";
import { renderChrome, h, statusBadge, renderTimeline, setBusy } from "./ui.js";

renderChrome("track.html");
const form = document.getElementById("track-form");
const input = form.elements.n;
const result = document.getElementById("result");
const errorSlot = document.getElementById("track-error");

let current = null;
window.addEventListener("zento:lang", () => { if (current) lookup(current); });
async function lookup(raw) {
  current = raw;
  errorSlot.textContent = "";
  result.replaceChildren(h("div", { class: "skeleton", style: "height:120px;max-width:620px" }));
  const btn = form.querySelector("button");
  setBusy(btn, true, "Looking\u2026");
  try {
    const t = await api(`/track/${encodeURIComponent(raw)}`, { auth: false });
    document.title = `${t.tracking_number} | ZENTO COURIER`;
    result.replaceChildren(h("div", { class: "waybill", style: "max-width:620px" },
      h("div", { class: "waybill-head" }, h("span", { class: "tracking-no" }, t.tracking_number), statusBadge(t.status)),
      h("p", {}, h("b", {}, t.pickup_city), " \u2192 ", h("b", {}, t.delivery_city), h("span", { class: "muted" }, ` \u00B7 ${t.service.replace("_", " ")} service`)),
      renderTimeline(t.events, t.status)));
  } catch (err) {
    result.replaceChildren();
    errorSlot.textContent = err.message;
    input.setAttribute("aria-invalid", "true");
  } finally { setBusy(btn, false); }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = input.value.trim();
  if (!v) return;
  history.replaceState(null, "", `track.html?n=${encodeURIComponent(v)}`);
  lookup(v);
});

const initial = new URLSearchParams(location.search).get("n");
if (initial) { input.value = initial; lookup(initial); }
