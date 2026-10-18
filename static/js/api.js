// Thin fetch wrapper for the JSON API.
import { state, tr } from "./state.js";

let onUnauthorized = () => {};
/** Register what to do when the server says the session is gone (set by the app shell). */
export const setUnauthorizedHandler = (handler) => { onUnauthorized = handler; };

const errorMessage = (detail) => {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e.msg).join("; ");
  return tr("error");
};

export async function api(path, options = {}) {
  // Auth is an HttpOnly cookie set by the server; JS never sees or stores the token.
  // The custom header is the CSRF guard the server requires on state-changing requests.
  const headers = {
    "Content-Type": "application/json",
    "Accept-Language": state.lang,
    "X-Requested-With": "smarthealth",
  };
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`/api${path}${separator}lang=${state.lang}`,
    { ...options, headers, credentials: "same-origin" });

  if (response.status === 401 && state.session) {
    onUnauthorized();
    throw new Error("Session expired");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorMessage(body.detail));
  return body;
}
