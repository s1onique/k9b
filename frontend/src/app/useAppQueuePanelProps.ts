/**
 * App queue panel props hook - extracts prop construction from App.tsx.
 *
 * This hook wraps buildQueuePanelProps for use in App.tsx, creating a clean
 * seam without changing behavior.
 *
 * @module app
 */
import {
  buildQueuePanelProps,
  type BuildQueuePanelPropsArgs,
} from "../components/QueuePanel/buildQueuePanelProps";

// Re-export the builder arg type for consumers
export type { BuildQueuePanelPropsArgs };

/**
 * Build queue panel props for App.tsx.
 *
 * @param args - Same arguments as buildQueuePanelProps
 * @returns QueuePanelProps ready to pass to WorkNextChecksLane
 */
export function useAppQueuePanelProps(
  args: BuildQueuePanelPropsArgs
): ReturnType<typeof buildQueuePanelProps> {
  return buildQueuePanelProps(args);
}
