/**
 * PastRunNotice.tsx
 *
 * Displays notices about past runs and freshness warnings.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

import dayjs from "dayjs";

// Format age duration (abbreviated)
const formatAgeDuration = (minutes: number): string => {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
};

export interface PastRunNoticeProps {
  /** Whether the selected run is the latest run */
  isSelectedRunLatest: boolean;
  /** Whether the run timestamp is considered fresh (< 10 minutes) */
  runFresh: boolean;
  /** Run timestamp in ISO format */
  runTimestamp: string;
}

export const PastRunNotice = ({
  isSelectedRunLatest,
  runFresh,
  runTimestamp,
}: PastRunNoticeProps) => {
  const runAgeMinutes = Math.floor(dayjs().diff(dayjs(runTimestamp), "minute"));

  // Case 1: Past run selected - always show past run notice
  if (!isSelectedRunLatest) {
    return (
      <div className="alert alert-inline alert-past-run">
        This is a past run collected {formatAgeDuration(runAgeMinutes)} ago.
      </div>
    );
  }

  // Case 2: Latest run selected but stale - show freshness warning
  if (isSelectedRunLatest && !runFresh) {
    return (
      <div className="alert alert-inline">
        Latest run is {runAgeMinutes} minute{runAgeMinutes === 1 ? "" : "s"} old; ensure the scheduler is running.
      </div>
    );
  }

  // Case 3: Latest run and fresh - no notice
  return null;
};