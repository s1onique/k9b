/**
 * Demo Feature Module
 *
 * Re-exports for demo finding selection and related utilities.
 */

export {
  selectDemoFindings,
  selectHistoricalFindings,
  getCleanClusterFallback,
  containsForbiddenPhrase,
  validateFindings,
} from "./demoFindingSelection";

export type {
  DemoFindingSelectionInput,
  DemoFindingSelectionResult,
} from "./demoFindingSelection";