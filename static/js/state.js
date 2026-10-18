// Shared application state and tiny helpers used by every module.
// `I18N` is defined by the classic script i18n.js, which loads before the modules.
export const $ = (id) => document.getElementById(id);

export const state = {
  lang: "en",
  session: null,        // { username, role, facility_id } – never the token (it is an HttpOnly cookie)
  tab: null,
  facilities: [],
  medicines: [],
  knownHigh: null,      // ids of centres already known to be high severity (for the new-alert banner)
  timer: null,
  renderId: 0,          // guards against stale responses overwriting a newer view
};

/** Translate a UI string key, falling back to English and then to the key itself. */
export const tr = (key) => (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;

export function notice(message, isError) {
  const el = $("notice");
  el.textContent = message || "";
  el.className = isError ? "bad" : "";
}
