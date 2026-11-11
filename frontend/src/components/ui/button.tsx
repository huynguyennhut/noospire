import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'destructive' | 'outline' | 'ghost' | 'glass';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'secondary',
      size = 'md',
      loading = false,
      icon,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const variantClasses: Record<ButtonVariant, string> = {
      primary:
        'bg-white text-nf-950 font-bold shadow-[0_2px_12px_rgba(255,255,255,0.15)] hover:bg-nf-100 hover:shadow-[0_4px_16px_rgba(255,255,255,0.25)] border border-white active:scale-[0.98]',
      secondary:
        'bg-white/[0.04] hover:bg-white/[0.08] text-nf-200 border border-white/[0.08] hover:border-white/20 active:bg-white/[0.1] backdrop-blur-md',
      destructive:
        'bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:border-rose-500/50 shadow-sm shadow-rose-950/40 active:scale-[0.98]',
      outline:
        'border border-white/15 bg-transparent hover:bg-white/[0.04] text-nf-200 active:bg-white/[0.08]',
      ghost:
        'bg-transparent hover:bg-white/[0.05] text-nf-400 hover:text-white',
      glass:
        'bg-nf-900/60 backdrop-blur-xl border border-white/[0.08] hover:border-white/20 text-nf-200 hover:text-white shadow-[0_4px_16px_rgba(0,0,0,0.3)] active:scale-[0.98]',
    };

    const sizeClasses: Record<ButtonSize, string> = {
      sm: 'px-2.5 py-1 text-xs rounded-lg gap-1.5',
      md: 'px-3.5 py-1.5 text-xs font-semibold rounded-xl gap-2',
      lg: 'px-5 py-2.5 text-sm font-bold rounded-xl gap-2.5',
      icon: 'p-2 rounded-xl h-8 w-8 justify-center',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          'inline-flex items-center justify-center font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white/20 disabled:opacity-50 disabled:pointer-events-none select-none cursor-pointer',
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        {...props}
      >
        {loading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-current shrink-0" />
        ) : (
          icon && <span className="shrink-0">{icon}</span>
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
