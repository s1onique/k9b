/**
 * IncidentSnapshotPanel review packet generation tests
 *
 * Verifies:
 * - Generate review packet button visibility after capture
 * - API call to generateIncidentReviewPacket
 * - Success state with copy/download buttons
 * - Error handling for packet generation failures
 * - Reset button clears packet state
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentSnapshotPanel } from "../components/IncidentSnapshotPanel";
import { mockSuccessResponse, mockPacketResponse } from "./incident-snapshot-panel.fixtures";

// Mock the API functions
vi.mock("../api", () => ({
  captureIncidentSnapshot: vi.fn(),
  generateIncidentReviewPacket: vi.fn(),
}));

import { captureIncidentSnapshot, generateIncidentReviewPacket } from "../api";

describe("Review packet generation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Generate review packet button after successful snapshot capture", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    // Check Generate review packet button is visible
    expect(screen.getByRole("button", { name: /generate review packet/i })).toBeInTheDocument();
  });

  it("calls generateIncidentReviewPacket with the captured bundle", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    vi.mocked(generateIncidentReviewPacket).mockResolvedValueOnce(mockPacketResponse);

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    // Verify generateIncidentReviewPacket was called with the bundle
    expect(generateIncidentReviewPacket).toHaveBeenCalledTimes(1);
    expect(generateIncidentReviewPacket).toHaveBeenCalledWith({
      bundle: mockSuccessResponse.bundle,
      format: "markdown",
    });
  });

  it("shows Copy review packet and Download review packet.md on success", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    vi.mocked(generateIncidentReviewPacket).mockResolvedValueOnce(mockPacketResponse);

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Review packet generated/i)).toBeInTheDocument();
    });

    // Check copy and download buttons are visible
    expect(screen.getByRole("button", { name: /copy review packet/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download review packet\.md/i })).toBeInTheDocument();
  });

  it("renders error message when packet generation fails", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    vi.mocked(generateIncidentReviewPacket).mockRejectedValueOnce(
      new Error("Bundle processing failed")
    );

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Packet generation failed/i)).toBeInTheDocument();
    });

    // Check error message is displayed
    expect(screen.getByText(/Bundle processing failed/i)).toBeInTheDocument();
  });

  it("renders error from API response body", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    vi.mocked(generateIncidentReviewPacket).mockResolvedValueOnce({
      bundle_id: "default-20260101-120000",
      packet: "",
      format: "markdown",
      error: "Invalid bundle structure",
    });

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Packet generation failed/i)).toBeInTheDocument();
    });

    // Check error from response body is displayed
    expect(screen.getByText(/Invalid bundle structure/i)).toBeInTheDocument();
  });

  it("Reset button clears packet state", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    vi.mocked(generateIncidentReviewPacket).mockResolvedValueOnce(mockPacketResponse);

    render(<IncidentSnapshotPanel namespace="default" />);

    // Capture bundle
    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    // Generate packet
    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Review packet generated/i)).toBeInTheDocument();
    });

    // Click new capture (reset) button
    const resetButton = screen.getByRole("button", { name: /new capture/i });
    await act(async () => {
      await user.click(resetButton);
    });

    await waitFor(() => {
      // Capture button should be back
      expect(screen.getByRole("button", { name: /capture incident bundle/i })).toBeInTheDocument();
    });

    // Packet state should be cleared (no packet success/error messages)
    expect(screen.queryByText(/Review packet generated/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Packet generation failed/i)).not.toBeInTheDocument();
  });

  it("shows loading state while generating packet", async () => {
    const user = userEvent.setup();
    vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);
    // Create a promise that doesn't resolve immediately
    vi.mocked(generateIncidentReviewPacket).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockPacketResponse), 1000))
    );

    render(<IncidentSnapshotPanel namespace="default" />);

    const captureButton = screen.getByRole("button", { name: /capture incident bundle/i });
    await act(async () => {
      await user.click(captureButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
    });

    const generateButton = screen.getByRole("button", { name: /generate review packet/i });
    await act(async () => {
      await user.click(generateButton);
    });

    // Loading state should be visible
    expect(screen.getByText(/Generating review packet/i)).toBeInTheDocument();
  });
});
