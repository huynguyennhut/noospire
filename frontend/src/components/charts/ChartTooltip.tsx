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
      <div className="bg-nf-900/95 backdrop-blur-xl border border-white/10 rounded-xl p-3 shadow-2xl min-w-[140px] text-xs">
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
