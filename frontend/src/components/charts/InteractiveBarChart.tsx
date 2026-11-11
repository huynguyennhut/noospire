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

  const safeData = useMemo(() => (Array.isArray(data) ? data : []), [data]);
  const safeSeries = useMemo(() => (Array.isArray(series) ? series : []), [series]);

  // Compute maximum values
  const { maxVal, stackedMax } = useMemo(() => {
    let mSingle = 0;
    let mStacked = 0;
    safeData.forEach((d) => {
      let sum = 0;
      safeSeries.forEach((s) => {
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
  }, [safeData, safeSeries]);

  const yMax = mode === 'stacked' ? stackedMax : maxVal;
  const kCount = Math.max(1, safeData.length);

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
          {safeData.map((d, kIdx) => {
            const isHovered = hoveredCategory === kIdx;

            if (orientation === 'vertical') {
              const stepX = plotWidth / kCount;
              const slotW = stepX * 0.72;
              const catX = margin.left + kIdx * stepX + (stepX - slotW) / 2;

              if (mode === 'grouped') {
                const barW = slotW / Math.max(1, safeSeries.length);

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

                    {safeSeries.map((s, sIdx) => {
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
                    {safeSeries.map((s) => {
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
              const val = Number(d[safeSeries[0]?.dataKey]) || 0;
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
                    fill={safeSeries[0]?.color || '#06B6D4'}
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
            title={safeData[hoveredCategory]?.[categoryKey]}
            payload={safeSeries.map((s) => ({
              name: s.name,
              value: valueFormatter(Number(safeData[hoveredCategory]?.[s.dataKey]) || 0),
              color: s.color,
            }))}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center justify-center gap-5 mt-2 text-xs">
        {safeSeries.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5 text-slate-300">
            <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: s.color }} />
            <span className="font-medium text-slate-400">{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
