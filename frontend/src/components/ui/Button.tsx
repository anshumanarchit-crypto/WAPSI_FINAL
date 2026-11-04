import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500 disabled:pointer-events-none disabled:opacity-50 select-none',
  {
    variants: {
      variant: {
        default:
          'bg-indigo-600 text-white shadow hover:bg-indigo-500 active:scale-[0.98]',
        primary:
          'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-500/25 hover:from-indigo-500 hover:to-purple-500 active:scale-[0.98]',
        success:
          'bg-emerald-600 text-white shadow hover:bg-emerald-500 active:scale-[0.98]',
        destructive:
          'bg-red-600 text-white shadow-sm hover:bg-red-500 active:scale-[0.98]',
        outline:
          'border border-slate-700 bg-slate-900/60 text-slate-200 shadow-sm hover:bg-slate-800 hover:text-white',
        secondary:
          'bg-slate-800 text-slate-100 shadow-sm hover:bg-slate-700',
        ghost: 'text-slate-300 hover:bg-slate-800/80 hover:text-white',
        link: 'text-indigo-400 underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-10 rounded-lg px-8 text-base',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';
