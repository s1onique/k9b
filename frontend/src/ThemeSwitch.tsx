/**
 * Theme Switch Component
 * 
 * Provides user-facing toggle between Dark and Solarized Light themes.
 * Uses a native <select> element for simple, accessible theme switching.
 */

import { useCallback, useState } from "react";
import { applyTheme, readStoredTheme, ThemeName, THEME_STORAGE_KEY } from "./theme";

export { THEME_STORAGE_KEY };
export type { ThemeName };

export const ThemeSwitch = () => {
  const [currentTheme, setCurrentTheme] = useState<ThemeName>(readStoredTheme());

  const handleThemeChange = useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const theme = event.target.value as ThemeName;
    applyTheme(theme);
    setCurrentTheme(theme);
  }, []);

  return (
    <div className="theme-switch">
      <label className="theme-switch-label">
        <span className="visually-hidden">Theme</span>
        <select
          className="theme-switch-select"
          value={currentTheme}
          onChange={handleThemeChange}
          aria-label="Select theme"
        >
          <option value="dark">Dark</option>
          <option value="solarized-light">Solarized Light</option>
        </select>
      </label>
    </div>
  );
};
