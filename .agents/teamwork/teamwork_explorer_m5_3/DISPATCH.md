## 2026-11-08T15:19:03Z

Sender: 3ff4f284-0e46-40b0-b26d-38272165c219
Priority: MESSAGE_PRIORITY_HIGH

You are an Explorer for Milestone 5: Responsive Shell & Viewport Architecture.

MANDATORY FIRST STEP:
Read C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read C:\Users\nguye\desktop\noospire\PROJECT.md.

Working directory: C:\Users\nguye\desktop\noospire
Your state folder: C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_3\

MISSION & SCOPE:
Design the concrete architecture and implementation plan for the responsive application shell in `frontend/src/components/Shell.tsx` and related layout files:
1. Examine `frontend/src/components/Shell.tsx` and identify responsive weaknesses across mobile (< 768px), tablet (768px - 1024px), and desktop (> 1024px) viewports.
2. Design mobile navigation:
   - Sticky top bar with brand mark, target indicator, language toggle, and animated hamburger menu button (`Menu` / `X`).
   - Slide-over drawer / modal overlay that smoothly transitions from left, presenting all 14 navigation links, grouped logically (Core Overview, Inventory & Scans, Intelligence & Modules, Governance & System).
   - Touch-friendly tap targets (minimum 44px height), active link highlight, and auto-close drawer on route click.
3. Design tablet and desktop navigation:
   - Desktop: sticky vertical sidebar with frosted glass (`backdrop-blur-xl border-r border-white/10`), brand banner, quick status indicator (Live SOC status), and collapsed/expanded toggle support.
   - Main content viewport: fluid container with appropriate horizontal padding (`px-4 sm:px-6 lg:px-8`) ensuring wide data tables and metric charts do not overflow or cause horizontal body scroll.
4. Top status bar & utility features:
   - Notification indicator (bell icon with unread badge counter).
   - Bilingual locale toggle button (`VI / EN`) with smooth animation.
   - Target environment badge (`Empire Education Platform` with green pulse).
   - Backend connectivity / health indicator pill.
5. Provide the exact implementation blueprint and test checklist for the Worker.

CONSTRAINTS:
- You are read-only. Do NOT write or modify application code.
- Write your comprehensive plan to `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_3\plan_shell.md`.
- Write your final handoff to `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_3\handoff.md`.
- Update `progress.md` in your state folder with timestamps for heartbeat.
- Send a message to parent when completed.
