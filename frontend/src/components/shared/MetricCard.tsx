import React from 'react';
import { Card } from '../ui/Card';
import { cn } from '../../lib/utils';
import { MiniBarChart } from './MiniBarChart';
import { ArrowUpRight, ArrowDownRight, Info } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { motion } from 'framer-motion';
import { useDemoStore } from '../../store/demoStore';

export interface MetricCardProps {
  title: string;
  value: string;
  delta?: string;
  deltaType?: 'positive' | 'negative' | 'neutral' | 'warning' | 'info';
  deltaSubtext?: string;
  subtext?: string;
  infoTooltip?: string;
  accentColor?: 'purple' | 'emerald' | 'amber' | 'rose' | 'cyan';
  icon?: React.ReactNode;
  barData?: number[];
  sparklineData?: number[];
  className?: string;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  delta,
  deltaType = 'positive',
  deltaSubtext = 'vs baseline',
  subtext,
  infoTooltip,
  accentColor = 'purple',
  icon,
  barData,
  sparklineData,
  className,
  onClick,
}) => {
  const theme = useDemoStore((state) => state.theme);

  const getTopBorderAndGlow = () => {
    switch (accentColor) {
      case 'rose':
        return theme === 'light' ? 'border-t-2 border-t-rose-500' : 'border-t-2 border-t-rose-500/80 shadow-rose-950/20';
      case 'amber':
        return theme === 'light' ? 'border-t-2 border-t-amber-500' : 'border-t-2 border-t-amber-500/80 shadow-amber-950/20';
      case 'emerald':
        return theme === 'light' ? 'border-t-2 border-t-emerald-500' : 'border-t-2 border-t-emerald-500/80 shadow-emerald-950/20';
      case 'cyan':
        return theme === 'light' ? 'border-t-2 border-t-cyan-500' : 'border-t-2 border-t-cyan-500/80 shadow-cyan-950/20';
      default:
        return theme === 'light' ? 'border-t-2 border-t-indigo-500' : 'border-t-2 border-t-indigo-500/80 shadow-indigo-950/20';
    }
  };

  const getIconBadgeClass = () => {
    if (theme === 'light') {
      switch (accentColor) {
        case 'rose':
          return 'bg-rose-50 text-rose-700 border border-rose-200';
        case 'amber':
          return 'bg-amber-50 text-amber-700 border border-amber-200';
        case 'emerald':
          return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
        case 'cyan':
          return 'bg-cyan-50 text-cyan-700 border border-cyan-200';
        default:
          return 'bg-indigo-50 text-indigo-700 border border-indigo-200';
      }
    }
    switch (accentColor) {
      case 'rose':
        return 'bg-rose-500/15 text-rose-400 border border-rose-500/30';
      case 'amber':
        return 'bg-amber-500/15 text-amber-400 border border-amber-500/30';
      case 'emerald':
        return 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30';
      case 'cyan':
        return 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30';
      default:
        return 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30';
    }
  };

  const getDeltaBadgeClass = () => {
    if (theme === 'light') {
      switch (deltaType) {
        case 'positive':
          return 'text-emerald-800 bg-emerald-100 border-emerald-300';
        case 'warning':
          return 'text-amber-800 bg-amber-100 border-amber-300';
        case 'negative':
          return 'text-rose-800 bg-rose-100 border-rose-300';
        case 'info':
          return 'text-cyan-800 bg-cyan-100 border-cyan-300';
        default:
          return 'text-slate-700 bg-slate-100 border-slate-300';
      }
    }
    switch (deltaType) {
      case 'positive':
        return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
      case 'warning':
        return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
      case 'negative':
        return 'text-rose-400 bg-rose-500/10 border-rose-500/30';
      case 'info':
        return 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30';
      default:
        return 'text-slate-400 bg-slate-800 border-slate-700';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      whileHover={{ 
        x: -4, 
        rotateZ: -1.2,
        scale: 1.015,
        transition: { type: 'spring', stiffness: 400, damping: 25 }
      }}
      className="h-full cursor-pointer"
      onClick={onClick}
    >
      <Card
        className={cn(
          'relative overflow-hidden p-3.5 rounded-xl transition-all group h-full flex flex-col justify-between select-none shadow-xl backdrop-blur-md',
          theme === 'light'
            ? 'bg-white border-slate-200 text-slate-900 hover:border-slate-300 shadow-sm'
            : 'border-slate-800 bg-[#0B111E]/95 text-slate-100 hover:border-slate-600',
          getTopBorderAndGlow(),
          className
        )}
      >
        <div>
          {/* Header with circular icon badge, title & info button */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              {icon && (
                <div className={cn('w-5 h-5 rounded-md flex items-center justify-center text-xs shrink-0', getIconBadgeClass())}>
                  {icon}
                </div>
              )}
              <span className={cn(
                "text-[10.5px] font-bold uppercase tracking-wider truncate",
                theme === 'light' ? "text-slate-600" : "text-slate-400"
              )}>
                {title}
              </span>
            </div>
            {infoTooltip && (
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button className={cn(
                      "transition-colors p-0.5",
                      theme === 'light' ? "text-slate-400 hover:text-slate-600" : "text-slate-500 hover:text-slate-300"
                    )}>
                      <Info className="w-3 h-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="bg-slate-900 border border-slate-700 text-slate-200 text-xs p-2 max-w-xs shadow-xl">
                    <p>{infoTooltip}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>

          {/* Numeric Value + Glowing Trend Arrow Badge */}
          <div className="mt-2 flex items-baseline justify-between gap-1.5">
            <div className={cn(
              "text-xl sm:text-2xl font-black tracking-tight tabular-nums",
              theme === 'light' ? "text-slate-900" : "text-white"
            )}>
              {value}
            </div>
            {delta && (
              <div className={cn(
                'flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10.5px] font-bold tabular-nums border shadow-sm',
                getDeltaBadgeClass()
              )}>
                <ArrowUpRight className="w-3 h-3" />
                <span>{delta}</span>
              </div>
            )}
          </div>
        </div>

        {/* Delta footer row */}
        {(deltaSubtext || subtext) && (
          <div className={cn(
            "mt-2 flex items-center justify-between text-[10px] pt-1.5 border-t",
            theme === 'light' ? "border-slate-200 text-slate-500" : "border-slate-800/80 text-slate-400"
          )}>
            <span>{deltaSubtext || ''}</span>
            {subtext && <span className={cn(
              "truncate max-w-[120px]",
              theme === 'light' ? "text-slate-600" : "text-slate-500"
            )}>{subtext}</span>}
          </div>
        )}
      </Card>
    </motion.div>
  );
};
