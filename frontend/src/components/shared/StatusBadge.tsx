import React from 'react';
import { cn } from '../../lib/utils';
import { CaseStatus } from '../../types';

interface StatusBadgeProps {
  status: CaseStatus | string;
  size?: 'sm' | 'md';
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md', className }) => {
  const getBadgeStyle = (s: string) => {
    switch (s.toUpperCase()) {
      case 'READY':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'APPROVED':
        return 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40';
      case 'RECOVERED':
        return 'bg-emerald-500/20 text-emerald-300 border-emerald-400/50 shadow-sm shadow-emerald-500/20';
      case 'REVIEW':
      case 'NEEDS REVIEW':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
      case 'MONITORING':
        return 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30';
      case 'ACTIONED':
        return 'bg-blue-500/15 text-blue-400 border-blue-500/30';
      case 'FAILED':
        return 'bg-rose-500/15 text-rose-400 border-rose-500/30';
      case 'ESCALATED':
        return 'bg-purple-500/15 text-purple-400 border-purple-500/30';
      case 'DETECTED':
      case 'SCORED':
        return 'bg-slate-700/50 text-slate-300 border-slate-600/50';
      case 'WITHIN LIMIT':
      case 'HEALTHY':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'NEAR LIMIT':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <span
      className={cn(
        'inline-flex items-center border whitespace-nowrap',
        size === 'sm' 
          ? 'px-1.5 py-0.2 rounded text-[9px] font-bold tracking-normal uppercase'
          : 'px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase',
        getBadgeStyle(status),
        className
      )}
    >
      {status}
    </span>
  );
};
