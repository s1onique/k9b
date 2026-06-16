/**
 * App Header Component
 *
 * Extracted from App.tsx to reduce component size while maintaining
 * hook call order and state dependencies.
 */

import dayjs from "dayjs";
import { relativeRecency } from "../utils";
import {
  FRESHNESS_EMOJI,
  getPageFreshnessLevel,
  getRunFreshnessLevel,
  FRESHNESS_LABEL,
  AUTOREFRESH_OPTIONS,
} from "../utils/selectors";
import { ThemeSwitch } from "../ThemeSwitch";
import { HeaderBranding } from "../components/HeaderBranding";

export interface AppHeaderProps {
  // Run identity
  headerRunId: string;
  headerRunLabel: string;
  headerRunTimestamp: string;
  isSelectedRunLatest: boolean;
  latestRunRecency: string;
  runRecency: string;

  // Page freshness
  lastRefresh: ReturnType<typeof import("dayjs")["default"]>;
  onRefresh: () => void;

  // Auto-refresh
  autoRefreshInterval: number | undefined;
  onAutoRefreshChange: (value: string) => void;

  // Navigation
  onClickLatest: () => void;

  // Demo shell
  onOpenDemo: () => void;

  // Clock seam for testability (optional, defaults to real time)
  clock?: dayjs.Dayjs;
}

export function AppHeader({
  headerRunId,
  headerRunLabel,
  headerRunTimestamp,
  isSelectedRunLatest,
  latestRunRecency,
  runRecency,
  lastRefresh,
  onRefresh,
  autoRefreshInterval,
  onAutoRefreshChange,
  onClickLatest,
  onOpenDemo,
  clock,
}: AppHeaderProps) {
  const autoRefreshSelectValue = autoRefreshInterval ? String(autoRefreshInterval) : "off";
  const currentTime = clock ?? dayjs();

  return (
    <header className="panel hero compact">
      <div className="hero-content">
        <HeaderBranding />
        <div className="hero-run">
          <div className="hero-run-identity">
            <div className="hero-run-header">
              <p className="eyebrow hero-run-label">Selected run</p>
              <span className={`run-badge run-badge--${isSelectedRunLatest ? "latest" : "past"}`}>
                {isSelectedRunLatest ? "Latest" : "Past run"}
              </span>
            </div>
            <div className="hero-run-title">
              <strong>Run {headerRunLabel}</strong>
              <span className="hero-run-id">ID {headerRunId}</span>
            </div>
            <p className="hero-run-captured">Captured {runRecency}</p>
          </div>
          <div className="hero-run-freshness">
            {isSelectedRunLatest && (
              <span className={`freshness-indicator freshness-indicator--${getRunFreshnessLevel(headerRunTimestamp, currentTime)}`}>
                <span className="freshness-indicator__emoji">{FRESHNESS_EMOJI[getRunFreshnessLevel(headerRunTimestamp, currentTime)]}</span>
                <span className="freshness-indicator__label">{FRESHNESS_LABEL[getRunFreshnessLevel(headerRunTimestamp, currentTime)]}</span>
              </span>
            )}
            {!isSelectedRunLatest && (
              <button
                type="button"
                className="link tiny"
                onClick={onClickLatest}
                title="Jump back to the latest run"
              >
                ← Latest
              </button>
            )}
          </div>
          {!isSelectedRunLatest && (
            <p className="hero-run-latest-hint">
              Latest run available: {latestRunRecency}
            </p>
          )}
        </div>
      </div>
      <div className="hero-actions">
        <div className="refresh-controls">
          <span
            className={`page-freshness-indicator page-freshness-indicator--${getPageFreshnessLevel(lastRefresh, currentTime)}`}
            title={`Page data refreshed ${relativeRecency(lastRefresh.toISOString())}`}
            aria-label={`Page data freshness: ${getPageFreshnessLevel(lastRefresh, currentTime)}`}
          >
            {FRESHNESS_EMOJI[getPageFreshnessLevel(lastRefresh, currentTime)]}
          </span>
          <button type="button" onClick={onRefresh}>
            Refresh
          </button>
          <div className="autorefresh-control">
            <label htmlFor="auto-refresh-interval">Auto</label>
            <select
              id="auto-refresh-interval"
              value={autoRefreshSelectValue}
              onChange={(event) => onAutoRefreshChange(event.target.value)}
            >
              {AUTOREFRESH_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {/* ACT 9.5: K8s Accelerator demo entry point */}
        <button
          type="button"
          className="demo-entry-button"
          onClick={onOpenDemo}
          title="Launch the guided K8s Accelerator demo"
          data-testid="start-demo-button"
        >
          Start demo
        </button>
        <ThemeSwitch />
      </div>
    </header>
  );
}