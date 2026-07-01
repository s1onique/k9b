/**
 * useQueueState hook — thin compatibility façade.
 *
 * Re-exports the hook and types from the queueState module.
 * This file exists to preserve existing import paths.
 *
 * @deprecated Import from `./queueState/useQueueState` for new code.
 */
export { useQueueState } from "./queueState/useQueueState";
export { QUEUE_VIEW_STORAGE_KEY } from "./queueState/constants";

export type {
  NextCheckQueueStatus,
  QueueFocusMode,
  QueueSortOption,
  QueueViewState,
  QueueGroup,
  UseQueueStateParams,
  UseQueueStateResult,
  UseQueueStateReturn,
} from "./queueState/types";
