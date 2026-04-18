/**
 * Header Branding Component
 *
 * Provides the brand mark area in the app header.
 * Renders the portrait logo asset by default from /branding/logo-vertical.svg.
 * The logo is treated as a decorative brand mark (aria-hidden on the img element).
 *
 * Default usage shows only the portrait logo mark. Text (brandName/title)
 * is optional and only renders when explicitly provided.
 *
 * Accessibility:
 * - Logo image is decorative (aria-hidden), parent div provides role="img" with aria-label
 * - When interactive (onClick provided): role="button" with aria-label from title or default
 * - Page title semantics are managed elsewhere
 */

import React from "react";

// Default portrait logo asset - 1024x1536 (2:3 aspect ratio)
const DEFAULT_LOGO_SRC = "/branding/logo-vertical.svg";

export interface HeaderBrandingProps {
  /** URL to a logo image to display. Defaults to portrait logo asset. */
  logoSrc?: string;
  /** Alt text for the logo image. */
  logoAlt?: string;
  /** Brand name to display as eyebrow text. */
  brandName?: string;
  /** Main title to display. */
  title?: string;
  /** Click handler for interactive mode. */
  onClick?: () => void;
}

export const HeaderBranding: React.FC<HeaderBrandingProps> = ({
  logoSrc,
  logoAlt = "k9b brand logo",
  brandName,
  title,
  onClick,
}) => {
  const isInteractive = Boolean(onClick);
  // Use default logo when logoSrc is undefined or empty; empty string means no logo
  const effectiveLogoSrc = logoSrc || DEFAULT_LOGO_SRC;
  const isLogoProvided = effectiveLogoSrc !== "";
  const isTitleProvided = title !== undefined;

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick?.();
    }
  };

  // Compute aria-label based on mode
  const ariaLabel = isInteractive
    ? (isTitleProvided ? title : "Brand logo")
    : (isLogoProvided ? logoAlt : "Brand logo");

  // Compute title attribute - prefer explicit title prop when provided, fall back to logoAlt
  const tooltipTitle = isTitleProvided ? title : logoAlt;

  return (
    <div className="brand-logo-block">
      <div
        className="brand-logo-container"
        role={isInteractive ? "button" : "img"}
        aria-label={ariaLabel}
        title={tooltipTitle}
        onClick={onClick}
        tabIndex={isInteractive ? 0 : undefined}
        onKeyDown={isInteractive ? handleKeyDown : undefined}
      >
        <span className="brand-logo-mark" aria-hidden="true">
          {isLogoProvided && (
            <img 
              src={effectiveLogoSrc} 
              alt="" 
              className="brand-logo-image" 
            />
          )}
        </span>
      </div>
      {(brandName || title) && (
        <div className="brand-text-block">
          {brandName && <p className="brand-eyebrow">{brandName}</p>}
          <h1 className="brand-title">{title}</h1>
        </div>
      )}
    </div>
  );
};

export default HeaderBranding;
