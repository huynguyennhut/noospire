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

  const safeData = useMemo(() => (Array.isArray(data) ? data : []), [data]);
  const safeSeries = useMemo(() => (Array.isArray(series) ? series : []), [series]);

  // Compute maximum Y across all series
  const maxY = useMemo(() => {
    let max = 0;
    safeData.forEach((d) => {
      safeSeries.forEach((s) => {
        const val = Number(d[s.dataKey]) || 0;
        if (val > max) max = val;
      });
    });
    return max === 0 ? 10 : Math.ceil(max * 1.15);
  }, [safeData, safeSeries]);

  // Points for each series
  const seriesPoints = useMemo(() => {
    if (!safeData.length) return [];
    const n = safeData.length;

    return safeSeries.map((s) => {
      const points = safeData.map((d, i) => {
        const x = n === 1 ? margin.left + plotWidth / 2 : margin.left + (i / (n - 1)) * plotWidth;
        const val = Number(d[s.dataKey]) || 0;
        const y = margin.top + plotHeight - (val / maxY) * plotHeight;
        return { x, y, val };
      });
      return { ...s, points };
    });
  }, [safeData, safeSeries, maxY, plotWidth, plotHeight, margin.left, margin.top]);

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
            {safeData.map((d, i) => {
              const n = safeData.length;
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
            title={safeData[hoveredIndex]?.[xKey]}
            payload={safeSeries.map((s) => ({
              name: s.name,
              value: valueFormatter(Number(safeData[hoveredIndex]?.[s.dataKey]) || 0),
              color: s.color,
            }))}
          />
        )}
      </div>

      {/* Synchronized Legend */}
      <div className="flex flex-wrap items-center justify-center gap-5 mt-2 text-xs">
        {safeSeries.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="font-medium text-slate-400">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
