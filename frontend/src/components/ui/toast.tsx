'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';

export type ToastVariant = 'default' | 'success' | 'warning' | 'destructive' | 'info';

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
}

export interface ToastItem extends ToastOptions {
  id: string;
}

interface ToastContextType {
  toast: (options: ToastOptions) => void;
  dismiss: (id: string) => void;
  toasts: ToastItem[];
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast(): ToastContextType {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

function ToastElement({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const { id, title, description, variant = 'default', duration = 4500 } = toast;

  useEffect(() => {
    if (duration <= 0) return;
    const timer = setTimeout(() => {
      onDismiss(id);
    }, duration);
    return () => clearTimeout(timer);
  }, [id, duration, onDismiss]);

  const renderIcon = () => {
    switch (variant) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />;
      case 'destructive':
        return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
      case 'info':
      case 'default':
      default:
        return <Info className="w-4 h-4 text-white shrink-0" />;
    }
  };

  const getVariantStyles = () => {
    switch (variant) {
      case 'success':
        return 'border-emerald-500/30 shadow-[0_8px_32px_rgba(16,185,129,0.15)]';
      case 'warning':
        return 'border-amber-500/30 shadow-[0_8px_32px_rgba(245,158,11,0.15)]';
      case 'destructive':
        return 'border-rose-500/30 shadow-[0_8px_32px_rgba(244,63,94,0.15)]';
      case 'info':
      case 'default':
      default:
        return 'border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.6)]';
    }
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-auto relative w-full rounded-2xl backdrop-blur-2xl bg-nf-950/95 border ${getVariantStyles()} text-white p-3.5 transition-all duration-300 ease-out shadow-2xl animate-in fade-in slide-in-from-bottom-2 overflow-hidden`}
    >
      {/* Specular shine top border */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/25 to-transparent pointer-events-none" />

      <div className="flex items-start gap-3">
        <div className="mt-0.5 p-1 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center">
          {renderIcon()}
        </div>

        <div className="flex-1 min-w-0 pr-2">
          <div className="text-xs font-bold tracking-tight text-white leading-snug break-words">
            {title}
          </div>
          {description && (
            <div className="text-[11px] text-nf-300 mt-1 leading-relaxed break-words font-normal">
              {description}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => onDismiss(id)}
          className="shrink-0 p-1 rounded-lg text-nf-400 hover:text-white hover:bg-white/[0.08] transition focus:outline-none cursor-pointer"
          aria-label="Close notification"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((options: ToastOptions) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const newToast: ToastItem = { ...options, id };
    setToasts((prev) => [...prev.slice(-4), newToast]);
  }, []);

  return (
    <ToastContext.Provider value={{ toast, dismiss, toasts }}>
      {children}
      {/* Liquid Glass Toast Viewport */}
      <div
        className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0"
        aria-label="Notifications"
      >
        {toasts.map((t) => (
          <ToastElement key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export default ToastProvider;
