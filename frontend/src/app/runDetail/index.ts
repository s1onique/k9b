/**
 * runDetail/index.ts - Barrel export for Run Detail module.
 *
 * @module app/runDetail
 */

// Model types
export type {
  RunDetailModel,
  RunDetailPanelState,
  RunDetailTabId,
  DebugDiagnosticsState,
  Msg,
  Cmd,
  UpdateResult,
} from "./runDetailModel";

export { initialModel, createInitialModel } from "./runDetailModel";

// Update function
export { update, createInitialModel as createUpdateInitialModel } from "./runDetailUpdate";

// Effects
export { executeEffect, drainEffects } from "./runDetailEffects";
export type { EffectContext } from "./runDetailEffects";

// Controller hook
export { useRunDetailController } from "./useRunDetailController";
export type {
  UseRunDetailControllerOptions,
  UseRunDetailControllerResult,
} from "./useRunDetailController";
