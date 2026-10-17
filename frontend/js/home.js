import { api } from "./api.js";
import { renderChrome, money } from "./ui.js";

renderChrome("index.html");

document.getElementById("track-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const n = new FormData(e.currentTarget).get("n").trim();
  if (n) location.href = `track.html?n=${encodeURIComponent(n)}`;
});

// "From" prices come from the pricing API so they never drift from what customers are charged.
(async () => {
  try {
    const { currency } = await api("/pricing/options", { auth: false });
    for (const el of document.querySelectorAll("[data-zone]")) {
      const q = await api("/pricing/quote", { method: "POST", auth: false, body: { zone: el.dataset.zone, service: "standard", weight_kg: "1" } });
      el.textContent = `from ${money(q.total, currency)}`;
    }
  } catch { /* leave the placeholders; the Prices page still works */ }
})();
