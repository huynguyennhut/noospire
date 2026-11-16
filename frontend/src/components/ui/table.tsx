import * as React from 'react';
import { cn } from '@/lib/utils';

export const Table = React.forwardRef<
  HTMLTableElement,
  React.HTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <div className="relative w-full overflow-x-auto rounded-xl border border-white/[0.08] bg-[var(--bg-surface)] backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.35)]">
    <table
      ref={ref}
      className={cn('w-full caption-bottom text-left text-xs text-[var(--text-primary)]', className)}
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
      'bg-[var(--bg-surface-hover)] text-[var(--text-secondary)] uppercase tracking-wider text-[10px] border-b border-white/[0.08] font-bold select-none',
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
  <tbody ref={ref} className={cn('divide-y divide-white/[0.04]', className)} {...props} />
));
TableBody.displayName = 'TableBody';

export const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn('border-t border-white/[0.08] bg-[var(--bg-surface-hover)] font-medium text-[var(--text-secondary)]', className)}
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
      'border-b border-white/[0.04] transition-colors hover:bg-white/[0.025] data-[state=selected]:bg-white/[0.06] data-[state=selected]:border-l-2 data-[state=selected]:border-l-white',
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
    className={cn('py-3 px-3.5 font-bold text-[var(--text-secondary)] align-middle whitespace-nowrap', className)}
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
    className={cn('py-3 px-3.5 text-[var(--text-primary)] align-middle', className)}
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
    className={cn('mt-4 text-xs text-[var(--text-muted)] italic', className)}
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
    <TableCell colSpan={colSpan} className="py-12 text-center text-[var(--text-muted)]">
      <div className="flex flex-col items-center justify-center gap-2">
        {icon && <div className="text-nf-600">{icon}</div>}
        <span className="text-xs">{message}</span>
      </div>
    </TableCell>
  </TableRow>
);
