import * as React from 'react';
import { cn } from '@/lib/utils';

export type BadgeSeverity =
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'info'
  | 'neutral'
  | 'status'
  | string;

export type BadgeSize = 'sm' | 'md';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  severity?: BadgeSeverity;
  size?: BadgeSize;
  dot?: boolean;
  glow?: boolean;
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  (
    {
      className,
      severity = 'neutral',
      size = 'sm',
      dot = false,
      glow = false,
      children,
      ...props
    },
    ref
  ) => {
    const normalized = severity.toLowerCase();

    const severityStyles: Record<
      string,
      { bg: string; text: string; border: string; glow: string; dot: string }
    > = {
      critical: {
        bg: 'bg-rose-500/10',
        text: 'text-rose-400',
        border: 'border-rose-500/30',
        glow: 'shadow-[0_0_12px_rgba(244,63,94,0.2)]',
        dot: 'bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.6)]',
      },
      high: {
        bg: 'bg-orange-500/10',
        text: 'text-orange-400',
        border: 'border-orange-500/30',
        glow: 'shadow-[0_0_12px_rgba(249,115,22,0.2)]',
        dot: 'bg-orange-400 shadow-[0_0_6px_rgba(249,115,22,0.6)]',
      },
      medium: {
        bg: 'bg-amber-500/10',
        text: 'text-amber-400',
        border: 'border-amber-500/30',
        glow: 'shadow-[0_0_12px_rgba(245,158,11,0.2)]',
        dot: 'bg-amber-400 shadow-[0_0_6px_rgba(245,158,11,0.6)]',
      },
      low: {
        bg: 'bg-emerald-500/10',
        text: 'text-emerald-400',
        border: 'border-emerald-500/30',
        glow: 'shadow-[0_0_12px_rgba(16,185,129,0.2)]',
        dot: 'bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.6)]',
      },
      info: {
        bg: 'bg-sky-500/10',
        text: 'text-sky-300',
        border: 'border-sky-500/30',
        glow: 'shadow-[0_0_12px_rgba(14,165,233,0.15)]',
        dot: 'bg-sky-400 shadow-[0_0_6px_rgba(14,165,233,0.6)]',
      },
      status: {
        bg: 'bg-white/[0.08]',
        text: 'text-white',
        border: 'border-white/15',
        glow: 'shadow-[0_0_12px_rgba(255,255,255,0.1)]',
        dot: 'bg-white shadow-[0_0_6px_rgba(255,255,255,0.6)]',
      },
      neutral: {
        bg: 'bg-white/[0.04]',
        text: 'text-nf-300',
        border: 'border-white/[0.08]',
        glow: '',
        dot: 'bg-nf-400',
      },
    };

    const style = severityStyles[normalized] || severityStyles.neutral;

    const sizeClasses: Record<BadgeSize, string> = {
      sm: 'px-2 py-0.5 text-[10px] gap-1.5',
      md: 'px-2.5 py-1 text-xs gap-2',
    };

    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center font-bold uppercase tracking-wider rounded-md border backdrop-blur-md transition-colors',
          style.bg,
          style.text,
          style.border,
          glow && style.glow,
          sizeClasses[size],
          className
        )}
        {...props}
      >
        {dot && (
          <span className={cn('w-1.5 h-1.5 rounded-full shrink-0 animate-pulse', style.dot)} />
        )}
        {children}
      </span>
    );
  }
);
Badge.displayName = 'Badge';
