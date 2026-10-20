import { api, requireAuth, getUser, clearSession } from "./api.js";
import { renderChrome, h, field, clearErrors, showErrors, setBusy, formData, money } from "./ui.js";
import { loadOptions, renderChoices, watchQuote, renderQuote } from "./quote.js";

if (!requireAuth()) await new Promise(() => {}); // redirecting to sign in; stop this module quietly
renderChrome("book.html");

const form = document.getElementById("book-form");
const panel = document.getElementById("quote-panel");
renderQuote(panel, null);

const party = (prefix, title, user, cityLabel) => h("fieldset", {}, h("legend", {}, title),
  h("div", { class: "grid-2" },
    field({ name: `${prefix}_name`, label: "Name", autocomplete: "off", attrs: { maxlength: 100 } }),
    field({ name: `${prefix}_phone`, label: "Phone", type: "tel", autocomplete: "off", attrs: { maxlength: 20 } })),
  field({ name: prefix === "sender" ? "pickup_address" : "delivery_address", label: prefix === "sender" ? "Pickup address" : "Delivery address", autocomplete: "off", attrs: { maxlength: 255 } }),
  field({ name: prefix === "sender" ? "pickup_city" : "delivery_city", label: cityLabel, autocomplete: "off", attrs: { maxlength: 80 } }));

document.getElementById("sender").replaceChildren(party("sender", "Pickup", getUser(), "Pickup city"));
document.getElementById("recipient").replaceChildren(party("recipient", "Delivery", getUser(), "Delivery city"));
const user = getUser();
if (user) { form.elements.sender_name.value = user.full_name; form.elements.sender_phone.value = user.phone; }

document.getElementById("parcel").replaceChildren(
  field({ name: "weight_kg", label: "Weight (kg)", type: "number", attrs: { min: "0.01", step: "0.01", inputmode: "decimal" } }),
  h("div", { class: "grid-3" },
    ...["length_cm:Length (cm)", "width_cm:Width (cm)", "height_cm:Height (cm)"].map((s) => { const [name, label] = s.split(":"); return field({ name, label, type: "number", required: false, attrs: { min: 1, step: 1, inputmode: "numeric" } }); })),
  h("p", { class: "hint", style: "margin-top:-.5rem" }, "Size is optional. Bulky parcels are charged on size when that is more than their weight."),
  field({ name: "declared_value", label: "Value to insure", type: "number", required: false, attrs: { min: 0, step: "0.01", inputmode: "decimal", value: "0" } }),
  field({ name: "description", label: "What is inside?", required: false, attrs: { maxlength: 200 } }),
  field({ name: "cod_amount", label: "Cash on Delivery amount (\u09F3)", required: false, attrs: { min: 0, step: "0.01", inputmode: "decimal", value: "0" },
    hint: "Leave 0 if the receiver pays nothing. If you enter an amount, our rider collects it from the receiver and it goes to your wallet after delivery." }),
  h("label", { class: "check" }, h("input", { type: "checkbox", name: "fragile" }), "This parcel is fragile"));

let currency = "BDT";
try {
  const opts = await loadOptions();
  currency = opts.currency;
  renderChoices(document.getElementById("zone-choices"), "zone", opts.zones, "local");
  renderChoices(document.getElementById("service-choices"), "service", opts.services, "standard");
  form.elements.weight_kg.max = opts.limits.max_weight_kg;
} catch (err) {
  form.querySelector(".form-error").textContent = err.message;
  form.querySelector(".form-error").hidden = false;
}
watchQuote(form, panel, currency, () => formData(form));

// Wallet balance: the booking price is taken from it at once.
const walletBox = h("div", { class: "notice", id: "wallet-box" }, "Checking your wallet\u2026");
form.insertBefore(walletBox, form.querySelector("button[type=submit]"));
async function showWallet() {
  try {
    const w = await api("/wallet");
    walletBox.replaceChildren(`Wallet balance: ${money(w.balance)}. The booking price is taken from it. `, h("a", { href: "wallet.html" }, "Deposit money"));
  } catch { walletBox.hidden = true; }
}
showWallet();

function payload() {
  const d = formData(form);
  d.cod_amount = d.cod_amount || "0";
  for (const k of ["length_cm", "width_cm", "height_cm"]) d[k] = d[k] === "" ? null : Number(d[k]);
  d.declared_value = d.declared_value || "0";
  d.description = d.description || null;
  return d;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearErrors(form);
  const btn = form.querySelector("button[type=submit]");
  setBusy(btn, true, "Booking\u2026");
  try {
    const p = await api("/parcels", { method: "POST", body: payload() });
    document.getElementById("book-layout").hidden = true;
    const done = document.getElementById("done");
    done.replaceChildren(
      h("h1", { style: "font-size:2rem" }, "Booking confirmed"),
      h("p", { class: "muted" }, "Your tracking number"),
      h("span", { class: "tracking-no" }, p.tracking_number),
      h("p", {}, `${money(p.price_total)} was taken from your wallet.`, Number(p.cod_amount) > 0 ? ` The rider will collect ${money(p.cod_amount)} from the receiver and it will be added to your wallet after delivery.` : null),
      h("p", {}, "Keep this number. Anyone with it can follow the parcel."),
      h("div", { class: "hero-actions", style: "justify-content:center" },
        h("a", { class: "btn btn-primary", href: "dashboard.html" }, "View my parcels"),
        h("a", { class: "btn btn-ghost", href: `track.html?n=${p.tracking_number}` }, "Track this parcel"),
        h("a", { class: "btn btn-ghost", href: "book.html" }, "Book another")));
    done.hidden = false;
    done.querySelector("h1").setAttribute("tabindex", "-1");
    done.querySelector("h1").focus();
  } catch (err) {
    if (err.status === 401) { location.href = `login.html?next=${encodeURIComponent("book.html")}`; return; }
    showErrors(form, err);
    setBusy(btn, false);
  }
});
