/**
 * IncidentSnapshotPanel tests
 *
 * Verifies:
 * - Capture action sends POST /api/incidents/snapshot with namespace and since_hours
 * - Success response renders summary counts and bundle_id
 * - Failure response renders sanitized error
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentSnapshotPanel } from "../components/IncidentSnapshotPanel";

// Mock the API functions
vi.mock("../api", () => ({
  captureIncidentSnapshot: vi.fn(),
  generateIncidentReviewPacket: vi.fn(),
}));

import { captureIncidentSnapshot, generateIncidentReviewPacket } from "../api";

const mockSuccessResponse = {
  bundle_id: "default-20260101-120000",
  captured_at: "2026-01-01T12:00:00Z",
  namespace: "default",
  summary: {
    total_pods: 10,
    failing_pods_count: 2,
    total_deployments: 3,
    total_events: 25,
    symptoms_count: 3,
  },
  bundle: {
    metadata: {
      bundle_id: "default-20260101-120000",
      namespace: "default",
    },
    pods: [],
    events: [],
    deployments: [],
    symptoms: [],
  },
};

const mockErrorResponse = {
  bundle_id: "",
  captured_at: "2026-01-01T12:00:00Z",
  namespace: "default",
  summary: {
    total_pods: 0,
    failing_pods_count: 0,
    total_deployments: 0,
    total_events: 0,
    symptoms_count: 0,
  },
  error: "Namespace not found",
};

describe("IncidentSnapshotPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Capture action sends correct request", () => {
    it("sends POST /api/incidents/snapshot with namespace and since_hours when namespace is provided", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(
        <IncidentSnapshotPanel namespace="monitoring" defaultNamespace="default" />
      );

      // Click the capture button
      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      // Verify API was called with correct parameters
      expect(captureIncidentSnapshot).toHaveBeenCalledTimes(1);
      expect(captureIncidentSnapshot).toHaveBeenCalledWith({
        namespace: "monitoring",
        since_hours: 2,
      });
    });

    it("uses input namespace when no namespace prop provided", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace={null} defaultNamespace="default" />);

      // Type namespace in input
      const input = screen.getByPlaceholderText(/e\.g\., default/i);
      await act(async () => {
        await user.clear(input);
        await user.type(input, "my-namespace");
      });

      // Click the capture button
      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      // Verify API was called with input namespace
      expect(captureIncidentSnapshot).toHaveBeenCalledWith({
        namespace: "my-namespace",
        since_hours: 2,
      });
    });
  });

  describe("Success response renders summary counts and bundle_id", () => {
    it("renders bundle_id on success", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
      });

      // Check bundle_id is displayed
      expect(screen.getByText(mockSuccessResponse.bundle_id)).toBeInTheDocument();
    });

    it("renders summary counts on success", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
      });

      // Check summary counts are displayed - count items in the summary list
      const listItems = screen.getAllByRole('listitem');
      const listText = listItems.map(li => li.textContent || '');
      expect(listText.some(t => t.includes('Total pods') && t.includes('10'))).toBe(true);
      expect(listText.some(t => t.includes('Failing pods') && t.includes('2'))).toBe(true);
      expect(listText.some(t => t.includes('Total deployments') && t.includes('3'))).toBe(true);
      expect(listText.some(t => t.includes('Total events') && t.includes('25'))).toBe(true);
      expect(listText.some(t => t.includes('Symptoms') && t.includes('3'))).toBe(true);
    });

    it("renders namespace and captured_at on success", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
      });

      // Check namespace is displayed
      expect(screen.getByText(/Namespace/)).toBeInTheDocument();
      expect(screen.getByText("default")).toBeInTheDocument();
    });
  });

  describe("Failure response renders sanitized error", () => {
    it("renders error message when API returns error in response body", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockErrorResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Capture failed/i)).toBeInTheDocument();
      });

      // Check error message is displayed
      expect(screen.getByText(/Namespace not found/i)).toBeInTheDocument();
    });

    it("renders error message when API throws", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockRejectedValueOnce(
        new Error("Connection refused")
      );

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Capture failed/i)).toBeInTheDocument();
      });

      // Check error message is displayed
      expect(screen.getByText(/Connection refused/i)).toBeInTheDocument();
    });

    it("shows try again button on error", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockRejectedValueOnce(
        new Error("Test error")
      );

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
      });
    });
  });

  describe("Loading state", () => {
    it("shows loading message while capturing", async () => {
      const user = userEvent.setup();
      // Create a promise that doesn't resolve immediately
      vi.mocked(captureIncidentSnapshot).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockSuccessResponse), 1000))
      );

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      // Loading state should be visible
      expect(screen.getByText(/Capturing incident snapshot/i)).toBeInTheDocument();
    });
  });

  describe("Bundle exposure", () => {
    it("shows copy and download buttons on success", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
      });

      // Check copy and download buttons are visible
      expect(screen.getByRole("button", { name: /copy bundle json/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /download bundle json/i })).toBeInTheDocument();
    });

    it("shows new capture button on success", async () => {
      const user = userEvent.setup();
      vi.mocked(captureIncidentSnapshot).mockResolvedValueOnce(mockSuccessResponse);

      render(<IncidentSnapshotPanel namespace="default" />);

      const button = screen.getByRole("button", { name: /capture incident bundle/i });
      await act(async () => {
        await user.click(button);
      });

      await waitFor(() => {
        expect(screen.getByText(/Bundle captured/i)).toBeInTheDocument();
      });

      // Check new capture button is visible
      expect(screen.getByRole("button", { name: /new capture/i })).toBeInTheDocument();
    });
  });

  describe("Review packet generation", () => {
    const mockPacketResponse = {
      bundle_id: "default-20260101-120000",
      packet: "# k9b Incident Review Packet\n\n**Generated by k9b**",
      format: "markdown",
    };

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
});
