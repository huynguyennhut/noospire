# Milestone 5 Technical Specification: UI Primitives & Design System Foundation

**Author**: Teamwork Explorer (Milestone 5)  
**Target Milestone**: M5 (UI Foundation, Primitives, Responsive Shell & Chart Engine)  
**Working Directory**: `C:\Users\nguye\desktop\noospire`  
**State Directory**: `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m5_1\`  
**Date**: 2026-11-08  

---

## 1. Executive Summary & Architectural Positioning

Milestone 5 establishes the core reusable frontend architecture for NOOSFORGE Security Intelligence, creating a unified, production-grade UI design system based on the **Black/White/Liquid Glass dark UI theme**.

Currently, the frontend views (`/dashboard`, `/findings`, `/assets`, `/scans`, etc.) use ad-hoc Tailwind classes with duplicated modal implementations, inconsistent table padding, hardcoded badge colors, and non-standardized button variants. In addition, `frontend` lacks an ESLint configuration file (`.eslintrc.json`), causing automated calls to `npm run lint` (`next lint`) to stall and fail interactively with code 1 in headless/CI environments.

This specification provides the exact technical blueprints and drop-in TypeScript implementations for:
1. `frontend/.eslintrc.json` extending `next/core-web-vitals` to ensure non-interactive, automated CI linting passes cleanly.
2. Standard utility `cn` helper in `frontend/src/lib/utils.ts` combining `clsx` and `tailwind-merge`.
3. Standardized, lightweight, zero-bloat UI component primitives in `frontend/src/components/ui/`:
   - `card.tsx`: Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, and `StatCard`.
   - `button.tsx`: Button supporting 6 variants (`primary` cyan glow, `secondary` glass, `destructive` rose, `outline` specular border, `ghost`, `glass`), 4 sizes (`sm`, `md`, `lg`, `icon`), and loading spinner state.
   - `badge.tsx`: Badge supporting 6 severity levels (`critical`, `high`, `medium`, `low`, `info`, `neutral`), 2 sizes, pulsing dot indicator, and text glow.
   - `table.tsx`: Table, TableHeader, TableBody, TableHead, TableRow, TableCell, TableCaption, TableFooter, and TableEmpty with responsive overflow wrapper and hover states.
   - `modal.tsx`: Modal / Dialog with backdrop blur (`backdrop-blur-md`), specular border, close button (`X`), title, description, content, footer, keyboard `Escape` listener, and scroll lock.
   - `tabs.tsx`: Tabs, TabsList, TabsTrigger, TabsContent with active indicator highlight and keyboard/ARIA accessibility.
   - `input.tsx`: Input with glass background, cyan focus ring, specular border, optional search/prefix icon, and optional clear button.
   - `tooltip.tsx`: Floating hover tooltip with dark glass container, arrow pointer, and positional placement.
   - `index.ts`: Unified barrel exports.

All primitives strictly rely only on the project's pre-installed dependencies: React 18, TypeScript 5, Tailwind CSS 3, `clsx`, `tailwind-merge`, and `lucide-react`. No heavy third-party UI libraries (such as Radix UI, Headless UI, or Framer Motion) are introduced.

---

## 2. Directory Layout & File Manifest

```
frontend/
├── .eslintrc.json                    ← [NEW] Non-interactive Next.js ESLint configuration
├── package.json                      ← [MODIFY] Add devDependencies: eslint, eslint-config-next
├── src/
│   ├── lib/
│   │   ├── utils.ts                  ← [NEW] Standard cn() helper (clsx + tailwind-merge)
│   │   ├── api.ts                    ← [EXISTING]
│   │   ├── i18n.tsx                  ← [EXISTING]
│   │   └── types.ts                  ← [EXISTING]
│   ├── styles/
│   │   └── globals.css               ← [EXISTING] Liquid Glass & Specular design tokens
│   └── components/
│       ├── layout/
│       │   └── Shell.tsx             ← [EXISTING]
│       └── ui/                       ← [NEW DIRECTORY] Reusable UI Primitives
│           ├── card.tsx              ← Card, CardHeader, CardTitle, etc., and StatCard
│           ├── button.tsx            ← Button with variants, sizes & loading spinner
│           ├── badge.tsx             ← Severity badges with glow & dot indicator
│           ├── table.tsx             ← Responsive table, header, body, row, cells
│           ├── modal.tsx             ← Accessible liquid-glass dialog with ESC listener
│           ├── tabs.tsx              ← Accessible tab list, triggers & panels
│           ├── input.tsx             ← Glass input with focus cyan ring & search/clear icons
│           ├── tooltip.tsx           ← Floating hover tooltip with dark glass & arrow
│           └── index.ts              ← Barrel export for clean @/components/ui imports
```

---

## 3. ESLint Non-Interactive Configuration Specification

### 3.1 Problem Analysis
Running `npm run lint` (`next lint`) in `frontend/` currently results in an interactive prompt:
```
? How would you like to configure ESLint? https://nextjs.org/docs/basic-features/eslint
❯  Strict (recommended)
   Base
   Cancel
```
Because Antigravity CLI and CI runners operate in non-interactive terminal sessions, this prompt exits immediately with exit code 1.

### 3.2 Solution Specification
1. Create `frontend/.eslintrc.json` with the following configuration:
```json
{
  "extends": "next/core-web-vitals"
}
```

2. Add the required ESLint dependencies to `frontend/package.json` under `devDependencies`:
```json
"devDependencies": {
  "@types/node": "^20.17.0",
  "@types/react": "^18.3.12",
  "@types/react-dom": "^18.3.1",
  "autoprefixer": "^10.4.20",
  "eslint": "^8.57.0",
  "eslint-config-next": "14.2.24",
  "postcss": "^8.4.47",
  "tailwindcss": "^3.4.14",
  "typescript": "^5.6.3"
}
```
*Note*: `eslint-config-next: "14.2.24"` aligns exactly with `next: "^14.2.24"` in `dependencies`. Installing `eslint@^8.57.0` guarantees full compatibility with Next.js 14 and Node 18/20.

---

## 4. ClassName Utility: `src/lib/utils.ts`

To enable clean conditional styling and Tailwind class merging across all UI primitives, provide `src/lib/utils.ts`:

```typescript
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Combines conditional class names using clsx and merges Tailwind CSS classes safely using tailwind-merge.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

---

## 5. UI Component Primitives Technical Specifications

### 5.1 Card Primitives: `frontend/src/components/ui/card.tsx`

#### Architectural Requirements
- Implement standard modular card parts: `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`.
- Adhere to the `.liquid-glass-card` design token: `background: rgba(14, 21, 38, 0.6)`, `backdrop-filter: blur(16px)`, `border: 1px solid rgba(255, 255, 255, 0.08)`.
- Support `hoverElevate`: on hover, elevate surface to `rgba(20, 29, 51, 0.75)`, brighten border to `rgba(255, 255, 255, 0.2)`, translateY(-1px), and add subtle cyan glow.
- Support `glow`: `'cyan' | 'rose' | 'amber' | 'emerald' | 'none'`.
- Provide a composite `StatCard` component for KPI metrics (used extensively in `/dashboard` and `/active-assessments`).

#### Complete TypeScript Implementation
```typescript
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
      cyan: 'shadow-[0_0_20px_rgba(6,182,212,0.15)] border-cyan-500/30',
      rose: 'shadow-[0_0_20px_rgba(239,68,68,0.18)] border-rose-500/30',
      amber: 'shadow-[0_0_20px_rgba(245,158,11,0.18)] border-amber-500/30',
      emerald: 'shadow-[0_0_20px_rgba(16,185,129,0.18)] border-emerald-500/30',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'relative rounded-2xl border border-white/10 bg-cyber-900/60 backdrop-blur-md text-slate-100 shadow-md transition-all duration-200',
          hoverElevate &&
            'hover:bg-cyber-850/80 hover:border-white/20 hover:shadow-xl hover:-translate-y-0.5',
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
      'text-base md:text-lg font-black tracking-tight text-white flex items-center gap-2',
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
    className={cn('text-xs text-slate-400 font-normal leading-relaxed', className)}
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
      'flex items-center justify-between p-5 md:p-6 pt-0 border-t border-white/5 mt-auto text-xs text-slate-400',
      className
    )}
    {...props}
  />
));
CardFooter.displayName = 'CardFooter';

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
}

export const StatCard = React.forwardRef<HTMLDivElement, StatCardProps>(
  ({ title, value, subtitle, icon, trend, accent = 'cyan', className, ...props }, ref) => {
    const accentColors = {
      cyan: 'text-cyan-400',
      emerald: 'text-emerald-400',
      amber: 'text-amber-400',
      rose: 'text-rose-400',
      slate: 'text-slate-300',
    };

    return (
      <Card ref={ref} className={cn('p-4 md:p-5', className)} {...props}>
        <div className="flex items-center justify-between text-slate-400 text-xs">
          <span className="font-medium truncate">{title}</span>
          {icon && <div className="text-slate-500 shrink-0">{icon}</div>}
        </div>
        <div className={cn('mt-2 text-2xl md:text-3xl font-black tracking-tight', accentColors[accent])}>
          {value}
        </div>
        {(subtitle || trend) && (
          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-400">
            {subtitle && <span className="truncate">{subtitle}</span>}
            {trend && (
              <span
                className={cn(
                  'font-semibold ml-auto shrink-0',
                  trend.positive ? 'text-emerald-400' : 'text-rose-400'
                )}
              >
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
```

---

### 5.2 Button Primitive: `frontend/src/components/ui/button.tsx`

#### Architectural Requirements
- Variants:
  - `primary`: Cyan gradient with liquid glow: `from-cyan-500 to-cyan-400 text-slate-950 font-bold shadow-lg shadow-cyan-950/60 hover:from-cyan-400 hover:to-cyan-300 border border-cyan-400/40`.
  - `secondary`: Glass surface: `bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 border border-white/10 hover:border-white/20`.
  - `destructive`: Rose danger: `bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 hover:border-rose-500/50`.
  - `outline`: Specular border: `border border-white/15 bg-transparent hover:bg-white/[0.04] text-slate-200`.
  - `ghost`: Transparent hover: `bg-transparent hover:bg-white/[0.06] text-slate-400 hover:text-white`.
  - `glass`: Liquid glass container: `bg-cyber-900/60 backdrop-blur-md border border-white/10 hover:border-white/25 text-slate-200 hover:text-white shadow-glass`.
- Sizes:
  - `sm`: `px-2.5 py-1 text-xs rounded-lg gap-1.5`
  - `md`: `px-3.5 py-1.5 text-xs font-semibold rounded-xl gap-2`
  - `lg`: `px-5 py-2.5 text-sm font-bold rounded-xl gap-2.5`
  - `icon`: `p-2 rounded-xl h-8 w-8 justify-center`
- Loading state: `loading?: boolean` displays spinning icon (`Loader2` from `lucide-react`) and disables button with pointer-events-none.
- ForwardRef support with standard `HTMLButtonElement` attributes.

#### Complete TypeScript Implementation
```typescript
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
        'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-bold shadow-lg shadow-cyan-950/60 hover:from-cyan-400 hover:to-cyan-300 border border-cyan-400/40 active:scale-[0.98]',
      secondary:
        'bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 border border-white/10 hover:border-white/20 active:bg-white/[0.1]',
      destructive:
        'bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 hover:border-rose-500/50 shadow-sm shadow-rose-950/40 active:scale-[0.98]',
      outline:
        'border border-white/15 bg-transparent hover:bg-white/[0.04] text-slate-200 active:bg-white/[0.08]',
      ghost:
        'bg-transparent hover:bg-white/[0.06] text-slate-400 hover:text-white',
      glass:
        'bg-cyber-900/60 backdrop-blur-md border border-white/10 hover:border-white/25 text-slate-200 hover:text-white shadow-glass active:scale-[0.98]',
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
          'inline-flex items-center justify-center font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50 disabled:pointer-events-none select-none cursor-pointer',
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
```

---

### 5.3 Badge Primitive: `frontend/src/components/ui/badge.tsx`

#### Architectural Requirements
- Support 6 severity levels: `critical`, `high`, `medium`, `low`, `info`, `neutral`.
- Normalize input: accept both lowercase (`critical`) and uppercase (`CRITICAL`).
- Subtly glowing box-shadow and specular border matching `globals.css`.
- Optional `dot?: boolean` rendering a small pulsing status beacon.
- Sizes: `sm` (compact table cells) and `md` (detail cards/headers).

#### Complete TypeScript Implementation
```typescript
import * as React from 'react';
import { cn } from '@/lib/utils';

export type BadgeSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'neutral' | string;
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

    const severityStyles: Record<string, { bg: string; text: string; border: string; glow: string; dot: string }> = {
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
        bg: 'bg-cyan-500/10',
        text: 'text-cyan-400',
        border: 'border-cyan-500/30',
        glow: 'shadow-[0_0_12px_rgba(6,182,212,0.2)]',
        dot: 'bg-cyan-400 shadow-[0_0_6px_rgba(6,182,212,0.6)]',
      },
      neutral: {
        bg: 'bg-slate-500/10',
        text: 'text-slate-400',
        border: 'border-slate-500/20',
        glow: '',
        dot: 'bg-slate-400',
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
          'inline-flex items-center font-bold uppercase tracking-wider rounded-md border transition-colors',
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
```

---

### 5.4 Table Primitives: `frontend/src/components/ui/table.tsx`

#### Architectural Requirements
- Implement standard modular table components: `Table`, `TableHeader`, `TableBody`, `TableHead`, `TableRow`, `TableCell`, `TableCaption`, `TableFooter`, `TableEmpty`.
- Include automatic responsive container (`overflow-x-auto w-full`).
- Header styled with tactical dark theme: `bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10 font-bold`.
- Row hover highlight: `hover:bg-white/[0.02] transition-colors border-b border-white/5`.
- Selected row highlight: `data-[state=selected]:bg-cyan-950/40`.

#### Complete TypeScript Implementation
```typescript
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Table = React.forwardRef<
  HTMLTableElement,
  React.HTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <div className="relative w-full overflow-x-auto rounded-xl border border-white/10 bg-cyber-900/40 backdrop-blur-sm">
    <table
      ref={ref}
      className={cn('w-full caption-bottom text-left text-xs text-slate-200', className)}
      {...props}
    />
  </div>
));
Table.displayName = 'Table';

export const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead
    ref={ref}
    className={cn(
      'bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10 font-bold select-none',
      className
    )}
    {...props}
  />
));
TableHeader.displayName = 'TableHeader';

export const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody ref={ref} className={cn('divide-y divide-white/5', className)} {...props} />
));
TableBody.displayName = 'TableBody';

export const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn('border-t border-white/10 bg-cyber-950/50 font-medium text-slate-400', className)}
    {...props}
  />
));
TableFooter.displayName = 'TableFooter';

export const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      'border-b border-white/5 transition-colors hover:bg-white/[0.02] data-[state=selected]:bg-cyan-950/40 data-[state=selected]:border-l-2 data-[state=selected]:border-l-cyan-400',
      className
    )}
    {...props}
  />
));
TableRow.displayName = 'TableRow';

export const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn('py-3 px-3.5 font-bold text-slate-400 align-middle whitespace-nowrap', className)}
    {...props}
  />
));
TableHead.displayName = 'TableHead';

export const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn('py-3 px-3.5 text-slate-200 align-middle', className)}
    {...props}
  />
));
TableCell.displayName = 'TableCell';

export const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn('mt-4 text-xs text-slate-500 italic', className)}
    {...props}
  />
));
TableCaption.displayName = 'TableCaption';

export interface TableEmptyProps {
  colSpan: number;
  message?: string;
  icon?: React.ReactNode;
}

export const TableEmpty: React.FC<TableEmptyProps> = ({
  colSpan,
  message = 'No records found matching current criteria.',
  icon,
}) => (
  <TableRow>
    <TableCell colSpan={colSpan} className="py-12 text-center text-slate-500">
      <div className="flex flex-col items-center justify-center gap-2">
        {icon && <div className="text-slate-600">{icon}</div>}
        <span className="text-xs">{message}</span>
      </div>
    </TableCell>
  </TableRow>
);
```

---

### 5.5 Modal Primitive: `frontend/src/components/ui/modal.tsx`

#### Architectural Requirements
- Full-featured, accessible modal dialog with backdrop blur (`backdrop-blur-md`).
- Specular border styling adhering to `.liquid-glass-modal`: `border: 1px solid rgba(255, 255, 255, 0.15)`.
- Keyboard `Escape` listener to close modal automatically.
- Backdrop click listener with outside-click detection.
- Body scroll lock (`overflow: hidden` on `document.body` while mounted).
- Sizes: `'sm'` (max-w-md), `'md'` (max-w-lg), `'lg'` (max-w-2xl), `'xl'` (max-w-4xl), `'full'` (max-w-6xl).
- Portal-safe: mounts directly to `document.body` via `createPortal` when executed on the client.

#### Complete TypeScript Implementation
```typescript
'use client';

import * as React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: ModalSize;
  className?: string;
  closeOnBackdrop?: boolean;
  closeOnEsc?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  className,
  closeOnBackdrop = true,
  closeOnEsc = true,
}) => {
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  // Keyboard Escape listener
  React.useEffect(() => {
    if (!isOpen || !closeOnEsc) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeOnEsc, onClose]);

  // Body scroll locking
  React.useEffect(() => {
    if (isOpen) {
      const originalStyle = window.getComputedStyle(document.body).overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalStyle;
      };
    }
  }, [isOpen]);

  if (!mounted || !isOpen) return null;

  const sizeClasses: Record<ModalSize, string> = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-6xl',
  };

  const modalNode = (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
    >
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-cyber-950/80 backdrop-blur-md transition-opacity duration-200"
        onClick={() => {
          if (closeOnBackdrop) onClose();
        }}
      />

      {/* Modal Dialog Content */}
      <div
        className={cn(
          'relative w-full rounded-2xl border border-white/15 bg-gradient-to-b from-cyber-900/95 to-cyber-950/95 p-6 shadow-2xl backdrop-blur-xl transition-all duration-200 z-10 flex flex-col max-h-[calc(100vh-4rem)]',
          sizeClasses[size],
          className
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-white/10 shrink-0">
          <div>
            {title && (
              <h2 className="text-lg font-black tracking-tight text-white flex items-center gap-2">
                {title}
              </h2>
            )}
            {description && (
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">{description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white border border-white/10 transition shrink-0 ml-4"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable Body Content */}
        <div className="py-4 overflow-y-auto flex-1 text-xs text-slate-200 space-y-4">
          {children}
        </div>

        {/* Optional Footer */}
        {footer && (
          <div className="pt-4 border-t border-white/10 flex items-center justify-end gap-3 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  );

  return createPortal(modalNode, document.body);
};
```

---

### 5.6 Tabs Primitives: `frontend/src/components/ui/tabs.tsx`

#### Architectural Requirements
- Context-driven tab switching: `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`.
- Accessible: `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`.
- Support both controlled (`value` + `onValueChange`) and uncontrolled (`defaultValue`).
- Active indicator styling: `bg-white/[0.08] text-cyan-400 font-bold border border-white/20 shadow-sm`.

#### Complete TypeScript Implementation
```typescript
'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (val: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | undefined>(undefined);

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
}

export const Tabs: React.FC<TabsProps> = ({
  value,
  defaultValue = '',
  onValueChange,
  className,
  children,
  ...props
}) => {
  const [internalTab, setInternalTab] = React.useState(defaultValue);

  const activeTab = value !== undefined ? value : internalTab;

  const setActiveTab = React.useCallback(
    (val: string) => {
      if (value === undefined) {
        setInternalTab(val);
      }
      onValueChange?.(val);
    },
    [value, onValueChange]
  );

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className={cn('w-full flex flex-col space-y-4', className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
};

export const TabsList = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    role="tablist"
    className={cn(
      'inline-flex items-center gap-1 p-1 rounded-xl bg-cyber-950/80 border border-white/10 backdrop-blur-sm overflow-x-auto max-w-full',
      className
    )}
    {...props}
  />
));
TabsList.displayName = 'TabsList';

export interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
}

export const TabsTrigger = React.forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ className, value, children, ...props }, ref) => {
    const context = React.useContext(TabsContext);
    if (!context) {
      throw new Error('TabsTrigger must be used within a Tabs component');
    }

    const isActive = context.activeTab === value;

    return (
      <button
        ref={ref}
        type="button"
        role="tab"
        aria-selected={isActive}
        onClick={() => context.setActiveTab(value)}
        className={cn(
          'inline-flex items-center justify-center whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150 select-none cursor-pointer',
          isActive
            ? 'bg-white/[0.08] text-cyan-400 font-bold border border-white/20 shadow-sm'
            : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.03]',
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);
TabsTrigger.displayName = 'TabsTrigger';

export interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
}

export const TabsContent = React.forwardRef<HTMLDivElement, TabsContentProps>(
  ({ className, value, children, ...props }, ref) => {
    const context = React.useContext(TabsContext);
    if (!context) {
      throw new Error('TabsContent must be used within a Tabs component');
    }

    if (context.activeTab !== value) return null;

    return (
      <div
        ref={ref}
        role="tabpanel"
        className={cn('outline-none animate-fadeIn', className)}
        {...props}
      >
        {children}
      </div>
    );
  }
);
TabsContent.displayName = 'TabsContent';
```

---

### 5.7 Input Primitive: `frontend/src/components/ui/input.tsx`

#### Architectural Requirements
- Glass container: `bg-cyber-950/80 border border-white/10 text-white placeholder-slate-500 rounded-xl px-3 py-1.5 text-xs`.
- Focus ring: `focus:outline-none focus:border-cyan-500/80 focus:ring-1 focus:ring-cyan-500/50`.
- Leading icon support (`icon?: React.ReactNode` e.g., `<Search className="..." />`).
- Suffix clear icon support (`onClear?: () => void`).
- Error state styling (`error?: boolean | string`).

#### Complete TypeScript Implementation
```typescript
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
    const hasClear = onClear && value && String(value).length > 0;

    return (
      <div className="relative w-full">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">
            {icon}
          </div>
        )}
        <input
          ref={ref}
          type={type}
          value={value}
          disabled={disabled}
          className={cn(
            'w-full rounded-xl bg-cyber-950/80 border border-white/10 text-white placeholder-slate-500 px-3 py-1.5 text-xs transition-colors duration-150',
            'focus:outline-none focus:border-cyan-500/80 focus:ring-1 focus:ring-cyan-500/50',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            icon && 'pl-9',
            hasClear && 'pr-8',
            error && 'border-rose-500/80 focus:border-rose-500 focus:ring-rose-500/40 text-rose-200',
            className
          )}
          {...props}
        />
        {hasClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white p-0.5 rounded transition"
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
```

---

### 5.8 Tooltip Primitive: `frontend/src/components/ui/tooltip.tsx`

#### Architectural Requirements
- Zero heavyweight external dependencies.
- Floating dark glass container with specular border: `bg-cyber-900/95 backdrop-blur-md border border-white/15 text-slate-200 text-xs px-2.5 py-1 rounded-lg shadow-xl shadow-black/60 pointer-events-none z-50 whitespace-nowrap`.
- Arrow indicator positioned along the target side.
- Placements: `top`, `bottom`, `left`, `right`.
- Accessible `role="tooltip"`.

#### Complete TypeScript Implementation
```typescript
'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

export type TooltipSide = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipProps {
  content: React.ReactNode;
  side?: TooltipSide;
  delayMs?: number;
  className?: string;
  children: React.ReactNode;
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  side = 'top',
  delayMs = 150,
  className,
  children,
}) => {
  const [visible, setVisible] = React.useState(false);
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleMouseEnter = () => {
    timeoutRef.current = setTimeout(() => {
      setVisible(true);
    }, delayMs);
  };

  const handleMouseLeave = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setVisible(false);
  };

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const positionClasses: Record<TooltipSide, string> = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  const arrowClasses: Record<TooltipSide, string> = {
    top: 'top-full left-1/2 -translate-x-1/2 border-t-cyber-900/95 border-x-transparent border-b-transparent border-t-4 border-x-4 border-b-0',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-cyber-900/95 border-x-transparent border-t-transparent border-b-4 border-x-4 border-t-0',
    left: 'left-full top-1/2 -translate-y-1/2 border-l-cyber-900/95 border-y-transparent border-r-transparent border-l-4 border-y-4 border-r-0',
    right: 'right-full top-1/2 -translate-y-1/2 border-r-cyber-900/95 border-y-transparent border-l-transparent border-r-4 border-y-4 border-l-0',
  };

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
    >
      {children}
      {visible && content && (
        <div
          role="tooltip"
          className={cn(
            'absolute z-50 px-2.5 py-1 text-[11px] font-medium text-slate-200 bg-cyber-900/95 backdrop-blur-md border border-white/15 rounded-lg shadow-xl shadow-black/60 pointer-events-none whitespace-nowrap animate-fadeIn',
            positionClasses[side],
            className
          )}
        >
          {content}
          <div className={cn('absolute w-0 h-0', arrowClasses[side])} />
        </div>
      )}
    </div>
  );
};
```

---

### 5.9 Barrel Export: `frontend/src/components/ui/index.ts`

```typescript
export * from './card';
export * from './button';
export * from './badge';
export * from './table';
export * from './modal';
export * from './tabs';
export * from './input';
export * from './tooltip';
export { cn } from '@/lib/utils';
```

---

## 6. Design System Token Alignment Matrix

| UI Component | Applied Design Token / Class | CSS Specification | Dark Theme Rationale |
|---|---|---|---|
| **Card** | `.liquid-glass-card` / `Card` | `bg-cyber-900/60 backdrop-blur-md border-white/10` | Frosted dark glass container with subtle white specular border |
| **Card (Hover)** | `hoverElevate` | `bg-cyber-850/80 border-white/20 translateY(-1px)` | Smooth elevation feedback without harsh color shifts |
| **Button (Primary)** | Cyan Glow Gradient | `from-cyan-500 to-cyan-400 shadow-cyan-950/60` | High-contrast call to action for scan execution and primary triage |
| **Button (Secondary)** | Glass Surface | `bg-white/[0.04] border-white/10 text-slate-200` | Tactical secondary action with specular highlight |
| **Badge (Critical)** | Rose Glow | `bg-rose-500/10 text-rose-400 border-rose-500/30` | Immediate visual urgency for severe CVEs and active exploits |
| **Badge (Info)** | Cyan Glow | `bg-cyan-500/10 text-cyan-400 border-cyan-500/30` | Informational security observations and target verification tags |
| **Table** | Responsive Glass Container | `border-white/10 bg-cyber-900/40 backdrop-blur-sm` | Clean structured rows with subtle divider lines (`divide-white/5`) |
| **Modal** | `.liquid-glass-modal` | `bg-gradient-to-b from-cyber-900/95 to-cyber-950/95 border-white/15` | High-z-index focal overlay with keyboard ESC safety and backdrop blur |
| **Input** | Glass Input | `bg-cyber-950/80 border-white/10 focus:ring-cyan-500/50` | Sleek dark inputs with cyan focus state and search/clear icons |
| **Tabs** | Glass Tab Bar | `bg-cyber-950/80 border-white/10 active:text-cyan-400` | Smooth pill switcher with glowing active tab highlight |
| **Tooltip** | Glass Tooltip | `bg-cyber-900/95 border-white/15 shadow-xl` | Floating contextual help without third-party bundle weight |

---

## 7. Verification Method & Acceptance Protocol

### Step 1: Install Required ESLint Dependencies
```powershell
cd C:\Users\nguye\desktop\noospire\frontend
npm install -D eslint@^8.57.0 eslint-config-next@14.2.24
```

### Step 2: Write Files
- Create `frontend/.eslintrc.json` with `{"extends": "next/core-web-vitals"}`.
- Create `frontend/src/lib/utils.ts`.
- Create `frontend/src/components/ui/card.tsx`.
- Create `frontend/src/components/ui/button.tsx`.
- Create `frontend/src/components/ui/badge.tsx`.
- Create `frontend/src/components/ui/table.tsx`.
- Create `frontend/src/components/ui/modal.tsx`.
- Create `frontend/src/components/ui/tabs.tsx`.
- Create `frontend/src/components/ui/input.tsx`.
- Create `frontend/src/components/ui/tooltip.tsx`.
- Create `frontend/src/components/ui/index.ts`.

### Step 3: Run TypeScript Type Check
```powershell
cd C:\Users\nguye\desktop\noospire\frontend
npm run typecheck
```
*Expected*: Exits with code 0. Zero compiler errors.

### Step 4: Run Non-Interactive ESLint
```powershell
cd C:\Users\nguye\desktop\noospire\frontend
npm run lint
```
*Expected*: Executes non-interactively without prompting for setup. Exits with code 0.

### Step 5: Run Production Next.js Build
```powershell
cd C:\Users\nguye\desktop\noospire\frontend
npm run build
```
*Expected*: Static compilation of all 18 routes passes 100% cleanly.

### Step 6: Verify Backend Regression Protection
```powershell
cd C:\Users\nguye\desktop\noospire
python -m pytest tests/ -q
python scripts/verify_empire_e2e.py
```
*Expected*: All test suites pass without regression.
