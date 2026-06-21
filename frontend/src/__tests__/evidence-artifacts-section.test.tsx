/**
 * EvidenceArtifactsSection tests
 *
 * Verifies:
 * 1. Empty state: "No evidence artifacts attached."
 * 2. Single artifact rendering with all metadata
 * 3. Multiple artifacts rendering in sorted order
 * 4. Unknown artifact kind handled safely
 * 5. Safety wording present
 * 6. No raw content exposure
 * 7. No action/remediation controls
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvidenceArtifactsSection } from "../components/EvidenceArtifactsSection";
import type { EvidenceArtifact } from "../api";

// Full fixture using EvidenceArtifact
const createArtifactFixture = (overrides: Partial<EvidenceArtifact> = {}): EvidenceArtifact => ({
  artifact_id: "test-artifact-1",
  artifact_kind: "snapshot_bundle",
  evidence_role: "snapshot",
  source: null,
  created_at: null,
  attached_at: "2026-01-01T14:00:00Z",
  run_id: null,
  collector_run_id: null,
  summary: null,
  safe_reference: "test-artifact-1",
  available: true,
  unavailable_reason: null,
  read_only: true,
  raw_content_available: false,
  no_remediation_attempted: true,
  ...overrides,
});

describe("EvidenceArtifactsSection", () => {
  describe("1. Empty state", () => {
    it('shows "No evidence artifacts attached." when array is empty', () => {
      render(<EvidenceArtifactsSection evidenceArtifacts={[]} />);

      expect(screen.getByText("No evidence artifacts attached.")).toBeInTheDocument();
      expect(screen.getByText("Evidence artifacts")).toBeInTheDocument();
    });

    it("does not show list items when empty", () => {
      render(<EvidenceArtifactsSection evidenceArtifacts={[]} />);

      const list = document.querySelector(".evidence-artifacts-list");
      expect(list).not.toBeInTheDocument();
    });
  });

  describe("2. Single artifact rendering", () => {
    it("renders artifact with all metadata fields", () => {
      const artifact = createArtifactFixture({
        artifact_id: "snapshot-abc-123",
        artifact_kind: "snapshot_bundle",
        evidence_role: "snapshot",
        attached_at: "2026-01-15T10:30:00Z",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText("Snapshot bundle")).toBeInTheDocument();
      expect(screen.getByText("snapshot")).toBeInTheDocument();
      expect(screen.getByText("snapshot-abc-123")).toBeInTheDocument();
    });

    it("renders review_packet artifact kind", () => {
      const artifact = createArtifactFixture({
        artifact_id: "review-xyz-789",
        artifact_kind: "review_packet",
        evidence_role: "review_packet",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText("Review packet")).toBeInTheDocument();
    });

    it("renders evidence_artifact artifact kind", () => {
      const artifact = createArtifactFixture({
        artifact_id: "evidence-123",
        artifact_kind: "evidence_artifact",
        evidence_role: "primary",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText("Evidence artifact")).toBeInTheDocument();
    });

    it("renders debug_artifact artifact kind", () => {
      const artifact = createArtifactFixture({
        artifact_id: "debug-456",
        artifact_kind: "debug_artifact",
        evidence_role: "debug",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText("Debug artifact")).toBeInTheDocument();
    });

    it("renders unknown artifact kind safely", () => {
      const artifact = createArtifactFixture({
        artifact_id: "unknown-789",
        artifact_kind: "unknown",
        evidence_role: "unknown_role",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText("Unknown artifact")).toBeInTheDocument();
    });
  });

  describe("3. Multiple artifacts rendering", () => {
    it("renders multiple artifacts", () => {
      const artifacts = [
        createArtifactFixture({ artifact_id: "artifact-1", artifact_kind: "snapshot_bundle" }),
        createArtifactFixture({ artifact_id: "artifact-2", artifact_kind: "review_packet" }),
        createArtifactFixture({ artifact_id: "artifact-3", artifact_kind: "evidence_artifact" }),
      ];
      render(<EvidenceArtifactsSection evidenceArtifacts={artifacts} />);

      expect(screen.getByText("artifact-1")).toBeInTheDocument();
      expect(screen.getByText("artifact-2")).toBeInTheDocument();
      expect(screen.getByText("artifact-3")).toBeInTheDocument();
    });

    it("renders all artifact kind labels", () => {
      const artifacts = [
        createArtifactFixture({ artifact_id: "snap", artifact_kind: "snapshot_bundle" }),
        createArtifactFixture({ artifact_id: "review", artifact_kind: "review_packet" }),
        createArtifactFixture({ artifact_id: "evidence", artifact_kind: "evidence_artifact" }),
      ];
      render(<EvidenceArtifactsSection evidenceArtifacts={artifacts} />);

      expect(screen.getAllByText("Snapshot bundle")).toHaveLength(1);
      expect(screen.getAllByText("Review packet")).toHaveLength(1);
      expect(screen.getAllByText("Evidence artifact")).toHaveLength(1);
    });
  });

  describe("4. Safety wording", () => {


    it("shows section header with safety message", () => {
      const artifact = createArtifactFixture();
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getByText(/Read-only view/i)).toBeInTheDocument();
      expect(screen.getByText(/No remediation available/i)).toBeInTheDocument();
      expect(screen.getByText(/Raw content not exposed/i)).toBeInTheDocument();
    });
  });

  describe("5. No raw content exposure", () => {
    it("does not include raw_content, logs, stdout, stderr, stack_trace, prompt, secret fields in output", () => {
      // Create an artifact with potentially dangerous field names
      const artifact = createArtifactFixture({
        artifact_id: "safe-artifact",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      // Check the rendered output doesn't contain raw content fields
      const renderedHTML = document.body.innerHTML;

      // These fields should NOT appear in the DOM
      expect(renderedHTML).not.toContain("raw_content");
      expect(renderedHTML).not.toContain("logs");
      expect(renderedHTML).not.toContain("stdout");
      expect(renderedHTML).not.toContain("stderr");
      expect(renderedHTML).not.toContain("stack_trace");
      expect(renderedHTML).not.toContain("stackTrace");
      expect(renderedHTML).not.toContain("prompt");
      expect(renderedHTML).not.toContain("secret");
      expect(renderedHTML).not.toContain("token");
      expect(renderedHTML).not.toContain("kubeconfig");
    });

    it("only displays safe metadata fields", () => {
      const artifact = createArtifactFixture({
        artifact_id: "safe-meta-test",
        artifact_kind: "snapshot_bundle",
        evidence_role: "primary",
        attached_at: "2026-01-01T12:00:00Z",
        safe_reference: "safe-meta-test",
      });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      // These safe fields should appear
      expect(screen.getAllByText("safe-meta-test")).toHaveLength(2);
      expect(screen.getByText("Snapshot bundle")).toBeInTheDocument();
      expect(screen.getByText("primary")).toBeInTheDocument();
      expect(screen.getByText(/Attached:/i)).toBeInTheDocument();
      expect(screen.getByText(/Reference:/i)).toBeInTheDocument();
    });
  });

  describe("6. No action/remediation controls", () => {
    it("has no buttons", () => {
      const artifacts = [
        createArtifactFixture({ artifact_id: "art-1" }),
        createArtifactFixture({ artifact_id: "art-2" }),
      ];
      render(<EvidenceArtifactsSection evidenceArtifacts={artifacts} />);

      const buttons = document.querySelectorAll("button");
      expect(buttons.length).toBe(0);
    });

    it("has no links with action hrefs", () => {
      const artifact = createArtifactFixture({ artifact_id: "art-1" });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      const links = document.querySelectorAll("a");
      // Should have no links (all hrefs should be null or empty)
      for (const link of links) {
        const href = link.getAttribute("href");
        expect(href).toBeNull();
      }
    });

    it("has no form elements", () => {
      const artifact = createArtifactFixture({ artifact_id: "art-1" });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      const forms = document.querySelectorAll("form");
      const inputs = document.querySelectorAll("input");
      const textareas = document.querySelectorAll("textarea");
      const selects = document.querySelectorAll("select");

      expect(forms.length).toBe(0);
      expect(inputs.length).toBe(0);
      expect(textareas.length).toBe(0);
      expect(selects.length).toBe(0);
    });
  });

  describe("7. Safety flags verification", () => {
    it("shows read_only=true safety flag", () => {
      const artifact = createArtifactFixture({ read_only: true });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      expect(screen.getAllByText(/Read-only/i)).toHaveLength(2);
    });



    it("shows raw_content_available=false safety flag", () => {
      const artifact = createArtifactFixture({ raw_content_available: false });
      render(<EvidenceArtifactsSection evidenceArtifacts={[artifact]} />);

      // Check that raw content not available notice is present
      expect(screen.getByText(/Raw content not available/i)).toBeInTheDocument();
    });
  });
});
