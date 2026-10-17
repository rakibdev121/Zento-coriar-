import { renderChrome, formData } from "./ui.js";
import { loadOptions, renderChoices, watchQuote, renderQuote } from "./quote.js";

renderChrome("pricing.html");
const form = document.getElementById("quote-form");
const panel = document.getElementById("quote-panel");
renderQuote(panel, null);

try {
  const opts = await loadOptions();
  renderChoices(document.getElementById("zone-choices"), "zone", opts.zones, "local");
  renderChoices(document.getElementById("service-choices"), "service", opts.services, "standard");
  form.elements.weight_kg.max = opts.limits.max_weight_kg;
  watchQuote(form, panel, opts.currency, () => formData(form));
} catch (err) {
  panel.textContent = err.message;
}
