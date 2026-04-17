import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./themes.css";
import { applyStoredThemeOnLoad } from "./theme";

// Apply saved theme before first render to prevent flash
applyStoredThemeOnLoad();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);