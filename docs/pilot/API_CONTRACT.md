# Hợp đồng API · console ↔ FastAPI (sinh tự động)

Sinh bởi `python scripts/contract_audit.py --write` từ OpenAPI của app thật và mã nguồn `frontend/src`.

- Operation trong OpenAPI: **146**
- Lời gọi từ client: **115** · khớp 115 · thiếu route 0 · sai method 0 · động 0

## Lời gọi từ client

| Trạng thái | Method | Path client | Route server | Nơi gọi |
|---|---|---|---|---|
| ok | GET | `/alerts` | GET /alerts | `frontend/src/lib/api.ts:816` (client) |
| ok | POST | `/alerts/read-all` | POST /alerts/read-all | `frontend/src/lib/api.ts:824` (client) |
| ok | POST | `/alerts/{x}/read` | POST /alerts/{id}/read | `frontend/src/lib/api.ts:820` (client) |
| ok | GET | `/assets` | GET /assets | `frontend/src/lib/api.ts:465` (client) |
| ok | GET | `/assets` | GET /assets | `frontend/src/lib/api.ts:473` (client) |
| ok | POST | `/assets` | POST /assets | `frontend/src/lib/api.ts:477` (client) |
| ok | POST | `/assets/bulk-import` | POST /assets/bulk-import | `frontend/src/lib/api.ts:484` (client) |
| ok | POST | `/assets/bulk-preview` | POST /assets/bulk-preview | `frontend/src/app/assets/page.tsx:769` (page) |
| ok | GET | `/assets/{x}` | GET /assets/{asset_id} | `frontend/src/lib/api.ts:491` (client) |
| ok | DELETE | `/assets/{x}` | DELETE /assets/{asset_id} | `frontend/src/lib/api.ts:514` (client) |
| ok | POST | `/assets/{x}/artifacts` | POST /assets/{asset_id}/artifacts | `frontend/src/lib/api.ts:912` (client) |
| ok | PUT | `/assets/{x}/health-check` | PUT /assets/{asset_id}/health-check | `frontend/src/lib/api.ts:963` (client) |
| ok | GET | `/assets/{x}/summary` | GET /assets/{asset_id}/summary | `frontend/src/lib/api.ts:495` (client) |
| ok | POST | `/assets/{x}/verify` | POST /assets/{asset_id}/verify | `frontend/src/lib/api.ts:507` (client) |
| ok | GET | `/auth/audit` | GET /auth/audit | `frontend/src/app/users/page.tsx:51` (page) |
| ok | POST | `/auth/login` | POST /auth/login | `frontend/src/lib/api.ts:972` (client) |
| ok | POST | `/auth/logout` | POST /auth/logout | `frontend/src/lib/api.ts:983` (client) |
| ok | GET | `/auth/me` | GET /auth/me | `frontend/src/lib/api.ts:979` (client) |
| ok | GET | `/auth/users` | GET /auth/users | `frontend/src/app/users/page.tsx:59` (page) |
| ok | POST | `/auth/users/invite` | POST /auth/users/invite | `frontend/src/app/users/page.tsx:97` (page) |
| ok | GET | `/auth/users/{x}/grants` | GET /auth/users/{user_id}/grants | `frontend/src/app/users/page.tsx:74` (page) |
| ok | POST | `/auth/users/{x}/grants` | POST /auth/users/{user_id}/grants | `frontend/src/app/users/page.tsx:111` (page) |
| ok | DELETE | `/auth/users/{x}/grants/{x}` | DELETE /auth/users/{user_id}/grants/{grant_id} | `frontend/src/app/users/page.tsx:122` (page) |
| ok | PATCH | `/auth/users/{x}/status` | PATCH /auth/users/{user_id}/status | `frontend/src/app/users/page.tsx:85` (page) |
| ok | GET | `/baselines` | GET /baselines | `frontend/src/lib/api.ts:683` (client) |
| ok | POST | `/baselines` | POST /baselines | `frontend/src/lib/api.ts:687` (client) |
| ok | GET | `/dashboard/summary` | GET /dashboard/summary | `frontend/src/lib/api.ts:740` (client) |
| ok | GET | `/empire-modules` | GET /empire-modules | `frontend/src/lib/api.ts:451` (client) |
| ok | POST | `/engines/check-updates` | POST /engines/check-updates | `frontend/src/lib/api.ts:1014` (client) |
| ok | GET | `/engines/health` | GET /engines/health | `frontend/src/lib/api.ts:1006` (client) |
| ok | POST | `/engines/test` | POST /engines/test | `frontend/src/lib/api.ts:1010` (client) |
| ok | GET | `/engines/workers` | GET /engines/workers | `frontend/src/lib/api.ts:967` (client) |
| ok | GET | `/events` | GET /events | `frontend/src/lib/events.ts:74` (fetch) |
| ok | GET | `/events/stream` | GET /events/stream | `frontend/src/lib/events.ts:107` (eventsource) |
| ok | POST | `/executions` | POST /executions | `frontend/src/lib/api.ts:923` (client) |
| ok | GET | `/executions` | GET /executions | `frontend/src/lib/api.ts:934` (client) |
| ok | GET | `/executions/{x}` | GET /executions/{execution_id} | `frontend/src/lib/api.ts:938` (client) |
| ok | POST | `/executions/{x}/cancel` | POST /executions/{execution_id}/cancel | `frontend/src/lib/api.ts:942` (client) |
| ok | GET | `/executions/{x}/output` | GET /executions/{execution_id}/output | `frontend/src/lib/api.ts:946` (url) |
| ok | GET | `/findings` | GET /findings | `frontend/src/app/engine-runs/page.tsx:102` (page) |
| ok | GET | `/findings` | GET /findings | `frontend/src/lib/api.ts:655` (client) |
| ok | GET | `/findings/{x}` | GET /findings/{finding_id} | `frontend/src/lib/api.ts:659` (client) |
| ok | GET | `/findings/{x}/history` | GET /findings/{finding_id}/history | `frontend/src/lib/api.ts:748` (client) |
| ok | POST | `/findings/{x}/recheck` | POST /findings/{finding_id}/recheck | `frontend/src/lib/api.ts:752` (client) |
| ok | POST | `/findings/{x}/triage` | POST /findings/{finding_id}/triage | `frontend/src/lib/api.ts:663` (client) |
| ok | GET | `/healthz/ready` | GET /healthz/ready | `frontend/src/lib/api.ts:988` (fetch) |
| ok | GET | `/history` | GET /history | `frontend/src/lib/api.ts:771` (client) |
| ok | POST | `/history/hide` | POST /history/hide | `frontend/src/lib/api.ts:779` (client) |
| ok | POST | `/history/hide/preview` | POST /history/hide/preview | `frontend/src/lib/api.ts:775` (client) |
| ok | POST | `/logs/purge` | POST /logs/purge | `frontend/src/lib/api.ts:1027` (client) |
| ok | GET | `/metrics/charts/coverage` | GET /metrics/charts/coverage | `frontend/src/lib/api.ts:430` (client) |
| ok | GET | `/metrics/charts/intelligence-activity` | GET /metrics/charts/intelligence-activity | `frontend/src/lib/api.ts:442` (client) |
| ok | GET | `/metrics/charts/module-risk` | GET /metrics/charts/module-risk | `frontend/src/lib/api.ts:426` (client) |
| ok | GET | `/metrics/charts/remediation-progress` | GET /metrics/charts/remediation-progress | `frontend/src/lib/api.ts:446` (client) |
| ok | GET | `/metrics/charts/risk-trend` | GET /metrics/charts/risk-trend | `frontend/src/lib/api.ts:434` (client) |
| ok | GET | `/metrics/charts/scanner-performance` | GET /metrics/charts/scanner-performance | `frontend/src/lib/api.ts:438` (client) |
| ok | GET | `/metrics/charts/vulnerability-trend` | GET /metrics/charts/vulnerability-trend | `frontend/src/lib/api.ts:422` (client) |
| ok | GET | `/metrics/overview` | GET /metrics/overview | `frontend/src/lib/api.ts:414` (client) |
| ok | GET | `/metrics/severity-distribution` | GET /metrics/severity-distribution | `frontend/src/lib/api.ts:418` (client) |
| ok | GET | `/modules/hub` | GET /modules/hub | `frontend/src/lib/api.ts:744` (client) |
| ok | GET | `/monitor-schedules` | GET /monitor-schedules | `frontend/src/lib/api.ts:711` (client) |
| ok | POST | `/monitor-schedules` | POST /monitor-schedules | `frontend/src/lib/api.ts:715` (client) |
| ok | PATCH | `/monitor-schedules/{x}` | PATCH /monitor-schedules/{schedule_id} | `frontend/src/lib/api.ts:719` (client) |
| ok | GET | `/monitor-schedules/{x}/slots` | GET /monitor-schedules/{schedule_id}/slots | `frontend/src/lib/api.ts:723` (client) |
| ok | GET | `/notifications` | GET /notifications | `frontend/src/lib/api.ts:783` (client) |
| ok | POST | `/notifications/read-all` | POST /notifications/read-all | `frontend/src/lib/api.ts:791` (client) |
| ok | DELETE | `/notifications/{x}` | DELETE /notifications/{nid} | `frontend/src/lib/api.ts:795` (client) |
| ok | POST | `/notifications/{x}/read` | POST /notifications/{nid}/read | `frontend/src/lib/api.ts:787` (client) |
| ok | GET | `/operations/capacity` | GET /operations/capacity | `frontend/src/lib/api.ts:727` (client) |
| ok | PUT | `/operations/capacity` | PUT /operations/capacity | `frontend/src/lib/api.ts:731` (client) |
| ok | GET | `/operations/metrics` | GET /operations/metrics | `frontend/src/lib/api.ts:811` (client) |
| ok | GET | `/operations/overview` | GET /operations/overview | `frontend/src/lib/api.ts:735` (client) |
| ok | POST | `/plans/preview` | POST /plans/preview | `frontend/src/lib/api.ts:695` (client) |
| ok | GET | `/report-snapshots` | GET /report-snapshots | `frontend/src/lib/api.ts:799` (client) |
| ok | POST | `/report-snapshots` | POST /report-snapshots | `frontend/src/lib/api.ts:803` (client) |
| ok | GET | `/report-snapshots/{x}/download` | GET /report-snapshots/{rid}/download | `frontend/src/lib/api.ts:807` (url) |
| ok | GET | `/reports` | GET /reports | `frontend/src/lib/api.ts:884` (client) |
| ok | POST | `/reports/generate` | POST /reports/generate | `frontend/src/lib/api.ts:894` (client) |
| ok | DELETE | `/reports/{x}` | DELETE /reports/{report_id} | `frontend/src/lib/api.ts:901` (client) |
| ok | GET | `/reports/{x}/download` | GET /reports/{report_id}/download | `frontend/src/lib/api.ts:905` (url) |
| ok | GET | `/rules` | GET /rules | `frontend/src/lib/api.ts:848` (client) |
| ok | POST | `/rules` | POST /rules | `frontend/src/lib/api.ts:863` (client) |
| ok | POST | `/rules/validate` | POST /rules/validate | `frontend/src/lib/api.ts:856` (client) |
| ok | POST | `/rules/{x}/lifecycle` | POST /rules/{id}/lifecycle | `frontend/src/lib/api.ts:870` (client) |
| ok | POST | `/rules/{x}/test` | POST /rules/{id}/test | `frontend/src/lib/api.ts:877` (client) |
| ok | POST | `/runs` | POST /runs | `frontend/src/lib/api.ts:699` (client) |
| ok | GET | `/runs` | GET /runs | `frontend/src/lib/api.ts:757` (client) |
| ok | GET | `/runs/{x}` | GET /runs/{batch_id} | `frontend/src/lib/api.ts:707` (client) |
| ok | GET | `/runs/{x}/diff` | GET /runs/{batch_id}/diff | `frontend/src/lib/api.ts:765` (client) |
| ok | GET | `/runs/{x}/tree` | GET /runs/{batch_id}/tree | `frontend/src/lib/api.ts:761` (client) |
| ok | GET | `/scans` | GET /scans | `frontend/src/app/assets/page.tsx:642` (page) |
| ok | GET | `/scans` | GET /scans | `frontend/src/lib/api.ts:519` (client) |
| ok | POST | `/scans` | POST /scans | `frontend/src/lib/api.ts:529` (client) |
| ok | POST | `/scans/batch` | POST /scans/batch | `frontend/src/lib/api.ts:566` (client) |
| ok | GET | `/scans/batch/{x}` | GET /scans/batch/{batch_id} | `frontend/src/lib/api.ts:577` (client) |
| ok | POST | `/scans/batch/{x}/cancel` | POST /scans/batch/{batch_id}/cancel | `frontend/src/lib/api.ts:581` (client) |
| ok | GET | `/scans/batches` | GET /scans/batches | `frontend/src/lib/api.ts:573` (client) |
| ok | POST | `/scans/stop-all` | POST /scans/stop-all | `frontend/src/lib/api.ts:587` (client) |
| ok | GET | `/scans/trackcurrent` | GET /scans/trackcurrent | `frontend/src/lib/api.ts:639` (client) |
| ok | POST | `/scans/ultra` | POST /scans/ultra | `frontend/src/lib/api.ts:617` (client) |
| ok | GET | `/scans/ultra/fixture-379` | GET /scans/ultra/fixture-379 | `frontend/src/lib/api.ts:635` (client) |
| ok | GET | `/scans/{x}` | GET /scans/batches | `frontend/src/lib/api.ts:536` (client) |
| ok | POST | `/scans/{x}/cancel` | POST /scans/{scan_id}/cancel | `frontend/src/lib/api.ts:540` (client) |
| ok | GET | `/scans/{x}/events` | GET /scans/batch/{batch_id} | `frontend/src/lib/api.ts:561` (client) |
| ok | GET | `/scans/{x}/events/stream` | GET /scans/{scan_id}/events/stream | `frontend/src/app/active-assessments/page.tsx:321` (eventsource) |
| ok | GET | `/scans/{x}/logs` | GET /scans/batch/{batch_id} | `frontend/src/lib/api.ts:544` (client) |
| ok | DELETE | `/scans/{x}/logs` | DELETE /scans/{scan_id}/logs | `frontend/src/lib/api.ts:1023` (client) |
| ok | GET | `/settings` | GET /settings | `frontend/src/lib/api.ts:1019` (client) |
| ok | POST | `/system/reset` | POST /system/reset | `frontend/src/lib/api.ts:1031` (client) |
| ok | GET | `/threat-intel/advisory-snapshots` | GET /threat-intel/advisory-snapshots | `frontend/src/lib/api.ts:950` (client) |
| ok | POST | `/threat-intel/advisory-snapshots` | POST /threat-intel/advisory-snapshots | `frontend/src/lib/api.ts:955` (client) |
| ok | GET | `/threat-intel/cve/{x}` | GET /threat-intel/cve/{cve_id} | `frontend/src/lib/api.ts:838` (client) |
| ok | GET | `/threat-intel/kev` | GET /threat-intel/kev | `frontend/src/lib/api.ts:842` (client) |
| ok | GET | `/threat-intel/summary` | GET /threat-intel/summary | `frontend/src/lib/api.ts:830` (client) |
| ok | POST | `/threat-intel/sync` | POST /threat-intel/sync | `frontend/src/lib/api.ts:834` (client) |

## Operation server chưa có caller trong console

Không phải lỗi: phần lớn là API cho CLI/automation, endpoint cũ giữ tương thích hoặc API admin chưa có màn hình.

- `DELETE /alerts`
- `DELETE /alerts/{id}`
- `DELETE /baselines/{id}`
- `DELETE /rules/{id}`
- `DELETE /scans/{scan_id}`
- `GET /alerts/unread-count`
- `GET /assets/{asset_id}/artifacts`
- `GET /healthz/live`
- `GET /logs`
- `GET /logs/export`
- `GET /notifications/unread-count`
- `GET /reports/{report_id}`
- `GET /rules/{id}`
- `GET /scans/telemetry`
- `GET /scans/{scan_id}`
- `GET /scans/{scan_id}/events`
- `GET /scans/{scan_id}/logs`
- `GET /scans/{scan_id}/logs/stream`
- `GET /settings/ssrf-config`
- `GET /threat-intel/cves`
- `GET /version`
- `POST /auth/bootstrap`
- `POST /auth/refresh`
- `POST /baselines/reset`
- `POST /findings/{finding_id}/retest`
- `POST /history/unhide`
- `POST /reports`
- `POST /rules/test`
- `POST /scans/loop-test`
- `POST /scans/scan-all`
- `POST /settings/reset`
- `POST /settings/reset-baseline`
- `POST /threat-intel/epss/batch`
- `PUT /assets/{asset_id}`
- `PUT /rules/{id}`
- `PUT /settings`
- `PUT /settings/ssrf-config`
