import { api } from "./api.js";
import { h, money, etaText } from "./ui.js";

let optionsPromise;
export const loadOptions = () => (optionsPromise ||= api("/pricing/options", { auth: false }));

export function renderChoices(container, name, items, selected) {
  container.replaceChildren(...items.map((it) => h("label", { class: "choice" },
    h("input", { type: "radio", name, value: it.id, checked: it.id === selected }),
    h("span", {}, h("b", {}, it.label), h("small", {}, it.description)))));
}

/** Same-day is local-only: disable it elsewhere and fall back to standard. */
export function syncServiceAvailability(form) {
  const local = form.elements.zone?.value === "local";
  const sameDay = form.querySelector('input[name="service"][value="same_day"]');
  if (!sameDay) return;
  sameDay.disabled = !local;
  if (!local && sameDay.checked) form.querySelector('input[name="service"][value="standard"]').checked = true;
}

export function toQuotePayload(d) {
  const p = { zone: d.zone, service: d.service, weight_kg: d.weight_kg, fragile: !!d.fragile, declared_value: d.declared_value || "0" };
  for (const k of ["length_cm", "width_cm", "height_cm"]) if (d[k] !== "" && d[k] != null) p[k] = Number(d[k]);
  return p;
}

export function renderQuote(panel, quote, currency) {
  if (!quote) { panel.replaceChildren(h("h2", {}, "Your price"), h("p", { class: "empty" }, "Enter the parcel weight to see the price.")); return; }
  panel.replaceChildren(
    h("h2", {}, "Your price"),
    h("dl", {}, quote.lines.map((l) => h("div", { class: "row" }, h("dt", {}, l.label), h("dd", {}, money(l.amount, currency))))),
    h("div", { class: "total" }, h("span", {}, "Total"), h("span", { class: "num" }, money(quote.total, currency))),
    h("p", { class: "eta" }, `${etaText(quote.eta_min_days, quote.eta_max_days)}. Charged for ${Number(quote.chargeable_weight_kg)} kg.`));
}

/** Live quote: re-prices (debounced) whenever the form changes. Returns a function to force a refresh. */
export function watchQuote(form, panel, currency, getData) {
  let timer, seq = 0;
  const run = async () => {
    const mine = ++seq;
    const d = getData();
    if (!d.weight_kg) return renderQuote(panel, null, currency);
    try {
      const q = await api("/pricing/quote", { method: "POST", body: toQuotePayload(d), auth: false });
      if (mine === seq) renderQuote(panel, q, currency);
    } catch (err) {
      if (mine !== seq) return;
      const msg = err.fieldErrors?.length ? err.fieldErrors.map((e) => e.message).join(" ") : err.message;
      panel.replaceChildren(h("h2", {}, "Your price"), h("p", { class: "empty" }, msg));
    }
  };
  const schedule = () => { syncServiceAvailability(form); clearTimeout(timer); timer = setTimeout(run, 300); };
  form.addEventListener("input", schedule);
  form.addEventListener("change", schedule);
  syncServiceAvailability(form);
  run();
  return run;
}
