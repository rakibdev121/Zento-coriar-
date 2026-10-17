// API client and session helpers. Token lives in localStorage; all rendered text goes through textContent.
const TOKEN_KEY = "zento.token";
const USER_KEY = "zento.user";

export class ApiError extends Error {
  constructor(message, status, fieldErrors = []) { super(message); this.status = status; this.fieldErrors = fieldErrors; }
}

export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const getUser = () => { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; } };
export function saveSession({ access_token, user }) {
  try { localStorage.setItem(TOKEN_KEY, access_token); localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch { /* storage blocked */ }
}
export function clearSession() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); } catch { /* ignore */ } }
export function signOut() { clearSession(); location.href = "index.html"; }

/** Send people to sign-in (and back afterwards) when there is no valid session. */
export function requireAuth() {
  if (!getToken()) {
    const next = location.pathname.split("/").pop() + location.search;
    location.replace(`login.html?next=${encodeURIComponent(next)}`);
    return false;
  }
  return true;
}

/** Only allow redirects to same-site relative pages, never to other origins. */
export function safeNext(raw, fallback = "dashboard.html") {
  return typeof raw === "string" && /^[a-z0-9_\-]+\.html(\?[\w=&%\-]*)?$/i.test(raw) ? raw : fallback;
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  const token = getToken();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty or non-JSON body */ }
  if (!res.ok) {
    if (res.status === 401 && auth && token) { clearSession(); }
    const detail = typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.";
    throw new ApiError(detail, res.status, Array.isArray(data?.errors) ? data.errors : []);
  }
  return data;
}
