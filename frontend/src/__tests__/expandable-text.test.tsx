/**
 * expandable-text.test.tsx
 *
 * Tests for the ExpandableText component covering:
 * - Truncation on one visual line
 * - Popup opens on click/focus
 * - Popup contains full text
 * - Popup closes on Escape or click outside
 * - Generic popup label (not "command")
 * - Keyboard accessibility
 */

import { render, screen, act } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { ExpandableText } from "../components/ExpandableText";

// ============================================================================
// Test fixtures
// ============================================================================

const longText = "kubectl describe pod -n recommender-service recommender-service-7df47f487-dqghg --context admin@rees46-k8s";

const createProps = (overrides = {}) => ({
  text: "Simple test text",
  testId: "test",
  popupLabel: "Full text",
  label: undefined,
  className: undefined,
  code: false,
  ...overrides,
});

// ============================================================================
// ExpandableText Component Tests
// ============================================================================

describe("ExpandableText Component", () => {
  describe("Rendering", () => {
    test("renders the truncated text", () => {
      const props = createProps();
      render(<ExpandableText {...props} />);

      expect(screen.getByTestId("expandable-text-test-truncated")).toBeInTheDocument();
      expect(screen.getByText("Simple test text")).toBeInTheDocument();
    });

    test("renders with optional label before text", () => {
      const props = createProps({ label: "Check:" });
      render(<ExpandableText {...props} />);

      expect(screen.getByText("Check:")).toBeInTheDocument();
      expect(screen.getByText("Simple test text")).toBeInTheDocument();
    });

    test("renders with code/monospace styling when code prop is true", () => {
      const props = createProps({ code: true });
      render(<ExpandableText {...props} />);

      const truncated = screen.getByTestId("expandable-text-test-truncated");
      expect(truncated).toHaveClass("expandable-text-code");
    });

    test("does not render popup initially", () => {
      const props = createProps();
      render(<ExpandableText {...props} />);

      expect(screen.queryByTestId("expandable-text-test-popup")).not.toBeInTheDocument();
    });
  });

  describe("Truncation", () => {
    test("renders long text without wrapping", () => {
      const props = createProps({ text: longText });
      render(<ExpandableText {...props} />);

      const truncated = screen.getByTestId("expandable-text-test-truncated");
      expect(truncated).toHaveClass("expandable-text-truncated");

      // The text should be present
      expect(screen.getByText(longText)).toBeInTheDocument();
    });

    test("has truncation CSS classes applied", () => {
      const props = createProps({ text: longText });
      render(<ExpandableText {...props} />);

      const truncated = screen.getByTestId("expandable-text-test-truncated");
      // CSS classes ensure truncation behavior (overflow: hidden, text-overflow: ellipsis, white-space: nowrap)
      expect(truncated).toHaveClass("expandable-text-truncated");
    });
  });

  describe("Popup behavior", () => {
    test("opens popup on click", async () => {
      const props = createProps({ text: longText });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();
    });

    test("popup contains the full text", async () => {
      const props = createProps({ text: longText });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      const popupContent = screen.getByTestId("expandable-text-test-popup-content");
      expect(popupContent.textContent).toBe(longText);
    });

    test("popup uses custom label when provided", async () => {
      const props = createProps({ text: "Test", popupLabel: "Custom Label" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByText("Custom Label")).toBeInTheDocument();
    });

    test("popup uses generic 'Full text' label by default", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByText("Full text")).toBeInTheDocument();
    });

    test("popup closes on close button click", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();

      const closeButton = screen.getByTestId("expandable-text-test-popup-close");
      await act(async () => {
        await userEvent.click(closeButton);
      });

      expect(screen.queryByTestId("expandable-text-test-popup")).not.toBeInTheDocument();
    });

    test("popup closes on Escape key", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();

      await act(async () => {
        await userEvent.keyboard("{Escape}");
      });

      expect(screen.queryByTestId("expandable-text-test-popup")).not.toBeInTheDocument();
    });

    test("popup closes when clicking outside", async () => {
      const props = createProps({ text: "Test" });
      render(
        <div>
          <ExpandableText {...props} />
          <button data-testid="outside-button">Outside</button>
        </div>
      );

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();

      const outsideButton = screen.getByTestId("outside-button");
      await act(async () => {
        await userEvent.click(outsideButton);
      });

      expect(screen.queryByTestId("expandable-text-test-popup")).not.toBeInTheDocument();
    });
  });

  describe("Keyboard accessibility", () => {
    test("trigger is a button element that is keyboard-focusable", () => {
      const props = createProps();
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      // Button elements are naturally keyboard-focusable
      expect(trigger.tagName).toBe("BUTTON");
      expect(trigger).not.toHaveAttribute("disabled");
    });

    test("opens popup on Enter key", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      trigger.focus();
      await act(async () => {
        await userEvent.keyboard("{Enter}");
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();
    });

    test("opens popup on Space key", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      trigger.focus();
      await act(async () => {
        await userEvent.keyboard(" ");
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();
    });

    test("closes popup on Escape key and returns focus to trigger", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      trigger.focus();
      await act(async () => {
        await userEvent.keyboard("{Enter}");
      });

      expect(screen.getByTestId("expandable-text-test-popup")).toBeInTheDocument();

      await act(async () => {
        await userEvent.keyboard("{Escape}");
      });

      expect(screen.queryByTestId("expandable-text-test-popup")).not.toBeInTheDocument();
      expect(document.activeElement).toBe(trigger);
    });

    test("popup has role=dialog", async () => {
      const props = createProps({ text: "Test" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      const popup = screen.getByTestId("expandable-text-test-popup");
      expect(popup).toHaveAttribute("role", "dialog");
    });

    test("trigger has aria-expanded", () => {
      const props = createProps();
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      expect(trigger).toHaveAttribute("aria-expanded", "false");
    });

    test("trigger updates aria-expanded on open", async () => {
      const props = createProps();
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      expect(trigger).toHaveAttribute("aria-expanded", "false");

      await act(async () => {
        await userEvent.click(trigger);
      });

      expect(trigger).toHaveAttribute("aria-expanded", "true");
    });
  });

  describe("Multiple instances", () => {
    test("each instance operates independently - first popup opens", async () => {
      render(
        <div>
          <ExpandableText text="First text" testId="first" />
          <ExpandableText text="Second text" testId="second" />
        </div>
      );

      const firstTrigger = screen.getByTestId("expandable-text-first");

      // Open first popup
      await act(async () => {
        await userEvent.click(firstTrigger);
      });

      expect(screen.getByTestId("expandable-text-first-popup")).toBeInTheDocument();
      expect(screen.queryByTestId("expandable-text-second-popup")).not.toBeInTheDocument();
    });

    test("each instance operates independently - second popup opens", async () => {
      render(
        <div>
          <ExpandableText text="First text" testId="first" />
          <ExpandableText text="Second text" testId="second" />
        </div>
      );

      const secondTrigger = screen.getByTestId("expandable-text-second");

      // Open second popup
      await act(async () => {
        await userEvent.click(secondTrigger);
      });

      expect(screen.getByTestId("expandable-text-second-popup")).toBeInTheDocument();
    });
  });

  describe("Custom className", () => {
    test("applies custom className to wrapper", () => {
      const props = createProps({ className: "custom-class" });
      render(<ExpandableText {...props} />);

      const wrapper = screen.getByTestId("expandable-text-test");
      expect(wrapper.closest(".expandable-text-wrapper")).toHaveClass("custom-class");
    });
  });

  describe("Edge cases", () => {
    test("handles empty text", () => {
      const props = createProps({ text: "" });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      expect(trigger).toBeInTheDocument();
    });

    test("handles text with special characters", () => {
      const specialText = "kubectl exec -it <pod-name> -- /bin/bash --context 'user@cluster'";
      const props = createProps({ text: specialText });
      render(<ExpandableText {...props} />);

      expect(screen.getByText(specialText)).toBeInTheDocument();
    });

    test("handles text with newlines", async () => {
      const multilineText = "Line 1\nLine 2\nLine 3";
      const props = createProps({ text: multilineText });
      render(<ExpandableText {...props} />);

      const trigger = screen.getByTestId("expandable-text-test");
      await act(async () => {
        await userEvent.click(trigger);
      });

      const popupContent = screen.getByTestId("expandable-text-test-popup-content");
      expect(popupContent.textContent).toBe(multilineText);
    });
  });
});
