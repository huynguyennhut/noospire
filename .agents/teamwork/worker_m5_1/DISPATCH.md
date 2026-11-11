# DISPATCH — Milestone 5

## 2026-11-08T15:28:02Z
You are the Worker implementing Milestone 5: UI Primitives, Responsive Shell & Interactive SVG Chart Engine.

MANDATORY FIRST STEP:
Read C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read C:\Users\nguye\desktop\noospire\PROJECT.md.

Read the technical specifications produced by the M5 Explorers:
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_1\plan_primitives.md
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_2\plan_charts.md
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_3\plan_shell.md

Working directory: C:\Users\nguye\desktop\noospire
Your state folder: C:\Users\nguye\desktop\noospire\.agents\teamwork\worker_m5_1\

FILES YOU OWN EXCLUSIVELY:
- `frontend/.eslintrc.json`
- `frontend/package.json`
- `frontend/src/lib/utils.ts`
- `frontend/src/components/ui/` (`card.tsx`, `button.tsx`, `badge.tsx`, `table.tsx`, `modal.tsx`, `tabs.tsx`, `input.tsx`, `tooltip.tsx`, `stat-card.tsx`, `index.ts`)
- `frontend/src/components/charts/` (`InteractiveAreaChart.tsx`, `InteractiveBarChart.tsx`, `InteractiveDonutChart.tsx`, `InteractiveGaugeChart.tsx`, `adapters.ts`, `index.ts`)
- `frontend/src/components/layout/Shell.tsx` and `frontend/src/components/Shell.tsx`
- `frontend/src/lib/i18n.tsx`

IMPLEMENTATION TASKS:
1. ESLint & Linting Pipeline:
   - Create `frontend/.eslintrc.json` extending `"next/core-web-vitals"`.
   - Update `frontend/package.json` devDependencies if necessary to include `"eslint": "^8.57.0"` and `"eslint-config-next": "14.2.24"`. Run `npm install` in `frontend/` so `npm run lint` works non-interactively without prompts.
2. UI Primitives (`frontend/src/components/ui/`):
   - Create `frontend/src/lib/utils.ts` with standard `cn(...inputs)` combining `clsx` and `twMerge`.
   - Implement `card.tsx` (Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter) with liquid glass styling, subtle borders, and elevation tokens.
   - Implement `stat-card.tsx` (StatCard) with icon container, trend indicator (+/- percentage with arrow), metric value, and subtitle.
   - Implement `button.tsx` with variants (`primary`, `secondary`, `destructive`, `outline`, `ghost`, `glass`) and sizes (`sm`, `md`, `lg`) and loading spinner state.
   - Implement `badge.tsx` with severity variants (`critical`, `high`, `medium`, `low`, `info`, `neutral`, `status`).
   - Implement `table.tsx` with responsive overflow wrapper, hover effects, and border-subtle styling.
   - Implement `modal.tsx` with backdrop blur, keyboard ESC listener, body scroll lock, close button, title, content, footer.
   - Implement `tabs.tsx` with tab switching state and tab panels.
   - Implement `input.tsx` with glass styling and focus ring.
   - Implement `tooltip.tsx` with hover tooltip box and arrow.
   - Implement `index.ts` barrel export.
3. Interactive SVG Chart Engine (`frontend/src/components/charts/`):
   - Implement `InteractiveAreaChart.tsx`: smooth bezier curves (`M... C...`), linear gradient fill underneath, mousemove tracking with glowing crosshair vertical line, glowing dot, and floating tooltip.
   - Implement `InteractiveBarChart.tsx`: grouped/stacked bars with rounded tops, hover highlight, and floating tooltip.
   - Implement `InteractiveDonutChart.tsx`: SVG donut with segment hover expansion, center summary value/label, and interactive legend with highlight synchronization.
   - Implement `InteractiveGaugeChart.tsx`: semi-circular radial gauge with emerald/amber/rose zones, numerical readout, and risk posture label.
   - Implement `adapters.ts` and `index.ts` barrel export.
4. Responsive Shell Overhaul (`frontend/src/components/layout/Shell.tsx` and `frontend/src/components/Shell.tsx`):
   - Update `Shell.tsx` to be fully responsive across mobile (< 768px), tablet (768px - 1024px), and desktop (> 1024px):
     * Mobile: fixed slide-over drawer modal (`fixed inset-0 z-50` with backdrop blur, smooth slide from left, ESC dismissal, body scroll lock, hamburger menu button).
     * Tablet: collapsible sidebar (`w-64` vs `w-20` compact with hover tooltips).
     * Desktop: sticky vertical sidebar with frosted glass (`backdrop-blur-xl border-r border-white/10`).
     * Top utility bar: notification bell with unread badge counter (`3`) and alert popover, bilingual toggle (`VI / EN`), target environment badge (`Empire Education Platform` with pulsing emerald dot), and real-time backend API health status pill.
     * Categorize all 14 navigation views into 4 logical groups with bilingual headings.
   - Ensure `frontend/src/components/Shell.tsx` re-exports from `frontend/src/components/layout/Shell.tsx` for backwards compatibility.
   - Update `frontend/src/lib/i18n.tsx` with all necessary navigation and UI labels in both Vietnamese and English.
5. Verification:
   - Run `npm run lint` in `frontend/` — verify 0 errors.
   - Run `npm run build` in `frontend/` — verify all static routes compile cleanly with 0 TypeScript errors.
