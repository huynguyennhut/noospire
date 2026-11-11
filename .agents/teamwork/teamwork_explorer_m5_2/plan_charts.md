# Architectural Plan & Mathematical Specification: Zero-Dependency Interactive SVG Charting Engine

**Document Status**: COMPREHENSIVE ARCHITECTURAL BLUEPRINT  
**Target Package**: `frontend/src/components/charts/`  
**Milestone**: Milestone 5 (UI Foundation, Primitives, Responsive Shell & Chart Engine)  
**Author**: Teamwork Explorer (Milestone 5 - Charts Track)  
**Verification Command**: `npm --prefix frontend run typecheck`

---

## 1. Executive Summary & Design Philosophy

The NOOSFORGE Security Intelligence platform requires a high-performance, enterprise-grade, zero-dependency interactive charting engine to visualize attack surface metrics, vulnerability lifecycle trends, module risk indices, and scanner telemetry.

### 1.1 Core Tenets
1. **Zero External Charting Dependencies**: No heavy third-party libraries (e.g., D3, Recharts, Chart.js, Victory). The suite relies strictly on native React 18, SVG geometry, and Tailwind CSS. This guarantees:
   - Instant loading times (0 KB third-party chart library overhead).
   - Zero version mismatch or breaking changes during Next.js App Router updates.
   - Direct control over DOM rendering, event tracking, and accessibility.
2. **Black/White/Liquid Glass Design System Integration**:
   - Glassmorphic card containment (`liquid-glass-card`, `backdrop-blur-md`, `border-white/10`).
   - Cyberpunk palette: Accent Cyan (`#06B6D4`), Emerald (`#10B981`), Amber (`#F59E0B`), Rose (`#EF4444`), Violet (`#A855F7`).
   - Specular glows, linear gradient fills with alpha decay ($0.30 \to 0.00$), and tactical monospace fonts.
3. **Fluid Responsiveness**:
   - Container measurement via `ResizeObserver` with responsive SVG `viewBox` coordinates.
   - Smooth degradation when container dimensions change across mobile (< 768px), tablet (768px–1024px), and desktop (> 1024px).
4. **Interactive Precision**:
   - Real-time mouse/touch event tracking with nearest-neighbor projection ($O(1)$ index lookup).
   - Vertical crosshair rule (`stroke-cyan-500/50`) and glowing point indicators.
   - Floating glass tooltips with auto-inversion logic to prevent viewport clipping.
   - Bidirectionally synchronized legends with slice/bar highlighting.

---

## 2. Mathematical Specifications & Geometry Algorithms

### 2.1 Coordinate Space & Linear Normalization

Let an SVG chart container have measured pixel width $W$ and height $H$.  
Let margins be defined as $M = \{ \text{top}, \text{right}, \text{bottom}, \text{left} \}$.

The active plotting area is defined as:
$$W_{\text{plot}} = W - M_{\text{left}} - M_{\text{right}}$$
$$H_{\text{plot}} = H - M_{\text{top}} - M_{\text{bottom}}$$

#### Linear Projection Formulae
For a discrete dataset of $N$ points along the horizontal axis, the $x$-coordinate for point index $i \in [0, N-1]$ is:
$$X(i) = \begin{cases} 
M_{\text{left}} + \dfrac{W_{\text{plot}}}{2} & \text{if } N = 1 \\
M_{\text{left}} + \dfrac{i}{N - 1} \times W_{\text{plot}} & \text{if } N > 1 
\end{cases}$$

For continuous values $v \in [Y_{\min}, Y_{\max}]$ on the vertical axis (where SVG $y = 0$ corresponds to the top edge):
$$Y(v) = M_{\text{top}} + H_{\text{plot}} - \left( \dfrac{v - Y_{\min}}{Y_{\max} - Y_{\min}} \right) \times H_{\text{plot}}$$

To guarantee visually pleasant tick boundaries without chart edge clipping:
$$Y_{\max}^{\text{padded}} = \begin{cases} 
10 & \text{if } \max(V) = 0 \\
\lceil \max(V) \times 1.15 \rceil & \text{otherwise}
\end{cases}$$

---

### 2.2 Smooth Bézier Spline Algorithm (`InteractiveAreaChart`)

To eliminate jagged polyline artifacts without library bloat, we derive smooth cubic Bézier curves (`C cp1x,cp1y cp2x,cp2y x,y`) using Catmull-Rom spline control point derivation with a smoothing tension parameter $\tau = 0.20$.

#### Control Point Calculation
Given $N$ points $P_0, P_1, \dots, P_{N-1}$ where $P_i = (X_i, Y_i)$:
For each segment between $P_i$ and $P_{i+1}$ (for $i \in [0, N-2]$):

1. **Virtual Neighbor Selection**:
   $$P_{i-1} = \begin{cases} P_0 & \text{if } i = 0 \\ P_{i-1} & \text{otherwise} \end{cases}$$
   $$P_{i+2} = \begin{cases} P_{N-1} & \text{if } i = N - 2 \\ P_{i+2} & \text{otherwise} \end{cases}$$

2. **Control Point Derivation**:
   $$CP_{1,x} = P_{i,x} + (P_{i+1,x} - P_{i-1,x}) \times \tau$$
   $$CP_{1,y} = P_{i,y} + (P_{i+1,y} - P_{i-1,y}) \times \tau$$
   $$CP_{2,x} = P_{i+1,x} - (P_{i+2,x} - P_{i,x}) \times \tau$$
   $$CP_{2,y} = P_{i+1,y} - (P_{i+2,y} - P_{i,y}) \times \tau$$

3. **Baseline Bounding Clamping**:
   Since values cannot dip below the zero baseline ($Y_{\text{base}} = M_{\text{top}} + H_{\text{plot}}$) or overshoot the chart header ($M_{\text{top}}$):
   $$CP_{1,y} = \min(\max(CP_{1,y}, M_{\text{top}}), M_{\text{top}} + H_{\text{plot}})$$
   $$CP_{2,y} = \min(\max(CP_{2,y}, M_{\text{top}}), M_{\text{top}} + H_{\text{plot}})$$

4. **Path Assembly**:
   - **Line Path (`d_line`)**:
     $$\text{Start: } \texttt{M } P_{0,x}, P_{0,y}$$
     $$\text{For each segment } i: \texttt{ C } CP_{1,x},CP_{1,y} \text{ } CP_{2,x},CP_{2,y} \text{ } P_{i+1,x},P_{i+1,y}$$
   - **Area Path (`d_area`)**:
     $$\texttt{M } P_{0,x}, (M_{\text{top}} + H_{\text{plot}}) \texttt{ L } P_{0,x}, P_{0,y}$$
     $$\text{Append all Bézier segments from line path}$$
     $$\texttt{ L } P_{N-1,x}, (M_{\text{top}} + H_{\text{plot}}) \texttt{ Z}$$

---

### 2.3 Bar Geometry & Layout Algorithms (`InteractiveBarChart`)

`InteractiveBarChart` supports two layout modes (**Grouped** and **Stacked**) and two orientations (**Vertical** and **Horizontal**).

#### Mode A: Vertical Grouped Columns
Let $K$ be the number of categories and $M$ be the number of series.
- Category step width: $S_x = \dfrac{W_{\text{plot}}}{K}$.
- Category slot width: $W_{\text{slot}} = S_x \times (1 - p_{\text{inner}})$, where inner padding $p_{\text{inner}} = 0.25$.
- Single bar width: $W_{\text{bar}} = \dfrac{W_{\text{slot}}}{M}$.
- For category $k \in [0, K-1]$ and series $m \in [0, M-1]$:
  $$X_{k,m} = M_{\text{left}} + k \cdot S_x + \dfrac{S_x - W_{\text{slot}}}{2} + m \cdot W_{\text{bar}}$$
  $$H_{k,m} = \left( \dfrac{v_{k,m}}{Y_{\max}} \right) \times H_{\text{plot}}$$
  $$Y_{k,m} = M_{\text{top}} + H_{\text{plot}} - H_{k,m}$$

#### Mode B: Vertical Stacked Columns
In stacked mode, all series for category $k$ share the full slot width $W_{\text{bar}} = W_{\text{slot}}$.
- Cumulative sum: $S_{\text{total}, k} = \sum_{m=0}^{M-1} v_{k,m}$.
- Maximum stacked sum: $Y_{\max,\text{stacked}} = \max_k(S_{\text{total}, k}) \times 1.10$.
- For each segment $m$ from bottom to top:
  $$Y_{\text{base}} = M_{\text{top}} + H_{\text{plot}} - \left( \dfrac{\sum_{j=0}^{m-1} v_{k,j}}{Y_{\max,\text{stacked}}} \right) \times H_{\text{plot}}$$
  $$\Delta H_{k,m} = \left( \dfrac{v_{k,m}}{Y_{\max,\text{stacked}}} \right) \times H_{\text{plot}}$$
  $$Y_{\text{top}} = Y_{\text{base}} - \Delta H_{k,m}$$

#### Top-Corner Radius Path Generator
Standard `<rect rx="r">` rounds all 4 corners, which creates an undesirable gap at the baseline. To round **only** the top corners:
$$\begin{aligned}
\text{Path}(x, y, w, h, r) = \;& \texttt{M } x, (y + h) \\
& \texttt{L } x, (y + r) \\
& \texttt{Q } x, y \text{ } (x + r), y \\
& \texttt{L } (x + w - r), y \\
& \texttt{Q } (x + w), y \text{ } (x + w), (y + r) \\
& \texttt{L } (x + w), (y + h) \texttt{ Z}
\end{aligned}$$
*(When $h < r$, radius is automatically clamped to $h$ to avoid degenerate paths).*

---

### 2.4 Arc Trigonometry & Donut Geometry (`InteractiveDonutChart`)

`InteractiveDonutChart` renders full $360^\circ$ circular slices using SVG path arcs (`M ... A ...`).

#### Radial Parameters
- Center point: $C_x = \dfrac{W}{2}, \; C_y = \dfrac{H}{2}$.
- Outer radius: $R_{\text{outer}} = \min(C_x, C_y) - M_{\text{margin}}$ (with $M_{\text{margin}} = 16$).
- Inner radius: $R_{\text{inner}} = R_{\text{outer}} \times 0.68$ (creating the 32% ring thickness).
- Angular padding between slices: $\alpha_{\text{pad}} = 0.025 \text{ rad} \approx 1.43^\circ$.

#### Arc Vertex Equations
For slice $j$ with value $v_j$ in total $V_{\text{total}} = \sum_{k} v_k$:
- Normalized fraction: $f_j = \dfrac{v_j}{V_{\text{total}}}$.
- Angle domain: Slices begin at top-center ($-\dfrac{\pi}{2}$ rad) and rotate clockwise.
  $$\theta_{\text{start}, j} = -\dfrac{\pi}{2} + 2\pi \sum_{k < j} f_k + \dfrac{\alpha_{\text{pad}}}{2}$$
  $$\theta_{\text{end}, j} = \theta_{\text{start}, j} + 2\pi f_j - \alpha_{\text{pad}}$$

The 4 boundary vertices of the donut sector are:
$$P_1 = (C_x + R_{\text{outer}} \cos \theta_{\text{start}}, \; C_y + R_{\text{outer}} \sin \theta_{\text{start}})$$
$$P_2 = (C_x + R_{\text{outer}} \cos \theta_{\text{end}}, \; C_y + R_{\text{outer}} \sin \theta_{\text{end}})$$
$$P_3 = (C_x + R_{\text{inner}} \cos \theta_{\text{end}}, \; C_y + R_{\text{inner}} \sin \theta_{\text{end}})$$
$$P_4 = (C_x + R_{\text{inner}} \cos \theta_{\text{start}}, \; C_y + R_{\text{inner}} \sin \theta_{\text{start}})$$

Large Arc Flag determination:
$$\Delta \theta = \theta_{\text{end}} - \theta_{\text{start}}, \quad \text{largeArcFlag} = \begin{cases} 1 & \text{if } \Delta \theta > \pi \\ 0 & \text{otherwise} \end{cases}$$

#### Sector Path Command
$$\begin{aligned}
d = \;& \texttt{M } P_{1,x}, P_{1,y} \\
& \texttt{A } R_{\text{outer}}, R_{\text{outer}} \text{ } 0 \text{ } \text{largeArcFlag} \text{ } 1 \text{ } P_{2,x}, P_{2,y} \\
& \texttt{L } P_{3,x}, P_{3,y} \\
& \texttt{A } R_{\text{inner}}, R_{\text{inner}} \text{ } 0 \text{ } \text{largeArcFlag} \text{ } 0 \text{ } P_{4,x}, P_{4,y} \texttt{ Z}
\end{aligned}$$

#### Hover Centroid Translation
When segment $j$ is hovered, it expands radially outward by distance $\delta = 5\text{px}$ along its bisector angle $\theta_{\text{mid}} = \dfrac{\theta_{\text{start}} + \theta_{\text{end}}}{2}$:
$$\Delta X = \delta \cos \theta_{\text{mid}}, \quad \Delta Y = \delta \sin \theta_{\text{mid}}$$
Applied via SVG attribute: `transform="translate(${DeltaX}, ${DeltaY})"`.

---

### 2.5 Radial Gauge Geometry (`InteractiveGaugeChart`)

`InteractiveGaugeChart` renders an operational $180^\circ$ semi-circular dial representing posture risk (0–100 or Sentinel Risk Score).

#### Gauge Geometry
- Center pivot: $C_x = \dfrac{W}{2}, \; C_y = H - 24$.
- Gauge outer radius: $R = \min\left(\dfrac{W}{2} - 28, \; C_y - 20\right)$.
- Track thickness: $T_{\text{track}} = 16\text{px}$, inner radius $R_{\text{inner}} = R - T_{\text{track}}$.
- Angular mapping: Dial runs from left ($\phi = \pi$ rad, $180^\circ$) over top ($\phi = \dfrac{\pi}{2}$ rad, $90^\circ$) to right ($\phi = 0$ rad, $0^\circ$).
  For any score $S \in [0, 100]$:
  $$\phi(S) = \pi - \left(\dfrac{S}{100}\right) \times \pi = \pi \left(1 - \dfrac{S}{100}\right)$$

Cartesian coordinates along gauge arc:
$$x(\phi) = C_x + r \cos \phi$$
$$y(\phi) = C_y - r \sin \phi \quad (\text{since SVG } y \text{ increases downward})$$

#### Tri-Zone Thresholds
The background dial renders 3 visual zones:
1. **Low / Safe Zone**: $S \in [0, 35)$ $\to$ Emerald (`#10B981`)
2. **Medium / Elevated Zone**: $S \in [35, 70)$ $\to$ Amber (`#F59E0B`)
3. **High / Critical Zone**: $S \in [70, 100]$ $\to$ Rose (`#EF4444`)

#### Indicator Pip & Active Sweep Arc
- Sweep arc from left ($\phi = \pi$) to current angle $\phi(S)$.
- Glowing needle pip positioned at center radius $R_{\text{mid}} = R - \dfrac{T_{\text{track}}}{2}$:
  $$X_{\text{pip}} = C_x + R_{\text{mid}} \cos \phi(S)$$
  $$Y_{\text{pip}} = C_y - R_{\text{mid}} \sin \phi(S)$$
- Center readout:
  - Numerical value: $S$ formatted to 1 decimal place.
  - Risk posture badge: `OPTIMAL` (Emerald), `ELEVATED` (Amber), or `CRITICAL` (Rose).

---

## 3. Detailed Component Technical Specifications

### 3.1 `InteractiveAreaChart.tsx`

```typescript
export interface AreaChartSeries {
  id: string;
  name: string;
  color: string;           // Hex or RGB string (e.g. '#06B6D4')
  dataKey: string;         // Key in data item corresponding to number
  dashed?: boolean;
}

export interface InteractiveAreaChartProps {
  data: Array<Record<string, any>>;
  xKey: string;            // Key for X-axis label (e.g. 'date')
  series: AreaChartSeries[];
  height?: number;         // Default: 260
  yDomain?: [number, number]; // Optional fixed domain
  valueFormatter?: (value: number) => string;
  title?: string;
  subtitle?: string;
  showGrid?: boolean;      // Default: true
  showCrosshair?: boolean; // Default: true
  className?: string;
}
```

#### Key Architecture & Interaction Rules
1. **Responsive Measurement**: Employs `useChartDimensions()` ref hook returning `{ width, height }`.
2. **Event Tracking**:
   - `onMouseMove` / `onTouchMove` captures client coordinates, computes offset relative to chart bounds.
   - Computes nearest data index: `index = Math.round(((clientX - left) / plotWidth) * (N - 1))`.
   - Clamped to $[0, N-1]$.
3. **Crosshair & Highlight**:
   - Line: `<line x1={x} y1={M.top} x2={x} y2={M.top + H_plot} stroke="rgb(6,182,212)" strokeOpacity="0.45" strokeDasharray="3 3" />`
   - Point marker: Outer pulse `<circle cx={x} cy={y} r="8" fill={color} fillOpacity="0.2" className="animate-ping" />` and solid core `<circle cx={x} cy={y} r="4.5" fill="#070B14" stroke={color} strokeWidth="2.5" />`.
4. **Floating Glass Tooltip**:
   - Dynamic positioning: Tooltip X offset defaults to `x + 12px`. If `x + 12px + tooltipWidth > width`, flips to `x - tooltipWidth - 12px`.
   - Content: Formatted date header, series indicator dots with series names, and formatted metric values.
5. **Decimated X-Axis Ticks**:
   - If $N > 10$, X-axis labels are filtered to avoid text overlap: displays tick only if `idx % Math.ceil(N / 7) === 0` or `idx === N - 1`.

---

### 3.2 `InteractiveBarChart.tsx`

```typescript
export interface BarChartSeries {
  id: string;
  name: string;
  color: string;
  dataKey: string;
}

export interface InteractiveBarChartProps {
  data: Array<Record<string, any>>;
  categoryKey: string;     // Key for category name (e.g. 'module_name')
  series: BarChartSeries[];
  mode?: 'grouped' | 'stacked'; // Default: 'grouped'
  orientation?: 'vertical' | 'horizontal'; // Default: 'vertical'
  height?: number;         // Default: 260
  valueFormatter?: (value: number) => string;
  title?: string;
  subtitle?: string;
  showGrid?: boolean;
  className?: string;
}
```

#### Key Architecture & Interaction Rules
1. **Orientation Support**:
   - `vertical`: standard column chart with bottom categories and vertical height bars.
   - `horizontal`: row bar chart with left categories and horizontal length bars.
2. **Hover Highlight State**:
   - Category hover band: Semi-transparent vertical rect spanning full plot height behind active column.
   - Brightness elevation: Hovered bar renders at `fillOpacity="1.0"` with specular drop-shadow; non-hovered bars dim to `fillOpacity="0.5"`.
3. **Stacked Stacking Algorithm**:
   - Accumulates running baseline for stacked segments.
   - Only the uppermost segment with $v > 0$ gets top rounded corners.

---

### 3.3 `InteractiveDonutChart.tsx`

```typescript
export interface DonutSegment {
  id: string;
  label: string;
  value: number;
  color: string;
  formattedValue?: string;
}

export interface InteractiveDonutChartProps {
  data: DonutSegment[];
  height?: number;         // Default: 260
  innerRadiusRatio?: number; // Default: 0.68
  padAngle?: number;       // Default: 0.025
  primaryLabel?: string;   // Default: 'TOTAL'
  centerValue?: string | number; // Override center readout
  centerLabel?: string;
  showLegend?: boolean;    // Default: true
  legendPosition?: 'bottom' | 'right'; // Default: 'bottom'
  valueFormatter?: (value: number) => string;
  className?: string;
}
```

#### Key Architecture & Interaction Rules
1. **SVG Arc Path Engine**:
   - Standard SVG `M... A... L... A... Z` path generator supporting segments up to $360^\circ$.
   - Handles edge case of a single 100% slice (where start and end angles coincide) by rendering two semicircular $180^\circ$ arcs.
2. **Centroid Hover Displacement**:
   - Hovered slice transitions outward by 5px along the slice's angular bisector using CSS `transform` and cubic-bezier easing.
3. **Center Donut Hole Readout**:
   - Normal state: Displays total metric sum $\sum v_j$ and `primaryLabel` (e.g. "TOTAL FINDINGS").
   - Hovered state: Dynamically switches to hovered slice count and segment label with matching text color.
4. **Interactive Synchronized Legend**:
   - Hovering over a legend item triggers hover state on the corresponding donut segment.
   - Legend shows color swatch, segment label, raw value, and percentage share.

---

### 3.4 `InteractiveGaugeChart.tsx`

```typescript
export interface GaugeThreshold {
  value: number;           // Upper boundary of zone
  label: string;           // E.g. 'OPTIMAL', 'ELEVATED', 'CRITICAL'
  color: string;           // Hex or Tailwind color class
}

export interface InteractiveGaugeChartProps {
  value: number;           // 0 to 100
  minValue?: number;       // Default: 0
  maxValue?: number;       // Default: 100
  title?: string;
  subtitle?: string;
  height?: number;         // Default: 220
  postureText?: string;    // Custom posture text override
  thresholds?: GaugeThreshold[];
  showMinMax?: boolean;    // Default: true
  className?: string;
}
```

#### Key Architecture & Interaction Rules
1. **180° Semi-Circular Radial Dial**:
   - Center pivot $(C_x, C_y)$ anchored at the bottom edge.
   - 3 colored track segments forming the background track.
2. **Dynamic Value Sweep & Needle Pip**:
   - Foreground arc sweeps from $0^\circ$ to the exact proportional angle.
   - Glowing indicator pip at the apex of the active value arc.
3. **Central Posture Badge**:
   - Large bold monospace numerical readout.
   - Color-coded posture badge pill (`CRITICAL RISK`, `ELEVATED`, `OPTIMAL`).

---

## 4. Backend `/api/v1/metrics/charts/*` Interfaces & Data Adapters

Below are the exact TypeScript interfaces matching backend response payloads from `backend/app/api/metrics.py`, alongside adapter transformation functions.

### 4.1 TypeScript Data Schemas

```typescript
// ----------------------------------------------------------------------------
// Backend API Response Schemas (/api/v1/metrics/charts/*)
// ----------------------------------------------------------------------------

/** Response from GET /api/v1/metrics/severity-distribution */
export type SeverityDistributionResponse = Record<
  'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO',
  number
>;

/** Item in array from GET /api/v1/metrics/charts/vulnerability-trend?days=14 */
export interface VulnerabilityTrendItem {
  date: string;
  new_findings: number;
  fixed_findings: number;
  reopened_findings: number;
}

/** Item in array from GET /api/v1/metrics/charts/module-risk */
export interface ModuleRiskItem {
  module_key: string;
  module_name: string;
  risk_score: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  total_findings: number;
}

/** Response from GET /api/v1/metrics/charts/coverage */
export interface AssessmentCoverageResponse {
  total_targets: number;
  assessed_today: number;
  pending_assessment: number;
  coverage_percentage: number;
}

/** Item in array from GET /api/v1/metrics/charts/risk-trend?days=14 */
export interface RiskTrendItem {
  date: string;
  risk_score: number;
  active_findings: number;
}

/** Item in array from GET /api/v1/metrics/charts/scanner-performance */
export interface ScannerPerformanceItem {
  engine: string;
  total_executions: number;
  completed: number;
  failed: number;
  success_rate: number;
  avg_duration_seconds: number;
}

/** Response from GET /api/v1/metrics/charts/intelligence-activity */
export interface IntelligenceActivityResponse {
  total_cves_indexed: number;
  cisa_kev_active: number;
  high_epss_exploitable: number;
  detection_rules_active: number;
  last_sync: string;
}

/** Response from GET /api/v1/metrics/charts/remediation-progress */
export type RemediationProgressResponse = Record<
  'OPEN' | 'IN_REMEDIATION' | 'FIXED' | 'REOPENED' | 'ACCEPTED_RISK' | 'FALSE_POSITIVE',
  number
>;
```

### 4.2 Data Adapters for Dashboard Integration

```typescript
// ----------------------------------------------------------------------------
// Adapter Functions: Transforming API data into Chart Engine Props
// ----------------------------------------------------------------------------

import { DonutSegment } from './InteractiveDonutChart';
import { BarChartSeries } from './InteractiveBarChart';
import { AreaChartSeries } from './InteractiveAreaChart';

/**
 * Transforms /api/v1/metrics/severity-distribution into InteractiveDonutChart segments
 */
export function adaptSeverityToDonut(dist: SeverityDistributionResponse): DonutSegment[] {
  const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: '#EF4444', // Rose
    HIGH: '#F97316',     // Orange
    MEDIUM: '#F59E0B',   // Amber
    LOW: '#10B981',      // Emerald
    INFO: '#06B6D4',     // Cyan
  };

  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const;
  return order
    .filter((sev) => (dist[sev] || 0) > 0 || Object.values(dist).every((v) => v === 0))
    .map((sev) => ({
      id: sev,
      label: sev,
      value: dist[sev] || 0,
      color: SEVERITY_COLORS[sev] || '#64748B',
    }));
}

/**
 * Transforms /api/v1/metrics/charts/vulnerability-trend into InteractiveAreaChart props
 */
export function adaptVulnerabilityTrend(data: VulnerabilityTrendItem[]): {
  data: VulnerabilityTrendItem[];
  series: AreaChartSeries[];
} {
  return {
    data,
    series: [
      { id: 'new', name: 'New Findings', color: '#06B6D4', dataKey: 'new_findings' },
      { id: 'fixed', name: 'Remediated', color: '#10B981', dataKey: 'fixed_findings' },
      { id: 'reopened', name: 'Reopened', color: '#F59E0B', dataKey: 'reopened_findings', dashed: true },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/module-risk into InteractiveBarChart props
 */
export function adaptModuleRisk(data: ModuleRiskItem[]): {
  data: ModuleRiskItem[];
  series: BarChartSeries[];
} {
  return {
    data,
    series: [
      { id: 'risk_score', name: 'Risk Score (SRS)', color: '#EF4444', dataKey: 'risk_score' },
      { id: 'total_findings', name: 'Total Findings', color: '#06B6D4', dataKey: 'total_findings' },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/scanner-performance into InteractiveBarChart props
 */
export function adaptScannerPerformance(data: ScannerPerformanceItem[]): {
  data: ScannerPerformanceItem[];
  series: BarChartSeries[];
} {
  return {
    data,
    series: [
      { id: 'completed', name: 'Completed Scans', color: '#10B981', dataKey: 'completed' },
      { id: 'failed', name: 'Failed Scans', color: '#EF4444', dataKey: 'failed' },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/remediation-progress into horizontal InteractiveBarChart or Donut
 */
export function adaptRemediationProgressToDonut(data: RemediationProgressResponse): DonutSegment[] {
  const STATUS_COLORS: Record<string, string> = {
    OPEN: '#EF4444',
    IN_REMEDIATION: '#F59E0B',
    FIXED: '#10B981',
    REOPENED: '#EC4899',
    ACCEPTED_RISK: '#64748B',
    FALSE_POSITIVE: '#3B82F6',
  };

  return Object.entries(data)
    .filter(([_, count]) => count > 0)
    .map(([status, count]) => ({
      id: status,
      label: status.replace('_', ' '),
      value: count,
      color: STATUS_COLORS[status] || '#64748B',
    }));
}
```

---

## 5. File Layout & Barrel Export (`frontend/src/components/charts/`)

```
frontend/src/components/charts/
├── types.ts                    # Shared chart data interfaces, dimensions, prop contracts
├── useChartDimensions.ts       # Robust ResizeObserver hook with SSR fallback
├── ChartTooltip.tsx            # Floating glass tooltip primitive
├── InteractiveAreaChart.tsx    # Smooth Bézier multi-series area & line chart
├── InteractiveBarChart.tsx     # Grouped & stacked column/bar chart with top-radius
├── InteractiveDonutChart.tsx   # SVG arc donut chart with center metric readout & legend
├── InteractiveGaugeChart.tsx   # 180° radial risk gauge with dynamic zone needle
└── index.ts                    # Clean barrel export
```

### 5.1 Barrel Export (`index.ts`)

```typescript
export * from './types';
export * from './useChartDimensions';
export * from './ChartTooltip';
export * from './InteractiveAreaChart';
export * from './InteractiveBarChart';
export * from './InteractiveDonutChart';
export * from './InteractiveGaugeChart';
```

---

## 6. Full Implementation Blueprints for Worker

Below are the complete, drop-in production implementations for every module in `frontend/src/components/charts/`.

### 6.1 `frontend/src/components/charts/types.ts`

```typescript
import React from 'react';

export interface ChartMargin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface ChartDimensions {
  width: number;
  height: number;
  plotWidth: number;
  plotHeight: number;
  margin: ChartMargin;
}

export interface AreaSeriesConfig {
  id: string;
  name: string;
  color: string;
  dataKey: string;
  dashed?: boolean;
}

export interface BarSeriesConfig {
  id: string;
  name: string;
  color: string;
  dataKey: string;
}

export interface DonutSegmentItem {
  id: string;
  label: string;
  value: number;
  color: string;
  formattedValue?: string;
}

export interface GaugeZone {
  max: number;
  label: string;
  color: string;
}

export interface TooltipPayloadItem {
  name: string;
  value: number | string;
  color: string;
}
```

---

### 6.2 `frontend/src/components/charts/useChartDimensions.ts`

```typescript
import { useState, useEffect, useRef } from 'react';
import { ChartDimensions, ChartMargin } from './types';

const DEFAULT_MARGIN: ChartMargin = { top: 16, right: 20, bottom: 32, left: 44 };

export function useChartDimensions(
  customMargin: Partial<ChartMargin> = {},
  defaultHeight: number = 260
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const margin: ChartMargin = { ...DEFAULT_MARGIN, ...customMargin };

  const [dimensions, setDimensions] = useState<ChartDimensions>({
    width: 500,
    height: defaultHeight,
    plotWidth: Math.max(0, 500 - margin.left - margin.right),
    plotHeight: Math.max(0, defaultHeight - margin.top - margin.bottom),
    margin,
  });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateDimensions = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.max(200, Math.floor(rect.width));
      const height = defaultHeight;

      setDimensions({
        width,
        height,
        plotWidth: Math.max(0, width - margin.left - margin.right),
        plotHeight: Math.max(0, height - margin.top - margin.bottom),
        margin,
      });
    };

    updateDimensions();

    const resizeObserver = new ResizeObserver(() => {
      updateDimensions();
    });

    resizeObserver.observe(element);
    return () => {
      resizeObserver.disconnect();
    };
  }, [defaultHeight, margin.top, margin.right, margin.bottom, margin.left]);

  return { containerRef, dimensions };
}
```

---

### 6.3 `frontend/src/components/charts/ChartTooltip.tsx`

```typescript
import React from 'react';
import { TooltipPayloadItem } from './types';

export interface ChartTooltipProps {
  x: number;
  y: number;
  containerWidth: number;
  visible: boolean;
  title?: string;
  payload?: TooltipPayloadItem[];
}

export const ChartTooltip: React.FC<ChartTooltipProps> = ({
  x,
  y,
  containerWidth,
  visible,
  title,
  payload,
}) => {
  if (!visible || !payload || payload.length === 0) return null;

  // Auto-flip tooltip if near the right edge
  const tooltipWidth = 160;
  const isRightEdge = x + tooltipWidth + 24 > containerWidth;
  const leftPos = isRightEdge ? x - tooltipWidth - 12 : x + 12;

  return (
    <div
      className="absolute pointer-events-none z-30 transition-all duration-75 ease-out"
      style={{
        left: `${leftPos}px`,
        top: `${Math.max(8, y - 24)}px`,
      }}
    >
      <div className="bg-cyber-900/95 backdrop-blur-md border border-white/10 rounded-xl p-3 shadow-2xl min-w-[140px] text-xs">
        {title && (
          <div className="font-semibold text-slate-300 pb-1.5 mb-1.5 border-b border-white/10 font-mono text-[11px]">
            {title}
          </div>
        )}
        <div className="space-y-1.5">
          {payload.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-1.5 text-slate-400">
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: item.color }}
                />
                <span className="truncate max-w-[90px]">{item.name}:</span>
              </div>
              <span className="font-mono font-bold text-white text-right">
                {item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
```

---

### 6.4 `frontend/src/components/charts/InteractiveAreaChart.tsx`

```typescript
'use client';

import React, { useState, useId, useMemo } from 'react';
import { useChartDimensions } from './useChartDimensions';
import { ChartTooltip } from './ChartTooltip';
import { AreaSeriesConfig } from './types';

export interface InteractiveAreaChartProps {
  data: Array<Record<string, any>>;
  xKey: string;
  series: AreaSeriesConfig[];
  height?: number;
  valueFormatter?: (val: number) => string;
  title?: string;
  subtitle?: string;
  showGrid?: boolean;
  className?: string;
}

export const InteractiveAreaChart: React.FC<InteractiveAreaChartProps> = ({
  data,
  xKey,
  series,
  height = 240,
  valueFormatter = (v) => v.toString(),
  title,
  subtitle,
  showGrid = true,
  className = '',
}) => {
  const chartId = useId();
  const { containerRef, dimensions } = useChartDimensions({ top: 16, right: 16, bottom: 28, left: 40 }, height);
  const { width, plotWidth, plotHeight, margin } = dimensions;

  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Compute maximum Y across all series
  const maxY = useMemo(() => {
    let max = 0;
    data.forEach((d) => {
      series.forEach((s) => {
        const val = Number(d[s.dataKey]) || 0;
        if (val > max) max = val;
      });
    });
    return max === 0 ? 10 : Math.ceil(max * 1.15);
  }, [data, series]);

  // Points for each series
  const seriesPoints = useMemo(() => {
    if (!data.length) return [];
    const n = data.length;

    return series.map((s) => {
      const points = data.map((d, i) => {
        const x = n === 1 ? margin.left + plotWidth / 2 : margin.left + (i / (n - 1)) * plotWidth;
        const val = Number(d[s.dataKey]) || 0;
        const y = margin.top + plotHeight - (val / maxY) * plotHeight;
        return { x, y, val };
      });
      return { ...s, points };
    });
  }, [data, series, maxY, plotWidth, plotHeight, margin.left, margin.top]);

  // Catmull-Rom to Cubic Bézier spline generator
  const generateSplinePaths = (pts: Array<{ x: number; y: number }>) => {
    if (pts.length < 2) {
      if (pts.length === 1) {
        const p = pts[0];
        return {
          line: `M ${p.x - 5},${p.y} L ${p.x + 5},${p.y}`,
          area: `M ${p.x - 5},${margin.top + plotHeight} L ${p.x - 5},${p.y} L ${p.x + 5},${p.y} L ${p.x + 5},${margin.top + plotHeight} Z`,
        };
      }
      return { line: '', area: '' };
    }

    const tau = 0.2;
    let linePath = `M ${pts[0].x},${pts[0].y}`;

    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = i > 0 ? pts[i - 1] : pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = i < pts.length - 2 ? pts[i + 2] : p2;

      let cp1x = p1.x + (p2.x - p0.x) * tau;
      let cp1y = p1.y + (p2.y - p0.y) * tau;
      let cp2x = p2.x - (p3.x - p1.x) * tau;
      let cp2y = p2.y - (p3.y - p1.y) * tau;

      // Baseline bounding
      const bottom = margin.top + plotHeight;
      cp1y = Math.min(Math.max(cp1y, margin.top), bottom);
      cp2y = Math.min(Math.max(cp2y, margin.top), bottom);

      linePath += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }

    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPath = `M ${first.x},${margin.top + plotHeight} L ${first.x},${first.y} ${linePath.substring(linePath.indexOf('C'))} L ${last.x},${margin.top + plotHeight} Z`;

    return { line: linePath, area: areaPath };
  };

  // Mouse event handlers
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!data.length) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const xPos = e.clientX - rect.left - margin.left;
    const ratio = Math.max(0, Math.min(1, xPos / plotWidth));
    const idx = Math.round(ratio * (data.length - 1));
    setHoveredIndex(idx);
  };

  const handleMouseLeave = () => {
    setHoveredIndex(null);
  };

  // Grid ticks
  const yTicks = [0, Math.round(maxY * 0.33), Math.round(maxY * 0.66), maxY];

  const activeX = hoveredIndex !== null && data.length > 1
    ? margin.left + (hoveredIndex / (data.length - 1)) * plotWidth
    : null;

  return (
    <div className={`relative flex flex-col ${className}`} ref={containerRef}>
      {(title || subtitle) && (
        <div className="mb-2">
          {title && <h3 className="text-sm font-bold text-white tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
      )}

      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg
          width={width}
          height={height}
          className="overflow-visible select-none cursor-crosshair"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            {series.map((s, idx) => (
              <linearGradient
                key={s.id}
                id={`grad-${chartId}-${idx}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={s.color} stopOpacity="0.32" />
                <stop offset="85%" stopColor={s.color} stopOpacity="0.04" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0.0" />
              </linearGradient>
            ))}
          </defs>

          {/* Grid lines */}
          {showGrid && (
            <g className="grid-lines opacity-40">
              {yTicks.map((val, i) => {
                const y = margin.top + plotHeight - (val / maxY) * plotHeight;
                return (
                  <g key={i}>
                    <line
                      x1={margin.left}
                      y1={y}
                      x2={margin.left + plotWidth}
                      y2={y}
                      stroke="rgba(255, 255, 255, 0.08)"
                      strokeDasharray="3 3"
                    />
                    <text
                      x={margin.left - 8}
                      y={y + 3}
                      textAnchor="end"
                      className="text-[10px] font-mono fill-slate-500"
                    >
                      {valueFormatter(val)}
                    </text>
                  </g>
                );
              })}
            </g>
          )}

          {/* Area & Line paths */}
          {seriesPoints.map((s, idx) => {
            const { line, area } = generateSplinePaths(s.points);
            return (
              <g key={s.id} className="series-group">
                <path d={area} fill={`url(#grad-${chartId}-${idx})`} />
                <path
                  d={line}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2"
                  strokeDasharray={s.dashed ? '4 3' : undefined}
                />
              </g>
            );
          })}

          {/* Active Hover Crosshair & Glowing Points */}
          {activeX !== null && hoveredIndex !== null && (
            <g className="hover-crosshair pointer-events-none">
              <line
                x1={activeX}
                y1={margin.top}
                x2={activeX}
                y2={margin.top + plotHeight}
                stroke="#06B6D4"
                strokeOpacity="0.5"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
              {seriesPoints.map((s) => {
                const p = s.points[hoveredIndex];
                if (!p) return null;
                return (
                  <g key={s.id}>
                    <circle cx={p.x} cy={p.y} r="7" fill={s.color} fillOpacity="0.25" />
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r="4"
                      fill="#070B14"
                      stroke={s.color}
                      strokeWidth="2.5"
                    />
                  </g>
                );
              })}
            </g>
          )}

          {/* X Axis Labels */}
          <g className="x-axis">
            {data.map((d, i) => {
              const n = data.length;
              const x = n === 1 ? margin.left + plotWidth / 2 : margin.left + (i / (n - 1)) * plotWidth;
              const step = Math.max(1, Math.ceil(n / 6));
              if (i % step !== 0 && i !== n - 1) return null;

              return (
                <text
                  key={i}
                  x={x}
                  y={margin.top + plotHeight + 18}
                  textAnchor="middle"
                  className="text-[10px] font-mono fill-slate-400"
                >
                  {d[xKey]}
                </text>
              );
            })}
          </g>
        </svg>

        {/* Floating Tooltip */}
        {hoveredIndex !== null && activeX !== null && (
          <ChartTooltip
            x={activeX}
            y={margin.top + 20}
            containerWidth={width}
            visible={true}
            title={data[hoveredIndex]?.[xKey]}
            payload={series.map((s) => ({
              name: s.name,
              value: valueFormatter(Number(data[hoveredIndex]?.[s.dataKey]) || 0),
              color: s.color,
            }))}
          />
        )}
      </div>

      {/* Synchronized Legend */}
      <div className="flex flex-wrap items-center justify-center gap-5 mt-2 text-xs">
        {series.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="font-medium text-slate-400">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
```

---

### 6.5 `frontend/src/components/charts/InteractiveBarChart.tsx`

```typescript
'use client';

import React, { useState, useMemo } from 'react';
import { useChartDimensions } from './useChartDimensions';
import { ChartTooltip } from './ChartTooltip';
import { BarSeriesConfig } from './types';

export interface InteractiveBarChartProps {
  data: Array<Record<string, any>>;
  categoryKey: string;
  series: BarSeriesConfig[];
  mode?: 'grouped' | 'stacked';
  orientation?: 'vertical' | 'horizontal';
  height?: number;
  valueFormatter?: (val: number) => string;
  title?: string;
  subtitle?: string;
  showGrid?: boolean;
  className?: string;
}

export const InteractiveBarChart: React.FC<InteractiveBarChartProps> = ({
  data,
  categoryKey,
  series,
  mode = 'grouped',
  orientation = 'vertical',
  height = 240,
  valueFormatter = (v) => v.toString(),
  title,
  subtitle,
  showGrid = true,
  className = '',
}) => {
  const { containerRef, dimensions } = useChartDimensions(
    orientation === 'horizontal'
      ? { top: 16, right: 24, bottom: 24, left: 100 }
      : { top: 16, right: 16, bottom: 28, left: 40 },
    height
  );
  const { width, plotWidth, plotHeight, margin } = dimensions;

  const [hoveredCategory, setHoveredCategory] = useState<number | null>(null);

  // Compute maximum values
  const { maxVal, stackedMax } = useMemo(() => {
    let mSingle = 0;
    let mStacked = 0;
    data.forEach((d) => {
      let sum = 0;
      series.forEach((s) => {
        const val = Number(d[s.dataKey]) || 0;
        if (val > mSingle) mSingle = val;
        sum += val;
      });
      if (sum > mStacked) mStacked = sum;
    });
    return {
      maxVal: mSingle === 0 ? 10 : Math.ceil(mSingle * 1.15),
      stackedMax: mStacked === 0 ? 10 : Math.ceil(mStacked * 1.12),
    };
  }, [data, series]);

  const yMax = mode === 'stacked' ? stackedMax : maxVal;
  const kCount = Math.max(1, data.length);

  // Top-radius rounded SVG path helper
  const roundedBarPath = (x: number, y: number, w: number, h: number, r: number = 3) => {
    if (h <= 0 || w <= 0) return '';
    const safeR = Math.min(r, h, w / 2);
    return `M ${x},${y + h} L ${x},${y + safeR} Q ${x},${y} ${x + safeR},${y} L ${x + w - safeR},${y} Q ${x + w},${y} ${x + w},${y + safeR} L ${x + w},${y + h} Z`;
  };

  return (
    <div className={`relative flex flex-col ${className}`} ref={containerRef}>
      {(title || subtitle) && (
        <div className="mb-2">
          {title && <h3 className="text-sm font-bold text-white tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
      )}

      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg
          width={width}
          height={height}
          className="overflow-visible select-none"
          onMouseLeave={() => setHoveredCategory(null)}
        >
          {/* Vertical Grid lines */}
          {showGrid && orientation === 'vertical' && (
            <g className="grid-lines opacity-30">
              {[0, 0.5, 1].map((pct, idx) => {
                const y = margin.top + plotHeight - pct * plotHeight;
                return (
                  <line
                    key={idx}
                    x1={margin.left}
                    y1={y}
                    x2={margin.left + plotWidth}
                    y2={y}
                    stroke="rgba(255, 255, 255, 0.1)"
                    strokeDasharray="3 3"
                  />
                );
              })}
            </g>
          )}

          {/* Render Bars */}
          {data.map((d, kIdx) => {
            const isHovered = hoveredCategory === kIdx;

            if (orientation === 'vertical') {
              const stepX = plotWidth / kCount;
              const slotW = stepX * 0.72;
              const catX = margin.left + kIdx * stepX + (stepX - slotW) / 2;

              if (mode === 'grouped') {
                const barW = slotW / Math.max(1, series.length);

                return (
                  <g
                    key={kIdx}
                    onMouseEnter={() => setHoveredCategory(kIdx)}
                    className="cursor-pointer"
                  >
                    {/* Hover column background highlight */}
                    {isHovered && (
                      <rect
                        x={catX - 4}
                        y={margin.top}
                        width={slotW + 8}
                        height={plotHeight}
                        fill="rgba(255, 255, 255, 0.04)"
                        rx="4"
                      />
                    )}

                    {series.map((s, sIdx) => {
                      const val = Number(d[s.dataKey]) || 0;
                      const barH = (val / yMax) * plotHeight;
                      const barX = catX + sIdx * barW;
                      const barY = margin.top + plotHeight - barH;

                      return (
                        <path
                          key={s.id}
                          d={roundedBarPath(barX, barY, barW - 2, barH, 3)}
                          fill={s.color}
                          fillOpacity={hoveredCategory === null || isHovered ? 1.0 : 0.45}
                          className="transition-all duration-150"
                        />
                      );
                    })}

                    {/* Category X Label */}
                    <text
                      x={catX + slotW / 2}
                      y={margin.top + plotHeight + 18}
                      textAnchor="middle"
                      className="text-[10px] font-mono fill-slate-400"
                    >
                      {d[categoryKey]}
                    </text>
                  </g>
                );
              } else {
                // Stacked Vertical
                let currentY = margin.top + plotHeight;
                return (
                  <g
                    key={kIdx}
                    onMouseEnter={() => setHoveredCategory(kIdx)}
                    className="cursor-pointer"
                  >
                    {series.map((s) => {
                      const val = Number(d[s.dataKey]) || 0;
                      const segH = (val / yMax) * plotHeight;
                      currentY -= segH;

                      return (
                        <rect
                          key={s.id}
                          x={catX}
                          y={currentY}
                          width={slotW}
                          height={segH}
                          fill={s.color}
                          fillOpacity={hoveredCategory === null || isHovered ? 1.0 : 0.45}
                          rx={currentY <= margin.top + 2 ? 3 : 0}
                          className="transition-all duration-150"
                        />
                      );
                    })}

                    <text
                      x={catX + slotW / 2}
                      y={margin.top + plotHeight + 18}
                      textAnchor="middle"
                      className="text-[10px] font-mono fill-slate-400"
                    >
                      {d[categoryKey]}
                    </text>
                  </g>
                );
              }
            } else {
              // Horizontal Orientation
              const stepY = plotHeight / kCount;
              const slotH = stepY * 0.65;
              const catY = margin.top + kIdx * stepY + (stepY - slotH) / 2;
              const val = Number(d[series[0]?.dataKey]) || 0;
              const barLen = (val / yMax) * plotWidth;

              return (
                <g
                  key={kIdx}
                  onMouseEnter={() => setHoveredCategory(kIdx)}
                  className="cursor-pointer"
                >
                  <text
                    x={margin.left - 10}
                    y={catY + slotH / 2 + 4}
                    textAnchor="end"
                    className="text-[11px] font-medium fill-slate-300"
                  >
                    {d[categoryKey]}
                  </text>
                  <rect
                    x={margin.left}
                    y={catY}
                    width={Math.max(2, barLen)}
                    height={slotH}
                    fill={series[0]?.color || '#06B6D4'}
                    fillOpacity={hoveredCategory === null || isHovered ? 1.0 : 0.45}
                    rx="3"
                    className="transition-all duration-150"
                  />
                  <text
                    x={margin.left + barLen + 8}
                    y={catY + slotH / 2 + 4}
                    className="text-[10px] font-mono font-bold fill-slate-400"
                  >
                    {valueFormatter(val)}
                  </text>
                </g>
              );
            }
          })}
        </svg>

        {/* Floating Tooltip */}
        {hoveredCategory !== null && (
          <ChartTooltip
            x={
              orientation === 'vertical'
                ? margin.left + (hoveredCategory + 0.5) * (plotWidth / kCount)
                : margin.left + plotWidth / 2
            }
            y={margin.top + 20}
            containerWidth={width}
            visible={true}
            title={data[hoveredCategory]?.[categoryKey]}
            payload={series.map((s) => ({
              name: s.name,
              value: valueFormatter(Number(data[hoveredCategory]?.[s.dataKey]) || 0),
              color: s.color,
            }))}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center justify-center gap-5 mt-2 text-xs">
        {series.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: s.color }} />
            <span className="font-medium text-slate-400">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
```

---

### 6.6 `frontend/src/components/charts/InteractiveDonutChart.tsx`

```typescript
'use client';

import React, { useState, useMemo } from 'react';
import { useChartDimensions } from './useChartDimensions';
import { DonutSegmentItem } from './types';

export interface InteractiveDonutChartProps {
  data: DonutSegmentItem[];
  height?: number;
  innerRadiusRatio?: number;
  padAngle?: number;
  primaryLabel?: string;
  centerValue?: string | number;
  centerLabel?: string;
  showLegend?: boolean;
  valueFormatter?: (val: number) => string;
  title?: string;
  subtitle?: string;
  className?: string;
}

export const InteractiveDonutChart: React.FC<InteractiveDonutChartProps> = ({
  data,
  height = 240,
  innerRadiusRatio = 0.68,
  padAngle = 0.025,
  primaryLabel = 'TOTAL',
  centerValue,
  centerLabel,
  showLegend = true,
  valueFormatter = (v) => v.toString(),
  title,
  subtitle,
  className = '',
}) => {
  const { containerRef, dimensions } = useChartDimensions({ top: 10, right: 10, bottom: 10, left: 10 }, height);
  const { width } = dimensions;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const total = useMemo(() => {
    return data.reduce((acc, item) => acc + (item.value || 0), 0);
  }, [data]);

  const cx = width / 2;
  const cy = height / 2;
  const outerR = Math.min(cx, cy) - 16;
  const innerR = outerR * innerRadiusRatio;

  // Arc path generator
  const slices = useMemo(() => {
    if (total === 0) return [];
    let currentAngle = -Math.PI / 2;

    return data.map((item, idx) => {
      const fraction = item.value / total;
      const angleSpan = fraction * 2 * Math.PI;
      const startAngle = currentAngle + padAngle / 2;
      const endAngle = currentAngle + angleSpan - padAngle / 2;
      currentAngle += angleSpan;

      // Handle single full slice
      if (fraction >= 0.999) {
        return {
          ...item,
          path: `M ${cx},${cy - outerR} A ${outerR},${outerR} 0 1,1 ${cx},${cy + outerR} A ${outerR},${outerR} 0 1,1 ${cx},${cy - outerR} M ${cx},${cy - innerR} A ${innerR},${innerR} 0 1,0 ${cx},${cy + innerR} A ${innerR},${innerR} 0 1,0 ${cx},${cy - innerR} Z`,
          midAngle: 0,
        };
      }

      const x1 = cx + outerR * Math.cos(startAngle);
      const y1 = cy + outerR * Math.sin(startAngle);
      const x2 = cx + outerR * Math.cos(endAngle);
      const y2 = cy + outerR * Math.sin(endAngle);
      const x3 = cx + innerR * Math.cos(endAngle);
      const y3 = cy + innerR * Math.sin(endAngle);
      const x4 = cx + innerR * Math.cos(startAngle);
      const y4 = cy + innerR * Math.sin(startAngle);

      const largeArc = angleSpan > Math.PI ? 1 : 0;
      const path = `M ${x1},${y1} A ${outerR},${outerR} 0 ${largeArc},1 ${x2},${y2} L ${x3},${y3} A ${innerR},${innerR} 0 ${largeArc},0 ${x4},${y4} Z`;
      const midAngle = (startAngle + endAngle) / 2;

      return { ...item, path, midAngle };
    });
  }, [data, total, cx, cy, outerR, innerR, padAngle]);

  const activeSegment = hoveredIdx !== null ? data[hoveredIdx] : null;

  return (
    <div className={`relative flex flex-col items-center ${className}`} ref={containerRef}>
      {(title || subtitle) && (
        <div className="w-full mb-2 text-left">
          {title && <h3 className="text-sm font-bold text-white tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
      )}

      <div className="relative" style={{ width: `${width}px`, height: `${height}px` }}>
        <svg width={width} height={height} className="overflow-visible select-none">
          {/* Donut Slices */}
          {slices.map((slice, idx) => {
            const isHovered = hoveredIdx === idx;
            const dx = isHovered ? Math.cos(slice.midAngle) * 5 : 0;
            const dy = isHovered ? Math.sin(slice.midAngle) * 5 : 0;

            return (
              <path
                key={slice.id}
                d={slice.path}
                fill={slice.color}
                fillOpacity={hoveredIdx === null || isHovered ? 1.0 : 0.4}
                transform={`translate(${dx}, ${dy})`}
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
                className="cursor-pointer transition-all duration-150"
              />
            );
          })}

          {/* Center Readout */}
          <g className="center-text pointer-events-none">
            <text
              x={cx}
              y={cy - 2}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-2xl font-black font-mono fill-white"
            >
              {centerValue ?? (activeSegment ? activeSegment.value : total)}
            </text>
            <text
              x={cx}
              y={cy + 18}
              textAnchor="middle"
              dominantBaseline="middle"
              className="text-[10px] font-bold fill-slate-400 uppercase tracking-wider"
            >
              {centerLabel ?? (activeSegment ? activeSegment.label : primaryLabel)}
            </text>
          </g>
        </svg>
      </div>

      {/* Synchronized Legend */}
      {showLegend && (
        <div className="flex flex-wrap items-center justify-center gap-4 mt-3 text-xs">
          {data.map((item, idx) => {
            const isHovered = hoveredIdx === idx;
            const pct = total > 0 ? Math.round((item.value / total) * 100) : 0;

            return (
              <button
                key={item.id}
                type="button"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
                className={`flex items-center gap-2 px-2 py-1 rounded-lg transition-all ${
                  isHovered ? 'bg-white/10 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="font-medium">{item.label}</span>
                <span className="font-mono text-slate-300 font-bold">{valueFormatter(item.value)}</span>
                <span className="text-[10px] text-slate-500 font-mono">({pct}%)</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
```

---

### 6.7 `frontend/src/components/charts/InteractiveGaugeChart.tsx`

```typescript
'use client';

import React from 'react';
import { useChartDimensions } from './useChartDimensions';
import { GaugeZone } from './types';

export interface InteractiveGaugeChartProps {
  value: number; // 0 to 100
  minValue?: number;
  maxValue?: number;
  title?: string;
  subtitle?: string;
  height?: number;
  postureText?: string;
  zones?: GaugeZone[];
  className?: string;
}

const DEFAULT_ZONES: GaugeZone[] = [
  { max: 35, label: 'OPTIMAL', color: '#10B981' }, // Emerald
  { max: 70, label: 'ELEVATED', color: '#F59E0B' }, // Amber
  { max: 100, label: 'CRITICAL', color: '#EF4444' }, // Rose
];

export const InteractiveGaugeChart: React.FC<InteractiveGaugeChartProps> = ({
  value,
  minValue = 0,
  maxValue = 100,
  title,
  subtitle,
  height = 200,
  postureText,
  zones = DEFAULT_ZONES,
  className = '',
}) => {
  const { containerRef, dimensions } = useChartDimensions({ top: 12, right: 24, bottom: 16, left: 24 }, height);
  const { width } = dimensions;

  const clampedVal = Math.max(minValue, Math.min(maxValue, value));
  const normalizedRatio = (clampedVal - minValue) / (maxValue - minValue);

  // Active posture zone
  const activeZone = zones.find((z) => clampedVal <= z.max) || zones[zones.length - 1];

  const cx = width / 2;
  const cy = height - 20;
  const outerR = Math.min(cx - 24, cy - 20);
  const trackW = 16;
  const innerR = outerR - trackW;

  // Arc angle mapper: 180° dial from left (PI) to right (0)
  const angleForRatio = (ratio: number) => Math.PI * (1 - ratio);

  // Path generator for 180 degree gauge segments
  const makeGaugeArc = (rStart: number, rEnd: number) => {
    const aStart = angleForRatio(rStart);
    const aEnd = angleForRatio(rEnd);

    const x1 = cx + outerR * Math.cos(aStart);
    const y1 = cy - outerR * Math.sin(aStart);
    const x2 = cx + outerR * Math.cos(aEnd);
    const y2 = cy - outerR * Math.sin(aEnd);
    const x3 = cx + innerR * Math.cos(aEnd);
    const y3 = cy - innerR * Math.sin(aEnd);
    const x4 = cx + innerR * Math.cos(aStart);
    const y4 = cy - innerR * Math.sin(aStart);

    return `M ${x1},${y1} A ${outerR},${outerR} 0 0,1 ${x2},${y2} L ${x3},${y3} A ${innerR},${innerR} 0 0,0 ${x4},${y4} Z`;
  };

  // Needle Pip position
  const currentAngle = angleForRatio(normalizedRatio);
  const midR = outerR - trackW / 2;
  const pipX = cx + midR * Math.cos(currentAngle);
  const pipY = cy - midR * Math.sin(currentAngle);

  return (
    <div className={`relative flex flex-col items-center ${className}`} ref={containerRef}>
      {(title || subtitle) && (
        <div className="w-full mb-1 text-left">
          {title && <h3 className="text-sm font-bold text-white tracking-tight">{title}</h3>}
          {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
        </div>
      )}

      <div className="relative" style={{ width: `${width}px`, height: `${height}px` }}>
        <svg width={width} height={height} className="overflow-visible select-none">
          {/* Background Zone Arcs */}
          {zones.map((zone, idx) => {
            const prevMax = idx === 0 ? minValue : zones[idx - 1].max;
            const rStart = (prevMax - minValue) / (maxValue - minValue);
            const rEnd = (zone.max - minValue) / (maxValue - minValue);

            return (
              <path
                key={idx}
                d={makeGaugeArc(rStart, rEnd)}
                fill={zone.color}
                fillOpacity="0.22"
                stroke="rgba(255, 255, 255, 0.08)"
                strokeWidth="1"
              />
            );
          })}

          {/* Active Value Arc Sweep */}
          <path
            d={makeGaugeArc(0, normalizedRatio)}
            fill={activeZone.color}
            fillOpacity="0.9"
            className="transition-all duration-300"
          />

          {/* Glowing Indicator Pip */}
          <circle cx={pipX} cy={pipY} r="8" fill={activeZone.color} fillOpacity="0.3" className="animate-ping" />
          <circle cx={pipX} cy={pipY} r="4.5" fill="#070B14" stroke={activeZone.color} strokeWidth="2.5" />

          {/* Numerical Readout */}
          <text
            x={cx}
            y={cy - 34}
            textAnchor="middle"
            className="text-4xl font-black font-mono fill-white tracking-tight"
          >
            {clampedVal.toFixed(1)}
          </text>

          {/* Posture Badge */}
          <text
            x={cx}
            y={cy - 12}
            textAnchor="middle"
            fill={activeZone.color}
            className="text-xs font-bold font-mono tracking-wider"
          >
            {postureText || `${activeZone.label} RISK`}
          </text>

          {/* Min & Max Labels */}
          <text
            x={cx - outerR}
            y={cy + 16}
            textAnchor="middle"
            className="text-[10px] font-mono fill-slate-500"
          >
            {minValue}
          </text>
          <text
            x={cx + outerR}
            y={cy + 16}
            textAnchor="middle"
            className="text-[10px] font-mono fill-slate-500"
          >
            {maxValue}
          </text>
        </svg>
      </div>
    </div>
  );
};
```

---

## 7. Edge Case Handling & Performance Invariants

1. **Zero / Empty Data Invariant**:
   - When datasets are empty (`data = []`) or contain all zeros, charts gracefully render baseline grid marks and zero readouts without `NaN`, division-by-zero, or degenerate SVG path commands (`M NaN,NaN`).
2. **Single Data Point Invariant**:
   - In `InteractiveAreaChart`, a single data point renders a horizontal segment at $(x \pm 5\text{px})$ rather than crashing the Bézier polynomial math.
3. **No Horizontal Body Scroll**:
   - `ResizeObserver` measures container width accurately and clamps coordinates inside the bounding box.
4. **SSR & Hydration Safety**:
   - `useId()` produces deterministic SVG gradient IDs across server and client renders.
   - Initial width defaults to 500px until `ResizeObserver` attaches, preventing hydration mismatch.

---

## 8. Verification Strategy & Step-by-Step Acceptance Checklist

| Step | Target File | Verification Action | Expected Result |
|------|-------------|---------------------|-----------------|
| 1 | `frontend/src/components/charts/types.ts` | Type definitions check | All chart data schemas compiled |
| 2 | `frontend/src/components/charts/useChartDimensions.ts` | Resize observer logic | Responsive bounding dimensions calculated |
| 3 | `frontend/src/components/charts/InteractiveAreaChart.tsx` | Bézier spline curve math | Catmull-Rom cubic path generated with gradient fill |
| 4 | `frontend/src/components/charts/InteractiveBarChart.tsx` | Grouped/stacked bar geometry | Correct X/Y coordinates and top rounded corners |
| 5 | `frontend/src/components/charts/InteractiveDonutChart.tsx` | Arc trigonometry | Slices sweep $360^\circ$ with center metric display |
| 6 | `frontend/src/components/charts/InteractiveGaugeChart.tsx` | 180° radial gauge | Emerald/amber/rose zones with indicator pip |
| 7 | `frontend/src/components/charts/index.ts` | Barrel export | Clean export of all components and types |
| 8 | Whole Frontend | `npm --prefix frontend run typecheck` | 0 TypeScript errors |
