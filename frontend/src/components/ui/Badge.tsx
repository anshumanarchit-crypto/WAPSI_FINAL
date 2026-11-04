import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        default: 'border border-slate-700 bg-slate-800 text-slate-200',
        secondary: 'border border-slate-700/60 bg-slate-800/40 text-slate-300',
        success: 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        warning: 'border border-amber-500/30 bg-amber-500/10 text-amber-400',
        destructive: 'border border-red-500/30 bg-red-500/10 text-red-400',
        info: 'border border-cyan-500/30 bg-cyan-500/10 text-cyan-400',
        purple: 'border border-indigo-500/30 bg-indigo-500/15 text-indigo-300',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
