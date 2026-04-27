/**
 * CommandText.tsx
 *
 * Reusable component for displaying command text with truncation and accessible popup.
 *
 * Features:
 * - Renders command text on exactly one visual line with CSS truncation/ellipsis
 * - Shows a keyboard-accessible popup/popover with the full command text on click/focus
 * - Popup can wrap text and is readable
 * - Escape key closes the popup
 * - Focus is managed safely
 *
 * Usage:
 * <CommandText command="kubectl logs -n monitoring ... --context rees-naumen" />
 */

import { useState, useRef, useEffect, useCallback } from "react";

export interface CommandTextProps {
  /** The command text to display */
  command: string;
  /** Optional test ID for the command element */
  testId?: string;
}

/**
 * Truncatable command text with accessible popup for full text display.
 * 
 * The visible text shows exactly one line with ellipsis for overflow.
 * The popup shows the full command text and can wrap.
 */
export const CommandText = ({ command, testId }: CommandTextProps) => {
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const popupRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Close popup on Escape key
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isPopupOpen) {
        setIsPopupOpen(false);
        // Return focus to trigger when popup closes
        triggerRef.current?.focus();
      }
    };

    if (isPopupOpen) {
      document.addEventListener("keydown", handleKeyDown);
      // Focus the popup for keyboard navigation
      popupRef.current?.focus();
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isPopupOpen]);

  // Close popup when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        isPopupOpen &&
        popupRef.current &&
        triggerRef.current &&
        !popupRef.current.contains(event.target as Node) &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsPopupOpen(false);
      }
    };

    if (isPopupOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isPopupOpen]);

  const openPopup = useCallback(() => {
    setIsPopupOpen(true);
  }, []);

  const closePopup = useCallback(() => {
    setIsPopupOpen(false);
    triggerRef.current?.focus();
  }, []);

  const handleTriggerKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (isPopupOpen) {
          closePopup();
        } else {
          openPopup();
        }
      }
    },
    [isPopupOpen, openPopup, closePopup]
  );

  return (
    <div className="command-text-wrapper">
      <button
        ref={triggerRef}
        type="button"
        className="command-text-trigger"
        onClick={openPopup}
        onKeyDown={handleTriggerKeyDown}
        aria-expanded={isPopupOpen}
        aria-haspopup="dialog"
        aria-label={`Expand command: ${command}`}
        title="Click to see full command"
        data-testid={testId ? `command-text-${testId}` : undefined}
      >
        <code
          className="command-text-truncated"
          data-testid={testId ? `command-text-${testId}-truncated` : undefined}
        >
          {command}
        </code>
      </button>

      {isPopupOpen && (
        <div
          ref={popupRef}
          className="command-text-popup"
          role="dialog"
          aria-label="Full command text"
          tabIndex={-1}
          data-testid={testId ? `command-text-${testId}-popup` : undefined}
        >
          <div className="command-text-popup-header">
            <span className="command-text-popup-label">Full command</span>
            <button
              type="button"
              className="command-text-popup-close"
              onClick={closePopup}
              aria-label="Close popup"
              data-testid={testId ? `command-text-${testId}-popup-close` : undefined}
            >
              ×
            </button>
          </div>
          <pre
            className="command-text-popup-content"
            data-testid={testId ? `command-text-${testId}-popup-content` : undefined}
          >
            {command}
          </pre>
        </div>
      )}
    </div>
  );
};

export default CommandText;
