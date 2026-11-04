export type Theme = "dark" | "light";
const KEY = "mlforge.theme";

export function readTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage unavailable (private mode): theme still applies for this page */
  }
}

/** Inline script run before paint so a light-theme user never sees a dark flash. */
export const THEME_BOOTSTRAP = `try{if(localStorage.getItem("${KEY}")==="light")document.documentElement.dataset.theme="light"}catch(e){}`;
