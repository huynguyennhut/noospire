import * as React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { Card } from './card';
import { cn } from '@/lib/utils';

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: {
    value: string;
    positive?: boolean;
  };
  accent?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'slate';
  glow?: 'cyan' | 'rose' | 'amber' | 'emerald' | 'none';
}

export const StatCard = React.forwardRef<HTMLDivElement, StatCardProps>(
  ({ title, value, subtitle, icon, trend, accent = 'cyan', glow = 'none', className, ...props }, ref) => {
    const accentColors = {
      cyan: 'text-white',
      emerald: 'text-emerald-400',
      amber: 'text-amber-400',
      rose: 'text-rose-400',
      slate: 'text-nf-300',
    };

    const iconBgColors = {
      cyan: 'bg-white/[0.06] text-white border-white/10',
      emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
      slate: 'bg-white/[0.03] text-nf-400 border-white/[0.06]',
    };

    return (
      <Card ref={ref} glow={glow} className={cn('p-4 md:p-5 flex flex-col justify-between', className)} {...props}>
        <div className="flex items-center justify-between text-nf-400 text-xs">
          <span className="font-medium truncate tracking-wide text-nf-400">{title}</span>
          {icon && (
            <div className={cn('p-2 rounded-xl border shrink-0 backdrop-blur-md', iconBgColors[accent])}>
              {icon}
            </div>
          )}
        </div>
        <div className={cn('mt-3 text-2xl md:text-3xl font-extrabold tracking-tight font-mono', accentColors[accent])}>
          {value}
        </div>
        {(subtitle || trend) && (
          <div className="mt-2 pt-2 border-t border-white/[0.05] flex items-center justify-between text-[11px] text-nf-400">
            {subtitle && <span className="truncate">{subtitle}</span>}
            {trend && (
              <span
                className={cn(
                  'font-semibold ml-auto shrink-0 inline-flex items-center gap-0.5',
                  trend.positive ? 'text-emerald-400' : 'text-rose-400'
                )}
              >
                {trend.positive ? (
                  <ArrowUpRight className="w-3.5 h-3.5" />
                ) : (
                  <ArrowDownRight className="w-3.5 h-3.5" />
                )}
                {trend.value}
              </span>
            )}
          </div>
        )}
      </Card>
    );
  }
);
StatCard.displayName = 'StatCard';
