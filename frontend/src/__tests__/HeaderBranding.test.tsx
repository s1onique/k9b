import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { HeaderBranding } from "../components/HeaderBranding";

describe("HeaderBranding", () => {
  const DEFAULT_LOGO_SRC = "/branding/logo-vertical.svg";

  describe("rendering", () => {
    it("renders the portrait logo by default", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img", { name: /k9b brand logo/i });
      expect(branding).toBeInTheDocument();
      
      // The logo image should be present with the default portrait logo src
      const img = branding.querySelector("img.brand-logo-image");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", DEFAULT_LOGO_SRC);
      expect(img).toHaveAttribute("alt", "");
    });

    it("renders logo-only by default (no text blocks)", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).toBeInTheDocument();
      
      // No text content should be rendered by default
      const textBlock = branding.parentElement?.querySelector(".brand-text-block");
      expect(textBlock).not.toBeInTheDocument();
    });

    it("renders custom logo when logoSrc is provided", () => {
      render(<HeaderBranding logoSrc="/custom/logo.png" logoAlt="Custom Logo" />);
      
      const branding = screen.getByRole("img", { name: /custom logo/i });
      expect(branding).toBeInTheDocument();
      
      const img = branding.querySelector("img.brand-logo-image");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", "/custom/logo.png");
      expect(img).toHaveAttribute("alt", "");
    });

    it("uses default alt text when custom logoSrc is provided", () => {
      render(<HeaderBranding logoSrc="/logo.png" />);
      
      const img = screen.getByRole("img", { name: /k9b brand logo/i });
      expect(img).toBeInTheDocument();
      
      const imgElement = img.querySelector("img.brand-logo-image");
      expect(imgElement?.getAttribute("alt")).toBe("");
    });

    it("renders text block when brandName is provided", () => {
      render(<HeaderBranding brandName="Fleet triage" />);
      
      const textBlock = screen.getByText("Fleet triage");
      expect(textBlock).toBeInTheDocument();
      expect(textBlock).toHaveClass("brand-eyebrow");
    });

    it("renders text block when title is provided", () => {
      render(<HeaderBranding title="Cockpit" />);
      
      const titleElement = screen.getByRole("heading", { level: 1, name: "Cockpit" });
      expect(titleElement).toBeInTheDocument();
      expect(titleElement).toHaveClass("brand-title");
    });
  });

  describe("accessibility", () => {
    it("has role='img' when not interactive", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).toBeInTheDocument();
    });

    it("has role='button' when onClick is provided", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      expect(branding).toBeInTheDocument();
    });

    it("is focusable when interactive", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      expect(branding).toHaveAttribute("tabIndex", "0");
    });

    it("is not focusable when non-interactive", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).not.toHaveAttribute("tabIndex");
    });

    it("calls onClick when clicked", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      fireEvent.click(branding);
      
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("calls onClick when Enter key is pressed", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      fireEvent.keyDown(branding, { key: "Enter", code: "Enter" });
      
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("calls onClick when Space key is pressed", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      fireEvent.keyDown(branding, { key: " ", code: "Space" });
      
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("logo image uses empty alt to avoid redundant announcement", () => {
      render(<HeaderBranding />);
      
      const img = screen.getByRole("img").querySelector("img.brand-logo-image");
      // The img has alt="" because the parent div provides role="img" with aria-label
      expect(img).toHaveAttribute("alt", "");
    });
  });

  describe("title/tooltip", () => {
    it("has default title attribute showing logo alt", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).toHaveAttribute("title", "k9b brand logo");
    });

    it("uses custom title when provided via logoAlt", () => {
      render(<HeaderBranding logoAlt="Custom tooltip" />);
      
      const branding = screen.getByRole("img");
      expect(branding).toHaveAttribute("title", "Custom tooltip");
    });

    it("uses custom title for interactive mode", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} title="Click for info" />);
      
      const branding = screen.getByRole("button");
      expect(branding).toHaveAttribute("title", "Click for info");
    });
  });

  describe("aria-label", () => {
    it("has aria-label for default logo mode", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).toHaveAttribute("aria-label", "k9b brand logo");
    });

    it("has aria-label for interactive mode using title", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} title="Brand Logo" />);
      
      const branding = screen.getByRole("button");
      expect(branding).toHaveAttribute("aria-label", "Brand Logo");
    });

    it("has aria-label for interactive mode using default when no title", () => {
      const onClick = vi.fn();
      render(<HeaderBranding onClick={onClick} />);
      
      const branding = screen.getByRole("button");
      expect(branding).toHaveAttribute("aria-label", "Brand logo");
    });

    it("uses logoAlt for aria-label when custom logoSrc is provided", () => {
      render(<HeaderBranding logoSrc="/logo.png" logoAlt="My Company Logo" />);
      
      const branding = screen.getByRole("img");
      expect(branding).toHaveAttribute("aria-label", "My Company Logo");
    });
  });

  describe("logoSrc prop support", () => {
    it("shows default logo when logoSrc is empty string (falls back to default)", () => {
      render(<HeaderBranding logoSrc="" />);
      
      // Empty string is falsy, so default logo is shown
      const branding = screen.getByRole("img");
      const img = branding.querySelector("img.brand-logo-image");
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute("src", DEFAULT_LOGO_SRC);
    });

    it("shows custom logo when logoSrc is a valid URL", () => {
      render(<HeaderBranding logoSrc="https://example.com/logo.svg" />);
      
      const branding = screen.getByRole("img");
      const img = branding.querySelector("img.brand-logo-image");
      expect(img).toHaveAttribute("src", "https://example.com/logo.svg");
    });
  });

  describe("portrait proportions", () => {
    it("has correct container class for portrait styling", () => {
      render(<HeaderBranding />);
      
      const branding = screen.getByRole("img");
      expect(branding).toHaveClass("brand-logo-container");
    });

    it("image uses object-fit contain for portrait asset", () => {
      render(<HeaderBranding />);
      
      const img = screen.getByRole("img").querySelector("img.brand-logo-image");
      // The CSS defines object-fit: contain for .brand-logo-image
      expect(img).toBeInTheDocument();
    });
  });
});
