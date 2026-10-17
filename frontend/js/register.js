import { api, saveSession, getToken } from "./api.js";
import { renderChrome, field, clearErrors, showErrors, setBusy, formData } from "./ui.js";

if (getToken()) location.replace("dashboard.html");
renderChrome("register.html");

const form = document.getElementById("register-form");
document.getElementById("fields").replaceChildren(
  field({ name: "full_name", label: "Full name", autocomplete: "name", attrs: { minlength: 2, maxlength: 100 } }),
  field({ name: "email", label: "Email", type: "email", autocomplete: "email" }),
  field({ name: "phone", label: "Phone", type: "tel", autocomplete: "tel", hint: "Couriers use this to reach you about pickups.", attrs: { maxlength: 20 } }),
  field({ name: "password", label: "Password", type: "password", autocomplete: "new-password", hint: "At least 8 characters, with a letter and a number.", attrs: { minlength: 8, maxlength: 128 } }));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearErrors(form);
  const btn = form.querySelector("button[type=submit]");
  setBusy(btn, true, "Creating account\u2026");
  try {
    saveSession(await api("/auth/register", { method: "POST", auth: false, body: formData(form) }));
    location.href = "dashboard.html";
  } catch (err) {
    showErrors(form, err);
    setBusy(btn, false);
  }
});
