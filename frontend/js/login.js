import { api, saveSession, safeNext, getToken } from "./api.js";
import { renderChrome, field, clearErrors, showErrors, setBusy, formData } from "./ui.js";

const next = safeNext(new URLSearchParams(location.search).get("next"));
if (getToken()) location.replace(next);
renderChrome("login.html");

const form = document.getElementById("login-form");
document.getElementById("fields").replaceChildren(
  field({ name: "email", label: "Email", type: "email", autocomplete: "email" }),
  field({ name: "password", label: "Password", type: "password", autocomplete: "current-password" }));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearErrors(form);
  const btn = form.querySelector("button[type=submit]");
  setBusy(btn, true, "Signing in\u2026");
  try {
    saveSession(await api("/auth/login", { method: "POST", auth: false, body: formData(form) }));
    location.href = next;
  } catch (err) {
    showErrors(form, err);
    setBusy(btn, false);
  }
});
