/**
 * Shared safety test utilities for verifying no-remediation UI contracts.
 *
 * These utilities ensure consistent safety deny-lists across test files
 * and prevent drift in the remediation-safety invariant.
 */

/**
 * Regex pattern for forbidden remediation/action button text.
 * Matches words that indicate mutation, remediation, or unsafe actions.
 */
export const FORBIDDEN_REMEDIATION_BUTTON_TEXT = /apply|delete|patch|scale|restart|rollout|remediate|fix|resolve automatically|exec|mutate/i;

/**
 * Verifies that a button does not contain forbidden remediation text.
 */
export function expectButtonIsNotRemediation(
  button: HTMLElement,
): void {
  expect(button).not.toHaveTextContent(FORBIDDEN_REMEDIATION_BUTTON_TEXT);
}

/**
 * Verifies all buttons are safe (contain no forbidden remediation text).
 * Call this after asserting specific safe buttons exist.
 */
export function expectAllButtonsAreSafe(
  buttons: HTMLElement[],
): void {
  for (const button of buttons) {
    expectButtonIsNotRemediation(button);
  }
}
