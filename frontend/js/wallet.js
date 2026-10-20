import { api, requireAuth } from "./api.js";
import { renderChrome, h, field, clearErrors, showErrors, setBusy, formData, money, fmtDateTime, toast } from "./ui.js";

if (!requireAuth()) await new Promise(() => {}); // redirecting to sign in
renderChrome("wallet.html");

const root = document.getElementById("wallet-root");
const METHOD = { bkash: "bKash", nagad: "Nagad", rocket: "Rocket", bank: "Bank", cash: "Cash" };
const KIND = { deposit: "Deposit", booking: "Booking", refund: "Refund", cod: "COD received", commission: "Commission", withdrawal: "Withdrawal", withdrawal_refund: "Withdrawal returned", adjustment: "Adjustment", withdraw: "Withdraw", cod_deposit: "COD hand-in" };
let tab = "deposit";

const select = (name, label, options) => h("div", { class: "field" }, h("label", { for: `f-${name}` }, label),
  h("select", { id: `f-${name}`, name }, options.map(([v, l]) => h("option", { value: v }, l))), h("p", { class: "err", "data-for": name, role: "alert" }));

function moneyForm({ w, kind }) {
  const dep = kind === "deposit";
  const form = h("form", { class: "card", novalidate: true },
    h("div", { class: "form-error", role: "alert", hidden: true }),
    field({ name: "amount", label: "Amount (\u09F3)", type: "number", attrs: { min: "1", step: "0.01", inputmode: "decimal" }, hint: dep ? `Smallest deposit ${money(w.min_deposit)}` : `You can withdraw up to ${money(w.withdrawable)}. Smallest withdrawal ${money(w.min_withdraw)}.` }),
    select("method", dep ? "You paid with" : "Send my money to", [["bkash", "bKash"], ["nagad", "Nagad"], ["rocket", "Rocket"], ["bank", "Bank"]]),
    field({ name: "account", label: dep ? "The number or account you paid from" : "My bKash / Nagad / Rocket number or bank account", autocomplete: "off", attrs: { maxlength: 40, placeholder: "01XXXXXXXXX" } }),
    dep ? field({ name: "reference", label: "Transaction ID (TrxID)", autocomplete: "off", attrs: { maxlength: 60 }, hint: "You get it in the confirmation message after you send the money." }) : null,
    h("button", { class: "btn btn-primary", type: "submit" }, dep ? "Send deposit request" : "Request withdrawal"));
  form.addEventListener("submit", async (e) => {
    e.preventDefault(); clearErrors(form);
    const btn = form.querySelector("button[type=submit]"), d = formData(form);
    setBusy(btn, true, "Sending\u2026");
    try {
      await api(dep ? "/wallet/deposit" : "/wallet/withdraw", { method: "POST", body: { amount: d.amount, method: d.method, account: d.account, reference: d.reference || null } });
      toast(dep ? "Request sent. Your balance updates when we confirm the payment." : "Withdrawal requested. The amount is on hold until we pay it out.");
      await load();
    } catch (err) { showErrors(form, err); setBusy(btn, false); }
  });
  return form;
}

function depositPanel(w) {
  const lines = Object.entries(w.pay_to).filter(([, v]) => v).map(([k, v]) => h("div", {}, `${METHOD[k]}: `, h("b", {}, v)));
  return [h("div", { class: "pay-to" }, lines.length ? [h("div", {}, "1. Send money to one of these:"), ...lines, h("div", { style: "margin-top:.4rem" }, "2. Fill in the form below with the amount and your TrxID. We add the money after we check it.")]
    : h("div", {}, "Payment numbers have not been set up yet. Please contact ZENTO COURIER support to deposit.")), moneyForm({ w, kind: "deposit" })];
}

function withdrawPanel(w) {
  return [Number(w.cod_due) > 0 ? h("div", { class: "notice" }, `Withdrawal is limited until you hand in ${money(w.cod_due)} COD cash.`) : null, moneyForm({ w, kind: "withdraw" })].filter(Boolean);
}

const badge = (s) => h("span", { class: `badge ${s === "approved" ? "delivered" : s === "rejected" ? "cancelled" : "booked"}` }, s[0].toUpperCase() + s.slice(1));

function historyPanel(w) {
  const reqs = w.requests.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Date", "Type", "Amount", "Method", "Status"].map((t) => h("th", {}, t)))),
    h("tbody", {}, w.requests.map((r) => h("tr", {}, h("td", {}, fmtDateTime(r.created_at)), h("td", {}, KIND[r.kind] || r.kind), h("td", { class: "num" }, money(r.amount)), h("td", {}, METHOD[r.method] || r.method),
      h("td", {}, badge(r.status), r.admin_note ? h("small", { class: "muted", style: "display:block" }, r.admin_note) : null)))))) : h("p", { class: "muted" }, "No deposit or withdrawal requests yet.");
  const txns = w.transactions.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Date", "What", "Amount", "Balance"].map((t, i) => h("th", { class: i > 1 ? "right" : "" }, t)))),
    h("tbody", {}, w.transactions.map((t) => h("tr", {}, h("td", {}, fmtDateTime(t.created_at)), h("td", {}, KIND[t.kind] || t.kind, t.note ? h("small", { class: "muted", style: "display:block" }, t.note) : null),
      h("td", { class: `right num ${Number(t.amount) < 0 ? "neg" : "pos"}` }, `${Number(t.amount) < 0 ? "-" : "+"}${money(Math.abs(t.amount))}`), h("td", { class: "right num" }, money(t.balance_after))))))) : h("p", { class: "muted" }, "Nothing has happened in your wallet yet.");
  return [h("h2", { style: "font-size:1.3rem" }, "Deposit and withdrawal requests"), reqs, h("h2", { style: "font-size:1.3rem;margin-top:1.5rem" }, "Wallet history"), txns];
}

async function load() {
  let w;
  try { w = await api("/wallet"); } catch (err) {
    if (err.status === 401) { location.replace("login.html?next=wallet.html"); return; }
    root.replaceChildren(h("div", { class: "form-error" }, err.message)); return;
  }
  const tabBtn = (id, label) => h("button", { class: "btn btn-sm " + (tab === id ? "btn-primary" : "btn-ghost"), type: "button", onclick: () => { tab = id; render(w); } }, label);
  root.replaceChildren(
    h("div", { class: "wallet-hero" }, h("small", {}, "Wallet balance"), h("div", { class: "amt" }, money(w.balance)),
      h("small", { style: "margin-top:.5rem" }, `Available to withdraw: ${money(w.withdrawable)}`)),
    h("div", { class: "tabs", id: "tabs" }, tabBtn("deposit", "Deposit"), tabBtn("withdraw", "Withdraw"), tabBtn("history", "History")),
    h("div", { id: "panel", style: "max-width:640px" }));
  render(w);
}

function render(w) {
  const tabs = root.querySelector("#tabs");
  tabs.replaceChildren(...["deposit:Deposit", "withdraw:Withdraw", "history:History"].map((s) => { const [id, label] = s.split(":");
    return h("button", { class: "btn btn-sm " + (tab === id ? "btn-primary" : "btn-ghost"), type: "button", onclick: () => { tab = id; render(w); } }, label); }));
  const panel = root.querySelector("#panel");
  panel.style.maxWidth = tab === "history" ? "none" : "640px";
  panel.replaceChildren(...(tab === "deposit" ? depositPanel(w) : tab === "withdraw" ? withdrawPanel(w) : historyPanel(w)));
}

load();

window.addEventListener("zento:lang", load);
