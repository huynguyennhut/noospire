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

  const safeData = useMemo(() => (Array.isArray(data) ? data : []), [data]);

  const total = useMemo(() => {
    return safeData.reduce((acc, item) => acc + (item.value || 0), 0);
  }, [safeData]);

  const cx = width / 2;
  const cy = height / 2;
  const outerR = Math.min(cx, cy) - 16;
  const innerR = outerR * innerRadiusRatio;

  // Arc path generator
  const slices = useMemo(() => {
    if (total === 0) return [];
    let currentAngle = -Math.PI / 2;

    return safeData.map((item, idx) => {
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
  }, [safeData, total, cx, cy, outerR, innerR, padAngle]);

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
          {safeData.map((item, idx) => {
            const isHovered = hoveredIdx === idx;
            const pct = total > 0 ? Math.round((item.value / total) * 100) : 0;

            return (
              <button
                key={item.id}
                type="button"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
                className={`flex items-center gap-2 px-2 py-1 rounded-lg transition-all cursor-pointer ${
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
