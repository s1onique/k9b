# Token hygiene

Use rtk for routine noisy shell commands and verification commands where compact output is enough.

When debugging failures, regressions, flaky tests, import errors, or log-sensitive behavior:
- first use compact rtk output to identify the failing area;
- then rerun the exact failing command without rtk when raw output may contain the clue;
- never treat compressed output as complete evidence for subtle failures.
