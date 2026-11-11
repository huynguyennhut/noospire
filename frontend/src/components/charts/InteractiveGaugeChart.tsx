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
          <circle cx={pipX} cy={pipY} r="4.5" fill="#09090B" stroke={activeZone.color} strokeWidth="2.5" />

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
