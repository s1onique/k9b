/**
 * RunDiagnosticPackPanel component.
 * Displays a download link for the diagnostic pack artifact and related review bundles.
 * Renders links to the main diagnostic pack archive, review bundle, and 14b review input.
 */

import React from "react";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import type { RunPayload } from "../types";

dayjs.extend(utc);

/**
 * Builds an artifact URL from a path.
 * @param path - The artifact path
 * @returns The artifact URL or null if path is empty
 */
const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

/**
 * Format a timestamp for display.
 * @param value - ISO timestamp string
 * @returns Formatted timestamp string
 */
const formatTimestamp = (value: string) => dayjs.utc(value).format("MMM D, YYYY HH:mm [UTC]");

export interface RunDiagnosticPackPanelProps {
  diagnosticPack: RunPayload["diagnosticPack"] | undefined;
}

/**
 * RunDiagnosticPackPanel displays links to download the diagnostic pack and related review artifacts.
 */
export const RunDiagnosticPackPanel = ({
  diagnosticPack,
}: RunDiagnosticPackPanelProps) => {
  if (!diagnosticPack || !diagnosticPack.path) {
    return null;
  }
  const artifactLink = artifactUrl(diagnosticPack.path);
  if (!artifactLink) {
    return null;
  }
  const reviewBundleLink = diagnosticPack.reviewBundlePath
    ? artifactUrl(diagnosticPack.reviewBundlePath)
    : null;
  const reviewInput14bLink = diagnosticPack.reviewInput14bPath
    ? artifactUrl(diagnosticPack.reviewInput14bPath)
    : null;
  return (
    <section className="panel diagnostic-pack-download" id="diagnostic-pack-download">
      <div className="section-head">
        <div>
          <p className="eyebrow">Diagnostic pack</p>
          <h2>Run diagnostic package archive</h2>
        </div>
      </div>
      {diagnosticPack.label ? (
        <p className="muted tiny">Label: {diagnosticPack.label}</p>
      ) : null}
      <p className="muted tiny">
        {diagnosticPack.timestamp
          ? formatTimestamp(diagnosticPack.timestamp)
          : "Timestamp unavailable"}
      </p>
      <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
        Download diagnostic pack
      </a>
      {reviewBundleLink && (
        <>
          <br />
          <a className="link" href={reviewBundleLink} target="_blank" rel="noreferrer">
            Review bundle
          </a>
        </>
      )}
      {reviewInput14bLink && (
        <>
          <br />
          <a className="link" href={reviewInput14bLink} target="_blank" rel="noreferrer">
            Review input (14b)
          </a>
        </>
      )}
    </section>
  );
};
