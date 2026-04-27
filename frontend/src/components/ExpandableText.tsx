/**
 * ExpandableText.tsx
 *
 * Reusable generic component for displaying text with truncation and accessible popup.
 *
 * Features:
 * - Renders text on exactly one visual line with CSS truncation/ellipsis
 * - Shows a keyboard-accessible popup/popover with the full text on click/focus
 * - Popup can wrap text and is readable
 * - Escape key closes the popup
 * - Focus is managed safely
 * - Generic enough for titles, check labels, commands, or other text
 *
 * Usage:
 * <ExpandableText text="kubectl logs -n monitoring ... --context rees-naumen" label="Check label" />
 * <ExpandableText text={item.title} label={item.workstream} popupLabel="Full check text" />
 */

import { useState, useRef, useEffect, useCallback } from "react";

export interface ExpandableTextProps {
  /** The text to display and truncate */
  text: string;
  /** Optional label to show before the text (e.g., workstream badge context) */
  label?: string;
  /** Optional custom popup label (default: "Full text") */
  popupLabel?: string;
  /** Optional test ID for the element */
  testId?: string;
  /** Optional CSS class for the wrapper */
  className?: string;
  /** Whether to render as code/monospace (default: false for titles) */
  code?: boolean;
}

/**
 * Truncatable text with accessible popup for full text display.
 * 
 * The visible text shows exactly one line with ellipsis for overflow.
 * The popup shows the full text and can wrap.
 */
export const ExpandableText = ({ text, label, popupLabel = "Full text", testId, className, code }: ExpandableTextProps) => {
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

  const wrapperClass = className ? `expandable-text-wrapper ${className}` : "expandable-text-wrapper";
  const textClass = code ? "expandable-text-truncated expandable-text-code" : "expandable-text-truncated";

  return (
    <span className={wrapperClass}>
      {label && <span className="expandable-text-label">{label}</span>}
      <button
        ref={triggerRef}
        type="button"
        className="expandable-text-trigger"
        onClick={openPopup}
        onKeyDown={handleTriggerKeyDown}
        aria-expanded={isPopupOpen}
        aria-haspopup="dialog"
        aria-label={`Expand: ${text}`}
        title="Click to see full text"
        data-testid={testId ? `expandable-text-${testId}` : undefined}
      >
        <span
          className={textClass}
          data-testid={testId ? `expandable-text-${testId}-truncated` : undefined}
        >
          {text}
        </span>
      </button>

      {isPopupOpen && (
        <div
          ref={popupRef}
          className="expandable-text-popup"
          role="dialog"
          aria-label={popupLabel}
          tabIndex={-1}
          data-testid={testId ? `expandable-text-${testId}-popup` : undefined}
        >
          <div className="expandable-text-popup-header">
            <span className="expandable-text-popup-label">{popupLabel}</span>
            <button
              type="button"
              className="expandable-text-popup-close"
              onClick={closePopup}
              aria-label="Close popup"
              data-testid={testId ? `expandable-text-${testId}-popup-close` : undefined}
            >
              ×
            </button>
          </div>
          <pre
            className="expandable-text-popup-content"
            data-testid={testId ? `expandable-text-${testId}-popup-content` : undefined}
          >
            {text}
          </pre>
        </div>
      )}
    </span>
  );
};

export default ExpandableText;
