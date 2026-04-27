/**
 * RunDiagnosticPackPanel component.
 * Displays a download link for the diagnostic pack artifact and related review bundles.
 * Renders links to the main diagnostic pack archive, review bundle, and 14b review input.
 */

import React from "react";
import { artifactUrl, formatTimestamp } from "../utils";
import type { RunPayload } from "../types";

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
        <h2>Run diagnostic package</h2>
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
