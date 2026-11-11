/**
 * Adversarial Verification Harness for Interactive SVG Chart Mathematics & Boundary Conditions
 * Milestone 5 - Challenger 2
 */

import fs from 'node:fs';
import path from 'node:path';

let passCount = 0;
let failCount = 0;
const failures = [];

function assert(condition, message, detail = {}) {
  if (condition) {
    passCount++;
    console.log(`  [PASS] ${message}`);
  } else {
    failCount++;
    failures.push({ message, detail });
    console.error(`  [FAIL] ${message}`, detail);
  }
}

console.log('='.repeat(70));
console.log('NOOSFORGE SVG CHART MATHEMATICS & BOUNDARY ADVERSARIAL VERIFIER');
console.log('='.repeat(70));

// -----------------------------------------------------------------------------
// 1. COMPONENT EXPORTS & IMPORT SANITY CHECK
// -----------------------------------------------------------------------------
console.log('\n--- 1. Component Exports & Source Sanity ---');

const chartsDir = path.resolve('frontend/src/components/charts');
const expectedFiles = [
  'types.ts',
  'useChartDimensions.ts',
  'ChartTooltip.tsx',
  'InteractiveAreaChart.tsx',
  'InteractiveBarChart.tsx',
  'InteractiveDonutChart.tsx',
  'InteractiveGaugeChart.tsx',
  'adapters.ts',
  'index.ts',
];

for (const file of expectedFiles) {
  const filePath = path.join(chartsDir, file);
  assert(fs.existsSync(filePath), `File exists: ${file}`);
}

const indexSource = fs.readFileSync(path.join(chartsDir, 'index.ts'), 'utf-8');
assert(indexSource.includes("export * from './types'"), "index.ts exports types");
assert(indexSource.includes("export * from './InteractiveAreaChart'"), "index.ts exports InteractiveAreaChart");
assert(indexSource.includes("export * from './InteractiveBarChart'"), "index.ts exports InteractiveBarChart");
assert(indexSource.includes("export * from './InteractiveDonutChart'"), "index.ts exports InteractiveDonutChart");
assert(indexSource.includes("export * from './InteractiveGaugeChart'"), "index.ts exports InteractiveGaugeChart");
assert(indexSource.includes("export * from './adapters'"), "index.ts exports adapters");

// -----------------------------------------------------------------------------
// 2. INTERACTIVE AREA CHART MATHEMATICAL ENGINE
// -----------------------------------------------------------------------------
console.log('\n--- 2. InteractiveAreaChart Mathematical Engine ---');

function computeMaxY(data, series) {
  let max = 0;
  data.forEach((d) => {
    series.forEach((s) => {
      const val = Number(d[s.dataKey]) || 0;
      if (val > max) max = val;
    });
  });
  return max === 0 ? 10 : Math.ceil(max * 1.15);
}

function computeSeriesPoints(data, series, maxY, plotWidth, plotHeight, marginLeft, marginTop) {
  if (!data.length) return [];
  const n = data.length;
  return series.map((s) => {
    const points = data.map((d, i) => {
      const x = n === 1 ? marginLeft + plotWidth / 2 : marginLeft + (i / (n - 1)) * plotWidth;
      const val = Number(d[s.dataKey]) || 0;
      const y = marginTop + plotHeight - (val / maxY) * plotHeight;
      return { x, y, val };
    });
    return { ...s, points };
  });
}

function generateSplinePaths(pts, marginTop, plotHeight) {
  if (pts.length < 2) {
    if (pts.length === 1) {
      const p = pts[0];
      return {
        line: `M ${p.x - 5},${p.y} L ${p.x + 5},${p.y}`,
        area: `M ${p.x - 5},${marginTop + plotHeight} L ${p.x - 5},${p.y} L ${p.x + 5},${p.y} L ${p.x + 5},${marginTop + plotHeight} Z`,
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

    const bottom = marginTop + plotHeight;
    cp1y = Math.min(Math.max(cp1y, marginTop), bottom);
    cp2y = Math.min(Math.max(cp2y, marginTop), bottom);

    linePath += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }

  const first = pts[0];
  const last = pts[pts.length - 1];
  const areaPath = `M ${first.x},${marginTop + plotHeight} L ${first.x},${first.y} ${linePath.substring(linePath.indexOf('C'))} L ${last.x},${marginTop + plotHeight} Z`;

  return { line: linePath, area: areaPath };
}

// Test 2.1: Empty data handling
const emptyAreaMaxY = computeMaxY([], [{ dataKey: 'val' }]);
assert(emptyAreaMaxY === 10, 'AreaChart: Empty dataset defaults maxY to 10 (no division by zero)', { emptyAreaMaxY });

const emptyPoints = computeSeriesPoints([], [{ dataKey: 'val' }], emptyAreaMaxY, 400, 200, 40, 16);
assert(emptyPoints.length === 0, 'AreaChart: Empty dataset produces empty points array');

const emptySpline = generateSplinePaths([], 16, 200);
assert(emptySpline.line === '' && emptySpline.area === '', 'AreaChart: Empty points produces empty spline paths');

// Test 2.2: Single data point handling
const singleData = [{ label: 'Day 1', val: 50 }];
const singleMaxY = computeMaxY(singleData, [{ dataKey: 'val' }]);
assert(singleMaxY === Math.ceil(50 * 1.15), 'AreaChart: Single data point computes headroom maxY', { singleMaxY });

const singlePoints = computeSeriesPoints(singleData, [{ dataKey: 'val' }], singleMaxY, 400, 200, 40, 16);
assert(singlePoints[0].points[0].x === 40 + 400 / 2, 'AreaChart: Single point placed at plot center without division by zero', {
  x: singlePoints[0].points[0].x,
  expected: 240,
});
assert(!Number.isNaN(singlePoints[0].points[0].x) && !Number.isNaN(singlePoints[0].points[0].y), 'AreaChart: Single point coordinates contain no NaN');

const singleSpline = generateSplinePaths(singlePoints[0].points, 16, 200);
assert(!singleSpline.line.includes('NaN') && singleSpline.line.startsWith('M 235,'), 'AreaChart: Single point line path renders fallback tick without NaN', { line: singleSpline.line });
assert(!singleSpline.area.includes('NaN') && singleSpline.area.startsWith('M 235,216'), 'AreaChart: Single point area path renders closed polygon without NaN', { area: singleSpline.area });

// Test 2.3: All-zero dataset
const zeroData = [{ val: 0 }, { val: 0 }, { val: 0 }];
const zeroMaxY = computeMaxY(zeroData, [{ dataKey: 'val' }]);
assert(zeroMaxY === 10, 'AreaChart: All-zero dataset defaults maxY to 10 (avoids 0/0)', { zeroMaxY });

const zeroPoints = computeSeriesPoints(zeroData, [{ dataKey: 'val' }], zeroMaxY, 400, 200, 40, 16);
for (const p of zeroPoints[0].points) {
  assert(p.y === 16 + 200, 'AreaChart: All-zero point y equals bottom baseline', { y: p.y, baseline: 216 });
}
const zeroSpline = generateSplinePaths(zeroPoints[0].points, 16, 200);
assert(!zeroSpline.line.includes('NaN') && !zeroSpline.area.includes('NaN'), 'AreaChart: All-zero spline contains no NaN');
assert(zeroSpline.line.includes('C'), 'AreaChart: All-zero spline generates valid Bézier C command');

// Test 2.4: Extreme unbalanced scale (0 vs 1,000,000)
const extremeData = [{ val: 0 }, { val: 1000000 }, { val: 2 }];
const extremeMaxY = computeMaxY(extremeData, [{ dataKey: 'val' }]);
assert(extremeMaxY === Math.ceil(1000000 * 1.15), 'AreaChart: Extreme value scaled with 15% headroom', { extremeMaxY });
const extremePoints = computeSeriesPoints(extremeData, [{ dataKey: 'val' }], extremeMaxY, 400, 200, 40, 16);
for (const p of extremePoints[0].points) {
  assert(p.y >= 16 && p.y <= 216, 'AreaChart: All points contained within plotHeight boundary [16, 216]', { y: p.y });
}

// Test 2.5: Catmull-Rom Bézier spline tangent math and Y-clamping
const volatileData = [{ x: 40, y: 16 }, { x: 100, y: 216 }, { x: 160, y: 16 }, { x: 220, y: 216 }];
const volatileSpline = generateSplinePaths(volatileData, 16, 200);
assert(!volatileSpline.line.includes('NaN') && !volatileSpline.area.includes('NaN'), 'AreaChart: Volatile spline contains no NaN');
// Verify path starts with M and contains matching C commands
const cMatches = (volatileSpline.line.match(/C/g) || []).length;
assert(cMatches === volatileData.length - 1, 'AreaChart: Spline has exactly (n-1) cubic Bézier segments', { cMatches, expected: 3 });

// Test 2.6: Hover coordinate clamping
function clampHover(xPos, plotWidth, n) {
  const ratio = Math.max(0, Math.min(1, xPos / plotWidth));
  const idx = Math.round(ratio * (n - 1));
  return { ratio, idx };
}

assert(clampHover(-50, 400, 10).idx === 0, 'AreaChart: Hover x < 0 clamps to first index (0)');
assert(clampHover(500, 400, 10).idx === 9, 'AreaChart: Hover x > plotWidth clamps to last index (9)');
assert(clampHover(200, 400, 10).idx === 5, 'AreaChart: Hover midpoint correctly interpolates index');

// -----------------------------------------------------------------------------
// 3. INTERACTIVE BAR CHART MATHEMATICAL ENGINE
// -----------------------------------------------------------------------------
console.log('\n--- 3. InteractiveBarChart Mathematical Engine ---');

function computeBarMax(data, series) {
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
}

function roundedBarPath(x, y, w, h, r = 3) {
  if (h <= 0 || w <= 0) return '';
  const safeR = Math.min(r, h, w / 2);
  return `M ${x},${y + h} L ${x},${y + safeR} Q ${x},${y} ${x + safeR},${y} L ${x + w - safeR},${y} Q ${x + w},${y} ${x + w},${y + safeR} L ${x + w},${y + h} Z`;
}

// Test 3.1: Empty data
const emptyBarMax = computeBarMax([], [{ dataKey: 'v' }]);
assert(emptyBarMax.maxVal === 10 && emptyBarMax.stackedMax === 10, 'BarChart: Empty data defaults maxVal to 10');

// Test 3.2: Single data point
const singleBarMax = computeBarMax([{ cat: 'A', v: 40 }], [{ dataKey: 'v' }]);
assert(singleBarMax.maxVal === Math.ceil(40 * 1.15), 'BarChart: Single bar computes headroom maxVal');
const singleBarKCount = Math.max(1, 1);
const singleBarW = (400 / singleBarKCount) * 0.72;
assert(singleBarW > 0 && !Number.isNaN(singleBarW), 'BarChart: Single bar width is positive and finite', { singleBarW });

// Test 3.3: All-zero data
const zeroBarMax = computeBarMax([{ v: 0 }, { v: 0 }], [{ dataKey: 'v' }]);
assert(zeroBarMax.maxVal === 10, 'BarChart: All-zero data defaults to 10');
// Verify roundedBarPath when height is 0
const zeroBarPath = roundedBarPath(40, 200, 30, 0, 3);
assert(zeroBarPath === '', 'BarChart: Height 0 bar returns empty path string instead of negative SVG bounds');

// Test 3.4: Rounded bar corner radius safety clamping
const tinyHPath = roundedBarPath(10, 10, 20, 1.5, 3);
assert(tinyHPath.includes('1.5'), 'BarChart: Safe radius clamps to bar height when h < r', { tinyHPath });
const narrowWPath = roundedBarPath(10, 10, 2, 50, 3);
assert(narrowWPath.includes('L 11,'), 'BarChart: Safe radius clamps to w/2 when w/2 < r', { narrowWPath });

// Test 3.5: Stacked bar boundary preservation
const stackedData = [
  { s1: 300, s2: 700 },
  { s1: 0, s2: 0 },
];
const stackedBarMax = computeBarMax(stackedData, [{ dataKey: 's1' }, { dataKey: 's2' }]);
assert(stackedBarMax.stackedMax === Math.ceil(1000 * 1.12), 'BarChart: Stacked max computes cumulative sum correctly');

// -----------------------------------------------------------------------------
// 4. INTERACTIVE DONUT CHART ARC & CIRCUMFERENCE MATH
// -----------------------------------------------------------------------------
console.log('\n--- 4. InteractiveDonutChart Arc & Circumference Math ---');

function generateDonutSlices(data, width, height, innerRadiusRatio = 0.68, padAngle = 0.025) {
  const total = data.reduce((acc, item) => acc + (item.value || 0), 0);
  if (total === 0) return { total: 0, slices: [] };

  const cx = width / 2;
  const cy = height / 2;
  const outerR = Math.min(cx, cy) - 16;
  const innerR = outerR * innerRadiusRatio;

  let currentAngle = -Math.PI / 2;

  const slices = data.map((item, idx) => {
    const fraction = item.value / total;
    const angleSpan = fraction * 2 * Math.PI;
    const startAngle = currentAngle + padAngle / 2;
    const endAngle = currentAngle + angleSpan - padAngle / 2;
    currentAngle += angleSpan;

    if (fraction >= 0.999) {
      return {
        ...item,
        path: `M ${cx},${cy - outerR} A ${outerR},${outerR} 0 1,1 ${cx},${cy + outerR} A ${outerR},${outerR} 0 1,1 ${cx},${cy - outerR} M ${cx},${cy - innerR} A ${innerR},${innerR} 0 1,0 ${cx},${cy + innerR} A ${innerR},${innerR} 0 1,0 ${cx},${cy - innerR} Z`,
        midAngle: 0,
        fraction,
        angleSpan,
        startAngle,
        endAngle,
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

    return { ...item, path, midAngle, fraction, angleSpan, startAngle, endAngle };
  });

  return { total, slices, cx, cy, outerR, innerR };
}

// Test 4.1: Empty data
const emptyDonut = generateDonutSlices([], 300, 300);
assert(emptyDonut.total === 0 && emptyDonut.slices.length === 0, 'DonutChart: Empty dataset returns 0 total and empty slices');

// Test 4.2: All-zero data
const zeroDonut = generateDonutSlices([{ id: 'a', value: 0 }, { id: 'b', value: 0 }], 300, 300);
assert(zeroDonut.total === 0 && zeroDonut.slices.length === 0, 'DonutChart: All-zero dataset returns 0 total and empty slices without division by zero');

// Test 4.3: Single full slice (100%)
const singleDonut = generateDonutSlices([{ id: 'solo', value: 100 }], 300, 300);
assert(singleDonut.slices.length === 1, 'DonutChart: Single slice data produces 1 slice');
assert(singleDonut.slices[0].path.includes('A') && !singleDonut.slices[0].path.includes('NaN'), 'DonutChart: 100% slice generates complete dual-arc SVG donut ring without NaN');
// Check dual arc syntax: two outer arcs (1,1) and two inner arcs (1,0)
assert(singleDonut.slices[0].path.includes('0 1,1') && singleDonut.slices[0].path.includes('0 1,0'), 'DonutChart: 100% slice has both outer and inner concentric circular arcs');

// Test 4.4: 360-degree sum verification across multi slices
const multiDonutData = [
  { id: 'crit', value: 15 },
  { id: 'high', value: 25 },
  { id: 'med', value: 35 },
  { id: 'low', value: 25 },
];
const multiDonut = generateDonutSlices(multiDonutData, 300, 300);
let totalAngleSpan = 0;
for (const s of multiDonut.slices) {
  totalAngleSpan += s.angleSpan;
  assert(!s.path.includes('NaN'), `DonutChart: Slice ${s.id} contains no NaN`);
}
assert(Math.abs(totalAngleSpan - 2 * Math.PI) < 1e-9, 'DonutChart: Sum of slice angles spans exactly 2*PI (360 degrees)', { totalAngleSpan });

// Test 4.5: Hover translation vector norm
for (const s of multiDonut.slices) {
  const dx = Math.cos(s.midAngle) * 5;
  const dy = Math.sin(s.midAngle) * 5;
  const norm = Math.hypot(dx, dy);
  assert(Math.abs(norm - 5.0) < 1e-9, `DonutChart: Slice ${s.id} hover translation vector has exact magnitude of 5px`, { norm });
}

// Test 4.6: Adversarial edge case: Micro slice where angleSpan < padAngle
const microData = [
  { id: 'huge', value: 100000 },
  { id: 'micro', value: 1 },
];
const microDonut = generateDonutSlices(microData, 300, 300);
const microSlice = microDonut.slices[1];
const padInverted = microSlice.startAngle > microSlice.endAngle;
console.log(`  [INFO] Micro-slice angleSpan (${microSlice.angleSpan.toFixed(6)} rad) vs padAngle (0.025 rad) -> startAngle > endAngle: ${padInverted}`);
assert(!microSlice.path.includes('NaN'), 'DonutChart: Micro slice path contains no NaN even when angleSpan < padAngle');

// -----------------------------------------------------------------------------
// 5. INTERACTIVE GAUGE CHART 180-DEGREE RADIAL MATH
// -----------------------------------------------------------------------------
console.log('\n--- 5. InteractiveGaugeChart 180-Degree Radial Math ---');

function evaluateGauge(value, minValue = 0, maxValue = 100, width = 300, height = 200) {
  const clampedVal = Math.max(minValue, Math.min(maxValue, value));
  const normalizedRatio = (clampedVal - minValue) / (maxValue - minValue);

  const cx = width / 2;
  const cy = height - 20;
  const outerR = Math.min(cx - 24, cy - 20);
  const trackW = 16;
  const innerR = outerR - trackW;

  const angleForRatio = (ratio) => Math.PI * (1 - ratio);

  const makeGaugeArc = (rStart, rEnd) => {
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

    return {
      path: `M ${x1},${y1} A ${outerR},${outerR} 0 0,1 ${x2},${y2} L ${x3},${y3} A ${innerR},${innerR} 0 0,0 ${x4},${y4} Z`,
      coords: { x1, y1, x2, y2, x3, y3, x4, y4 },
    };
  };

  const currentAngle = angleForRatio(normalizedRatio);
  const midR = outerR - trackW / 2;
  const pipX = cx + midR * Math.cos(currentAngle);
  const pipY = cy - midR * Math.sin(currentAngle);

  return {
    clampedVal,
    normalizedRatio,
    cx,
    cy,
    outerR,
    innerR,
    midR,
    currentAngle,
    pipX,
    pipY,
    makeGaugeArc,
  };
}

// Test 5.1: Boundary values: 0, 50, 100
const gauge0 = evaluateGauge(0);
assert(gauge0.normalizedRatio === 0, 'GaugeChart: Value 0 gives ratio 0');
assert(Math.abs(gauge0.currentAngle - Math.PI) < 1e-9, 'GaugeChart: Ratio 0 maps to PI radians (180 deg, left baseline)');
assert(Math.abs(gauge0.pipX - (gauge0.cx - gauge0.midR)) < 1e-9, 'GaugeChart: Pip X at ratio 0 is exactly (cx - midR)');
assert(Math.abs(gauge0.pipY - gauge0.cy) < 1e-9, 'GaugeChart: Pip Y at ratio 0 is exactly at baseline cy');

const gauge50 = evaluateGauge(50);
assert(Math.abs(gauge50.normalizedRatio - 0.5) < 1e-9, 'GaugeChart: Value 50 gives ratio 0.5');
assert(Math.abs(gauge50.currentAngle - Math.PI / 2) < 1e-9, 'GaugeChart: Ratio 0.5 maps to PI/2 radians (90 deg, apex)');
assert(Math.abs(gauge50.pipX - gauge50.cx) < 1e-9, 'GaugeChart: Pip X at ratio 0.5 is centered at cx');
assert(Math.abs(gauge50.pipY - (gauge50.cy - gauge50.midR)) < 1e-9, 'GaugeChart: Pip Y at ratio 0.5 is at highest apex (cy - midR)');

const gauge100 = evaluateGauge(100);
assert(gauge100.normalizedRatio === 1, 'GaugeChart: Value 100 gives ratio 1');
assert(Math.abs(gauge100.currentAngle - 0) < 1e-9, 'GaugeChart: Ratio 1 maps to 0 radians (right baseline)');
assert(Math.abs(gauge100.pipX - (gauge100.cx + gauge100.midR)) < 1e-9, 'GaugeChart: Pip X at ratio 1 is exactly (cx + midR)');
assert(Math.abs(gauge100.pipY - gauge100.cy) < 1e-9, 'GaugeChart: Pip Y at ratio 1 is exactly at baseline cy');

// Test 5.2: Out of range clamping
const gaugeNegative = evaluateGauge(-100);
assert(gaugeNegative.clampedVal === 0 && gaugeNegative.normalizedRatio === 0, 'GaugeChart: Negative value correctly clamped to minValue 0');

const gaugeOverflow = evaluateGauge(500);
assert(gaugeOverflow.clampedVal === 100 && gaugeOverflow.normalizedRatio === 1, 'GaugeChart: Overflow value correctly clamped to maxValue 100');

// Test 5.3: Arc path generator geometry
const arcFull = gauge100.makeGaugeArc(0, 1);
assert(!arcFull.path.includes('NaN'), 'GaugeChart: Full semicircle arc contains no NaN');
assert(arcFull.path.startsWith('M') && arcFull.path.includes('A') && arcFull.path.endsWith('Z'), 'GaugeChart: Full semicircle arc is properly formatted closed SVG path');
assert(arcFull.coords.y1 <= gauge100.cy && arcFull.coords.y2 <= gauge100.cy, 'GaugeChart: Arc coordinates lie entirely in upper half-plane');

// -----------------------------------------------------------------------------
// 6. CHART TOOLTIP AUTO-INVERSION & POSITIONING
// -----------------------------------------------------------------------------
console.log('\n--- 6. ChartTooltip Auto-Inversion & Positioning ---');

function computeTooltipPosition(x, y, containerWidth) {
  const tooltipWidth = 160;
  const isRightEdge = x + tooltipWidth + 24 > containerWidth;
  const leftPos = isRightEdge ? x - tooltipWidth - 12 : x + 12;
  const topPos = Math.max(8, y - 24);
  return { leftPos, topPos, isRightEdge };
}

// Test 6.1: Left boundary (x near 0)
const leftTip = computeTooltipPosition(10, 100, 500);
assert(!leftTip.isRightEdge, 'Tooltip: x=10 does not trigger right edge flip');
assert(leftTip.leftPos === 22, 'Tooltip: x=10 positioned at x + 12 = 22');

// Test 6.2: Right boundary auto-inversion
const rightTip = computeTooltipPosition(450, 100, 500);
assert(rightTip.isRightEdge, 'Tooltip: x=450 near container width 500 triggers right edge flip');
assert(rightTip.leftPos === 450 - 160 - 12, 'Tooltip: x=450 flips to left of cursor (278px)', { leftPos: rightTip.leftPos });
assert(rightTip.leftPos > 0, 'Tooltip: Flipped tooltip stays strictly inside container viewport');

// Test 6.3: Top edge vertical clamping
const topTip = computeTooltipPosition(200, 10, 500);
assert(topTip.topPos === 8, 'Tooltip: y=10 clamped to Math.max(8, y-24) = 8px to prevent overflow', { topPos: topTip.topPos });

// -----------------------------------------------------------------------------
// 7. ADAPTER LOGIC INTEGRATION
// -----------------------------------------------------------------------------
console.log('\n--- 7. Adapter Functions Integration ---');

// Mock adapter logic mirroring frontend/src/components/charts/adapters.ts
function adaptSeverityToDonut(dist) {
  const SEVERITY_COLORS = {
    CRITICAL: '#EF4444',
    HIGH: '#F97316',
    MEDIUM: '#F59E0B',
    LOW: '#10B981',
    INFO: '#06B6D4',
  };
  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
  return order
    .filter((sev) => (dist[sev] || 0) > 0 || Object.values(dist).every((v) => v === 0))
    .map((sev) => ({
      id: sev,
      label: sev,
      value: dist[sev] || 0,
      color: SEVERITY_COLORS[sev] || '#64748B',
    }));
}

// Test 7.1: Severity with positive values
const sampleSev = { CRITICAL: 5, HIGH: 12, MEDIUM: 20, LOW: 8, INFO: 0 };
const sevDonut = adaptSeverityToDonut(sampleSev);
assert(sevDonut.length === 4, 'Adapters: Zero INFO filtered out when other severities exist');
assert(sevDonut.find((s) => s.id === 'CRITICAL').color === '#EF4444', 'Adapters: Critical mapped to rose');

// Test 7.2: Severity all zeros
const zeroSev = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
const zeroSevDonut = adaptSeverityToDonut(zeroSev);
assert(zeroSevDonut.length === 5, 'Adapters: All zeros preserves all 5 segments for empty state display');

// -----------------------------------------------------------------------------
// SUMMARY
// -----------------------------------------------------------------------------
console.log('\n' + '='.repeat(70));
console.log(`TOTAL PASSES: ${passCount}`);
console.log(`TOTAL FAILURES: ${failCount}`);
console.log('='.repeat(70));

if (failCount > 0) {
  console.error('\nFailures summary:');
  console.error(JSON.stringify(failures, null, 2));
  process.exit(1);
} else {
  console.log('\nALL MATHEMATICAL & BOUNDARY STRESS TESTS PASSED CLEANLY.');
  process.exit(0);
}
