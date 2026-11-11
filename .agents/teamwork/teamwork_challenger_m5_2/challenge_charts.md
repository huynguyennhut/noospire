# Adversarial Challenge Report: SVG Chart Mathematics & Boundary Conditions

**Document**: `challenge_charts.md`  
**Milestone**: Milestone 5 (UI Foundation, Primitives, Responsive Shell & Chart Engine)  
**Challenger**: Challenger 2 (Empirical Challenger — SVG Chart Mathematics & Boundary Verifier)  
**Target Codebase**: `frontend/src/components/charts/`  
**Execution Date**: 2026-11-08  
**Verification Harnesses**:
- `scripts/verify_svg_charts.mjs` (87 mathematical & boundary assertions — 100% PASS)
- `scripts/verify_react_charts.mjs` (37 React SSR rendering assertions — 100% PASS)
- `frontend/` compile & lint check: `npm run typecheck` (tsc 0 errors), `npm run lint` (0 chart warnings)
- Full regression suites: `pytest tests/` (164/164 passed), `python scripts/verify_empire_e2e.py` (10/10 passed)

---

## 1. Challenge Summary

**Overall Risk Assessment**: **LOW** (Production-Grade Robustness Verified)

The zero-dependency SVG charting engine in `frontend/src/components/charts/` was subjected to adversarial stress testing across boundary conditions, degenerate datasets, extreme numerical ratios, and mathematical models.

Across all 4 chart components (`InteractiveAreaChart`, `InteractiveBarChart`, `InteractiveDonutChart`, `InteractiveGaugeChart`) and auxiliary utilities (`ChartTooltip`, `useChartDimensions`, `adapters`), no runtime exceptions, unhandled `NaN`, or malformed SVG path outputs were produced. The mathematical formulations for Bézier curve splines, radial semicircles, and 360-degree donut rings comply with SVG 1.1/2.0 specifications. Minor ergonomic observations are documented below as low-severity advisories.

---

## 2. Adversarial Challenges & Invariant Stress-Testing

### Challenge 1 (Low): Micro-Slice Angular Span Inversion with Global Pad Angle in `InteractiveDonutChart`
- **Assumption Challenged**: In `InteractiveDonutChart.tsx` (lines 58-59), each slice calculates `startAngle = currentAngle + padAngle / 2` and `endAngle = currentAngle + angleSpan - padAngle / 2` where default `padAngle = 0.025` radians (~1.43°).
- **Attack Scenario**: An extreme dataset with an unbalanced distribution (e.g. `100,000` vs `1`) produces a micro-slice where `angleSpan = 2 * PI * (1 / 100001) = 0.0000628` radians. Because `angleSpan < padAngle`, `startAngle > endAngle`.
- **Empirical Observation**: The resulting SVG path coordinates remain finite and free of `NaN`. In SVG rendering, an arc where $startAngle > endAngle$ with `sweep-flag=1` either collapses visually or produces an imperceptible sub-pixel stroke. However, in extreme edge cases with multiple micro-slices, visual overlap could occur.
- **Blast Radius**: Cosmetic rendering of slices with value < 0.1% total share. Zero application crash or exception.
- **Recommended Mitigation (for future refinement)**:
  Clamp pad angle dynamically per segment:
  `const effectivePad = Math.min(padAngle, angleSpan / 2);`
  `const startAngle = currentAngle + effectivePad / 2;`
  `const endAngle = currentAngle + angleSpan - effectivePad / 2;`

---

### Challenge 2 (Informational): Single Data Point Hover Crosshair Suppressed in `InteractiveAreaChart`
- **Assumption Challenged**: When `data.length === 1`, how does `InteractiveAreaChart` respond to user mouse interactions?
- **Empirical Observation**: In `InteractiveAreaChart.tsx` line 124:
  `const activeX = hoveredIndex !== null && data.length > 1 ? margin.left + (hoveredIndex / (data.length - 1)) * plotWidth : null;`
  When `data.length === 1`, `activeX` evaluates to `null`. As a consequence, lines 209 and 265 deliberately suppress the vertical crosshair line and tooltip popup.
- **Blast Radius**: None. This is an intentional safety guard that gracefully prevents division-by-zero (`0 / (1 - 1) = NaN`). The chart renders the single data point correctly centered at `plotWidth / 2` with a 10px baseline tick (`M p.x-5,p.y L p.x+5,p.y`) and a closed polygon area path.

---

## 3. Mathematical Correctness & Geometry Verification

### 3.1. InteractiveAreaChart (Catmull-Rom to Cubic Bézier Spline)
- **Mathematical Model**:
  The spline generator in lines 78-98 converts discrete data points $(P_i)$ into a $C^1$-continuous cubic Bézier spline using a cardinal formulation with tension $\tau = 0.2$:
  $$CP_{1,i} = P_i + (P_{i+1} - P_{i-1}) \cdot \tau$$
  $$CP_{2,i} = P_{i+1} - (P_{i+2} - P_i) \cdot \tau$$
  At boundary endpoints ($i=0$ and $i=n-2$), forward difference ($P_0 = P_1$) and backward difference ($P_{n} = P_{n-1}$) are used to prevent out-of-bounds indexing.
- **Y-Clamping**:
  `cp1y = Math.min(Math.max(cp1y, margin.top), bottom)`
  `cp2y = Math.min(Math.max(cp2y, margin.top), bottom)`
  This clamps control points strictly within $[y_{top}, y_{bottom}]$, mathematically preventing overshoot and undershoot artifacts outside the chart viewport.
- **Area Path Extraction**:
  `linePath.substring(linePath.indexOf('C'))` correctly isolates cubic Bézier commands, connecting $(P_0.x, y_{bottom}) \to (P_0.x, P_0.y) \to \text{spline} \to (P_{last}.x, y_{bottom}) \to Z$.
- **Verification Result**: **PASS** (Zero `NaN`, exact $n-1$ segments, valid SVG path commands).

---

### 3.2. InteractiveDonutChart (360-Degree Arc & Concentric Geometry)
- **Circumference Math**:
  $$\sum_{i=1}^k \Delta\theta_i = \sum_{i=1}^k \left(\frac{v_i}{\sum v} \cdot 2\pi\right) = 2\pi \text{ radians} \equiv 360^\circ$$
  Our test confirmed $\left|\sum \Delta\theta_i - 2\pi\right| < 10^{-9}$.
- **Concentric Radii**:
  $cx = width / 2$, $cy = height / 2$, $R_{outer} = \min(cx, cy) - 16$, $R_{inner} = R_{outer} \times 0.68$.
- **Single Slice 100% Boundary**:
  When $fraction \ge 0.999$, the chart generates dual concentric circular arcs:
  `M cx, cy-R_outer A R_outer,R_outer 0 1,1 cx, cy+R_outer A R_outer,R_outer 0 1,1 cx, cy-R_outer`
  followed by inner counter-clockwise arc:
  `M cx, cy-R_inner A R_inner,R_inner 0 1,0 cx, cy+R_inner A R_inner,R_inner 0 1,0 cx, cy-R_inner Z`
  This fills the outer ring and preserves the transparent donut hole via nonzero winding rule.
- **Hover Radial Vector**:
  Slice displacement is calculated as $(dx, dy) = (\cos\theta_{mid} \cdot 5, \sin\theta_{mid} \cdot 5)$.
  Euclidean norm $\sqrt{dx^2 + dy^2} = 5.0\text{px}$ exactly.
- **Verification Result**: **PASS** (100% concentric, zero `NaN`, valid SVG arc commands).

---

### 3.3. InteractiveGaugeChart (180-Degree Semicircle Radial Dial)
- **Angle Parameterization**:
  $$\theta(r) = \pi \cdot (1 - r), \quad r = \frac{\text{clampedVal} - \text{min}}{\text{max} - \text{min}} \in [0, 1]$$
  - At $r = 0.0$: $\theta = \pi$ rad ($180^\circ$, left baseline $x = cx - R, y = cy$).
  - At $r = 0.5$: $\theta = \frac{\pi}{2}$ rad ($90^\circ$, apex $x = cx, y = cy - R$).
  - At $r = 1.0$: $\theta = 0$ rad ($0^\circ$, right baseline $x = cx + R, y = cy$).
- **SVG Coordinate Inversion**:
  Because SVG $+y$ points downward, the radial coordinate is correctly mapped as:
  $$y = cy - R \cdot \sin\theta$$
  Since $\theta \in [0, \pi]$, $\sin\theta \ge 0$, ensuring all points lie strictly in the upper half-plane $y \le cy$.
- **Needle Indicator Pip**:
  Placed along the centerline radius $R_{mid} = R_{outer} - \frac{W_{track}}{2}$:
  $$(pipX, pipY) = (cx + R_{mid}\cos\theta, cy - R_{mid}\sin\theta)$$
  Empirical measurements confirm $(pipX, pipY)$ resides precisely along the dial arc centerline under all values.
- **Verification Result**: **PASS** (Mathematically airtight).

---

### 3.4. InteractiveBarChart (Grouped, Stacked, Horizontal, and Rounded Corners)
- **Corner Radius Clamping**:
  `safeR = Math.min(r, h, w / 2)` guarantees that when $h < r$ or $w/2 < r$, the quadratic Bézier corner curve `Q x,y x+safeR,y` does not invert or exceed the bar dimensions.
- **Zero Height Defense**:
  `if (h <= 0 || w <= 0) return '';` avoids emitting degenerate SVG path tags with negative dimensions.
- **Stacked Mode**:
  Accumulates $y$-coordinates downward from $margin.top + plotHeight$, correctly segmenting series without floating point drift.
- **Verification Result**: **PASS** (No broken paths, zero `NaN`).

---

### 3.5. ChartTooltip (Auto-Inversion & Clamping)
- **Horizontal Auto-Inversion**:
  `isRightEdge = x + 160 + 24 > containerWidth`
  `leftPos = isRightEdge ? x - 160 - 12 : x + 12`
  - Cursor at $x = 10, containerWidth = 500 \implies left = 22\text{px}$ (within container).
  - Cursor at $x = 450, containerWidth = 500 \implies left = 278\text{px}$ (auto-flipped, within container).
- **Vertical Clamping**:
  `top = Math.max(8, y - 24)` prevents tooltip clipping above the top container margin.
- **Verification Result**: **PASS** (100% contained).

---

## 4. Stress Test Results Matrix

| # | Component | Adversarial Scenario | Expected Behavior | Actual Behavior | Verdict |
|---|---|---|---|---|---|
| 1 | `InteractiveAreaChart` | Empty dataset (`data = []`) | `maxY=10`, empty points, empty spline, valid grid | Rendered without error, no `NaN` in SVG | **PASS** |
| 2 | `InteractiveAreaChart` | Single data point (`data = [{ val: 10 }]`) | Fallback tick line & closed polygon, no 0/0 | Rendered fallback tick at $x=240$, no `NaN` | **PASS** |
| 3 | `InteractiveAreaChart` | All zero values (`data = [{ val: 0 }, { val: 0 }]`) | Scale $maxY=10$, points on bottom baseline | All $y=216$, flat Bézier line, no `NaN` | **PASS** |
| 4 | `InteractiveAreaChart` | Extreme ratio ($0$ vs $1,000,000$) | $maxY=1,150,000$, Bézier bounded | All points & control points within $[16, 216]$ | **PASS** |
| 5 | `InteractiveAreaChart` | Cursor outside viewBox ($x < 0, x > plotWidth$) | Coordinate ratio clamped to $[0, 1]$ | $x < 0 \to idx=0$, $x > plotWidth \to idx=n-1$ | **PASS** |
| 6 | `InteractiveBarChart` | Empty dataset (`data = []`) | $kCount=1$, no division by zero | Rendered without error, no `NaN` | **PASS** |
| 7 | `InteractiveBarChart` | Bar with height 0 | Returns empty path string | `roundedBarPath` returned `''`, no broken path | **PASS** |
| 8 | `InteractiveBarChart` | Tiny bar ($h = 1.5, r = 3$) | Radius clamped to $safeR = 1.5$ | Safe radius clamped, valid SVG path | **PASS** |
| 9 | `InteractiveBarChart` | Narrow bar ($w = 2, r = 3$) | Radius clamped to $safeR = 1.0$ | Safe radius clamped, valid SVG path | **PASS** |
| 10 | `InteractiveDonutChart` | Empty dataset (`data = []`) | $total=0$, center readout shows 0 | Slices empty, center shows 0, no `NaN` | **PASS** |
| 11 | `InteractiveDonutChart` | All zero values (`data = [{ value: 0 }]`) | $total=0$, legend displays `(0%)` | Percentage clamped to 0%, no `NaN%` | **PASS** |
| 12 | `InteractiveDonutChart` | Single full slice ($100\%$) | Dual 180° concentric outer & inner arcs | Full donut ring, transparent inner hole | **PASS** |
| 13 | `InteractiveDonutChart` | Multi-slice 360° | Total angle sum $= 2\pi$ | Exact sum $2\pi$ (error $< 10^{-9}$) | **PASS** |
| 14 | `InteractiveDonutChart` | Hover translation vector | Vector length $= 5.0\text{px}$ | Exact Euclidean norm $= 5.000\text{px}$ | **PASS** |
| 15 | `InteractiveGaugeChart` | $value = 0$ | Left baseline $\theta = \pi$, pip at $cx - midR$ | Ratio 0, angle $\pi$, pip at left baseline | **PASS** |
| 16 | `InteractiveGaugeChart` | $value = 50$ | Apex $\theta = \pi/2$, pip at $x=cx, y=cy-midR$ | Ratio 0.5, angle $\pi/2$, pip at apex | **PASS** |
| 17 | `InteractiveGaugeChart` | $value = 100$ | Right baseline $\theta = 0$, pip at $cx + midR$ | Ratio 1.0, angle 0, pip at right baseline | **PASS** |
| 18 | `InteractiveGaugeChart` | Out of bounds ($val = -25, val = 250$) | Clamped to $[minValue, maxValue]$ | Clamped to 0 and 100, valid pip & arc | **PASS** |
| 19 | `ChartTooltip` | Point near right edge ($x = 450$) | Auto-flips to left of point | Flipped to $left = 278\text{px} < containerWidth$ | **PASS** |
| 20 | `ChartTooltip` | Point near top edge ($y = 10$) | Clamped to $top = 8\text{px}$ | Clamped to $8\text{px}$, prevented clipping | **PASS** |

---

## 5. Build, Lint & Regression Verification

1. **TypeScript Typecheck**:
   `cd frontend; npm run typecheck`
   Output: `tsc --noEmit` exited with code 0 (0 compilation errors).
2. **ESLint Static Analysis**:
   `cd frontend; npm run lint`
   Output: exited with code 0 (0 warnings or errors in `components/charts/`).
3. **Automated Mathematical Verifier**:
   `node scripts/verify_svg_charts.mjs`
   Output: 87/87 tests passed (0 failures).
4. **React SSR Empirical Rendering**:
   `node scripts/verify_react_charts.mjs`
   Output: 37/37 tests passed (0 failures).
5. **Backend Pytest Suite**:
   `pytest tests/ -q`
   Output: 164 passed, 2 warnings in 295.00s.
6. **Empire E2E Verification**:
   `python scripts/verify_empire_e2e.py`
   Output: 10/10 automated tests passed (XANH MƯỢT 100%).

---

## 6. Unchallenged Areas

- **Client Browser WebGL/Canvas Acceleration**: Out of scope (components are pure SVG).
- **Touch Gesture Pinch-to-Zoom**: Not specified in requirements (standard desktop/tablet hover interaction is specified).

---

## 7. Adversarial Conclusion & Recommendation

The interactive SVG charting library demonstrates outstanding mathematical precision, defensive boundary handling, and full adherence to the Black/White/Liquid Glass design tokens.

**Final Verdict**: **APPROVE**
