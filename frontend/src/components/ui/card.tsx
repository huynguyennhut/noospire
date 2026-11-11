import * as React from 'react';
import { cn } from '@/lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hoverElevate?: boolean;
  glow?: 'cyan' | 'rose' | 'amber' | 'emerald' | 'none';
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, hoverElevate = true, glow = 'none', children, ...props }, ref) => {
    const glowClasses = {
      none: '',
      cyan: 'shadow-[0_0_24px_rgba(255,255,255,0.08)] border-white/20',
      rose: 'shadow-[0_0_24px_rgba(244,63,94,0.18)] border-rose-500/30',
      amber: 'shadow-[0_0_24px_rgba(245,158,11,0.18)] border-amber-500/30',
      emerald: 'shadow-[0_0_24px_rgba(16,185,129,0.18)] border-emerald-500/30',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'relative rounded-2xl border border-white/[0.07] bg-gradient-to-b from-white/[0.035] to-white/[0.005] bg-nf-900/60 backdrop-blur-xl text-nf-100 shadow-[0_8px_32px_0_rgba(0,0,0,0.45)] transition-all duration-200 overflow-hidden',
          'before:absolute before:inset-x-0 before:top-0 before:h-[1px] before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent before:pointer-events-none',
          hoverElevate &&
            'hover:bg-nf-850/80 hover:border-white/15 hover:shadow-[0_12px_40px_0_rgba(0,0,0,0.6)] hover:-translate-y-0.5',
          glow !== 'none' && glowClasses[glow],
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Card.displayName = 'Card';

export const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1.5 p-5 md:p-6 pb-2', className)}
    {...props}
  />
));
CardHeader.displayName = 'CardHeader';

export const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      'text-base md:text-lg font-bold tracking-tight text-white flex items-center gap-2',
      className
    )}
    {...props}
  />
));
CardTitle.displayName = 'CardTitle';

export const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn('text-xs text-nf-400 font-normal leading-relaxed', className)}
    {...props}
  />
));
CardDescription.displayName = 'CardDescription';

export const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('p-5 md:p-6 pt-2', className)} {...props} />
));
CardContent.displayName = 'CardContent';

export const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'flex items-center justify-between p-5 md:p-6 pt-0 border-t border-white/[0.06] mt-auto text-xs text-nf-400',
      className
    )}
    {...props}
  />
));
CardFooter.displayName = 'CardFooter';
