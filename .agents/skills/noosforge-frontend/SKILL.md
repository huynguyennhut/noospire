---
name: noosforge-frontend
description: Implement NOOSFORGE Next.js screens, premium Liquid Glass UI, charts and accessible interactions using existing components. Use for frontend changes, not backend authorization or deployment.
---

# Premium frontend and UI engineering

Read root `AGENTS.md`. Own presentation, browser behavior and client integration;
server permissions and task semantics belong to backend/security workflows.

## Implementation

1. Follow `frontend/src/app/layout.tsx` into `components/layout/Shell.tsx`, the
   theme, i18n and toast providers. `components/Shell.tsx`, `EvidenceViewer.tsx` and
   `TargetVerificationModal.tsx` at the component root are compatibility exports.
2. Inspect `src/styles/globals.css`, `tailwind.config.js`, `components/ui/`, and
   `components/charts/` before changing a screen. Reuse `nf`, `glass`, severity
   tokens and existing SVG chart adapters. Preserve `public/brand/` assets.
   Use restrained Black/White Liquid Glass; keep evidence and dense tables legible.
3. Verify both `obsidian-dark` and `warm-light`. The latter is stored as
   `sentinel_theme=warm-light` but applies `data-theme=warm`, `.light`, `.theme-warm`.
   Preserve `lib/i18n.tsx` VI/EN keys and the existing provider contract.
4. Keep `next.config.js` static export compatibility: browser-only APIs need client
   boundaries; do not add server actions or depend on a Next.js runtime server.
   Browser API requests use same-origin `/api/v1` through the gateway, not a public
   backend URL. Inspect `lib/api.ts` and `lib/events.ts` for cookies, CSRF, typed
   errors, SSE replay and polling. Do not put tokens in URLs or browser storage.
5. Wire actions to real responses before announcing success. Handle duplicate
   submissions, loading, empty, error, permission and unavailable-engine states.
   Keep KPI data and chart tooltips tied to API records. Do not hide partial coverage.
6. Check keyboard operation, visible focus, accessible labels, modal dismissal,
   sidebar behavior and responsive tables at desktop/tablet/mobile sizes. For a
   visual change, inspect hydrated screenshots in both themes with synthetic data.

## Verification

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py frontend
.venv/bin/python scripts/contract_audit.py
```

The frontend preset runs the `test:lifecycle`, `typecheck`, `lint` and `build` npm scripts
without installing/upgrading packages. The lifecycle test exercises actual status grouping and legacy aliases;
compile/build checks are not visual or browser proof. There is no configured component/E2E npm test runner.
Inspect legacy browser scripts before reuse: several contain fixed credentials,
fixed ports and write to historical screenshots. Use an isolated local stack and
fresh test-only artifacts; never automate customer scan buttons during UI QA.

Deliver changed interactions, affected shared components and actual verification;
report browser coverage as unverified if no browser checks ran.
