# Dashboard summary UI correction — 2026-11-17

The owner's screenshot reproduced a presentation and interpretation gap missed by
the earlier 17-route navigation smoke. Build success and page rendering had not
established visual acceptance of this particular summary panel.

## Corrected behavior

- Replaced the isolated black/translucent cards and raw diagnostic banner with
  semantic Obsidian/Warm surfaces, consistent spacing, readable timestamps and
  VI/EN product text. The watermark no longer crosses the card contents.
- Missing health configuration is explained without implying an outage or a
  successful assessment. Expired measurements count as unknown even when their
  historical status was up. No health endpoint was invented or enabled.
- Online workers are shown as an absolute count. Older heartbeat records are
  disclosed separately with an explanation; registered process history is not
  presented as the expected worker capacity. No worker records were deleted.
- Severity labels/counts use aligned columns and fixed tracks. Counts remain API
  values, including the single open synthetic finding in the acceptance lab.
- Daily activity has separate new/reopened/verified-fixed series, an explicit
  legend, date labels and matching observation-filter links. Previously a combined
  new+reopened bar always opened only the new filter.
- Refresh avoids overlapping requests, exposes loading/offline/cached states and
  keeps unavailable data distinct from an empty successful result.

## Acceptance

Frontend regressions render the actual component with React/Next Link: health
configuration, old worker records, each outcome link, empty/cached/English states
and expired healthy measurements. Final frontend: **16 passed**, TypeScript,
lint and static export passed. Exact commands/results are in the
[validation manifest](DASHBOARD_UI_FIX_VALIDATION.json). API contract audit:
124 matched calls, zero missing or method mismatches.
No backend/scanner/database behavior or dependency was changed.

Actual browser acceptance used the existing isolated lab on port 8082. Refresh
updated the server timestamp; the new-events bar opened four findings for
2026-11-16, and the fixed-events bar opened three resolved findings for 2026-11-17.
The worker card showed one online worker and three inactive historical records.
VI/EN text, both themes and 390×844 mobile layouts were inspected. Mobile document
width/scrollWidth was 385/385 and the summary panel 353/353. Browser warning/error
capture was empty. The viewport override was reset and the dashboard kept open.

Selected synthetic screenshots are in `screenshots/dashboard-ui-2026-11-17/`.
Detailed local captures are in
`storage/assessment-lab/evidence/dashboard-ui-2026-11-17/` (ignored runtime data).
The lab asset still has no approved health endpoint, so unknown health remains the
correct result. These changes accept the reported block, not every legacy chart
or all application accessibility. The changes remain local and uncommitted.
