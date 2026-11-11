import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ReactNode;
  error?: boolean | string;
  onClear?: () => void;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', icon, error, onClear, value, disabled, ...props }, ref) => {
    const hasClear = onClear && value !== undefined && String(value).length > 0;

    return (
      <div className="relative w-full">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-nf-500 pointer-events-none">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          type={type}
          value={value}
          disabled={disabled}
          className={cn(
            'w-full rounded-xl bg-nf-950/80 border border-white/[0.08] text-white placeholder-nf-500 px-3 py-1.5 text-xs transition-colors duration-150 backdrop-blur-md',
            'focus:outline-none focus:border-white/30 focus:ring-1 focus:ring-white/20',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            icon && 'pl-9',
            hasClear && 'pr-8',
            error && 'border-rose-500/60 focus:border-rose-500 focus:ring-rose-500/30 text-rose-200',
            className
          )}
          {...props}
        />
        {hasClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-nf-500 hover:text-white p-0.5 rounded transition"
            aria-label="Clear input"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
        {typeof error === 'string' && (
          <p className="mt-1 text-[11px] text-rose-400 font-medium">{error}</p>
        )}
      </div>
    );
  }
);
Input.displayName = 'Input';
