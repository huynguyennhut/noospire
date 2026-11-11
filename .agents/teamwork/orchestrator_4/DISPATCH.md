## 2026-11-09T00:39:13Z
[Message] timestamp=2026-11-09T00:39:13Z sender=6b4f0af6-a27b-4e89-b3aa-959eda68684c priority=MESSAGE_PRIORITY_HIGH content=Implement a production "Scan All" capability to scan all targets across all engines and assessment profiles with device resource optimization, alongside a black/white modern liquid glass UI incorporating the official logo asset, live thread and log tracking, and scan notifications.

Working directory: C:\Users\nguye\desktop\noospire
Integrity mode: development

## Verification Resources
- Existing backend test suite: `pytest tests/`
- Existing end-to-end verification script: `python scripts/verify_empire_e2e.py`
- Existing frontend build and typecheck: `npm run build`
- Existing frontend linter: `npm run lint`

## Requirements

### R1. "Scan All" Batch Scan Orchestration & Resource Optimization
The system must provide a "Scan All" batch execution capability that dispatches scans across all registered targets using all available scanning engines and assessment profiles. The batch execution must throttle concurrent tasks and manage worker resources to prevent device overutilization or performance degradation.

### R2. Black/White Modern Liquid Glass UI & Logo Integration
The frontend UI must support the "Scan All" workflow adhering to the platform's black/white modern theme and liquid glass styling. The official logo image located at `C:/Users/nguye/.gemini/antigravity-cli/brain/6fde3f07-9d36-4bda-a864-b53b67d53f2e/.user_uploaded/uploaded_media_1794171615086.jpg` must be incorporated into the application brand assets and shell header.

### R3. Live Thread Feed, Log Tracking & Telemetry
The UI must provide real-time tracking of active scan threads, current scan progress ("trackcurrent"), live log feeds, and notifications alerting users to scan lifecycle events (such as completion or errors).

### R4. Backward Compatibility & Test Integrity
All existing backend endpoints, database models, target verification flows, and frontend navigation views must remain functional without regression.

## Acceptance Criteria

### Batch Execution & Resource Optimization
- [ ] Triggering "Scan All" schedules scan tasks covering all registered targets across all available engines and assessment profiles.
- [ ] Batch execution limits concurrent scan processes/threads so that the host device is not overloaded.
- [ ] Users can monitor batch execution progress and cooperatively cancel or stop running batch jobs.

### UI Styling & Brand Integration
- [ ] The shell header and brand presentation display the official logo sourced from `C:/Users/nguye/.gemini/antigravity-cli/brain/6fde3f07-9d36-4bda-a864-b53b67d53f2e/.user_uploaded/uploaded_media_1794171615086.jpg`.
- [ ] The "Scan All" controls and tracking interface conform to the black/white modern theme with liquid glass styling (frosted cards, specular borders, backdrop blur).
- [ ] The UI renders cleanly across desktop, tablet, and mobile viewports without layout overflow.

### Live Telemetry, Log Tracking & Notifications
- [ ] Active scan threads and current execution state ("trackcurrent") are displayed in a real-time tracking feed.
- [ ] Scan logs stream in real time and are easily accessible in the UI.
- [ ] Scan lifecycle notifications trigger upon scan completion, warnings, or errors.

### Verification & Regressions
- [ ] Backend test suite passes (`pytest tests/`).
- [ ] E2E capability verification script passes (`python scripts/verify_empire_e2e.py`).
- [ ] Frontend static build succeeds with zero errors (`npm run build`).
- [ ] Frontend lint passes cleanly (`npm run lint`).
- [ ] New automated tests verify the "Scan All" batch orchestration and concurrency throttling.
