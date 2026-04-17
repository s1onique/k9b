/**
 * Theme System Module
 * 
 * Centralized theme configuration shared between:
 * - main.tsx (initial theme application before render)
 * - ThemeSwitch.tsx (runtime theme switching)
 */

export const THEME_STORAGE_KEY = "dashboard-theme";
export const VALID_THEMES = ["dark", "solarized-light"] as const;
export type ThemeName = (typeof VALID_THEMES)[number];

// Default theme when nothing is stored
export const DEFAULT_THEME: ThemeName = "dark";

/**
 * Read current theme from localStorage
 * Falls back to default theme if not set or invalid
 */
export const readStoredTheme = (): ThemeName => {
  if (typeof window === "undefined") {
    return DEFAULT_THEME;
  }
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored && VALID_THEMES.includes(stored as ThemeName)) {
      return stored as ThemeName;
    }
  } catch {
    // Ignore storage errors
  }
  return DEFAULT_THEME;
};

/**
 * Apply theme to document and persist to localStorage
 */
export const applyTheme = (theme: ThemeName): void => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Ignore storage errors
  }
  document.documentElement.setAttribute("data-theme", theme);
};

/**
 * Apply stored theme on initial page load (call before React renders)
 * This prevents flash of incorrect theme
 */
export const applyStoredThemeOnLoad = (): void => {
  const theme = readStoredTheme();
  applyTheme(theme);
};
