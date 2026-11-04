import React from 'react';
import { Card, CardTitle } from '../ui/Card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { Info, CheckCircle2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { useDemoStore } from '../../store/demoStore';
import { cn } from '../../lib/utils';

interface FunnelStepProps {
  title: string;
  amount: string;
  percentage: string;
  theme: 'dark' | 'light';
}

const FunnelTrapezoid: React.FC<FunnelStepProps> = ({ title, amount, percentage, theme }) => {
  const isLight = theme === 'light';

  return (
    <div className="relative flex-1 flex flex-col items-center justify-center min-w-[90px] group">
      {/* SVG Background Trapezoid matching uploaded image */}
      <div className="relative w-full h-[82px] flex items-center justify-center">
        <svg
          viewBox="0 0 130 90"
          preserveAspectRatio="none"
          className={cn(
            "absolute inset-0 w-full h-full transition-all",
            isLight
              ? "drop-shadow-[0_2px_8px_rgba(99,102,241,0.12)] group-hover:drop-shadow-[0_4px_14px_rgba(99,102,241,0.25)]"
              : "drop-shadow-[0_2px_8px_rgba(168,85,247,0.15)] group-hover:drop-shadow-[0_4px_14px_rgba(168,85,247,0.3)]"
          )}
        >
          <defs>
            <linearGradient id={`trapezoidGrad-${theme}`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor={isLight ? "#EEF2FF" : "#2E184D"} />
              <stop offset="100%" stopColor={isLight ? "#DDD6FE" : "#120B20"} />
            </linearGradient>
            <linearGradient id={`trapezoidBorder-${theme}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={isLight ? "#6366F1" : "#A855F7"} />
              <stop offset="50%" stopColor={isLight ? "#8B5CF6" : "#C084FC"} />
              <stop offset="100%" stopColor={isLight ? "#6366F1" : "#A855F7"} />
            </linearGradient>
          </defs>
          <polygon
            points="4,4 126,4 108,86 22,86"
            fill={`url(#trapezoidGrad-${theme})`}
            stroke={isLight ? "#A5B4FC" : "#8B5CF6"}
            strokeWidth="1.5"
            strokeOpacity={isLight ? "0.9" : "0.4"}
            className={cn(
              "transition-all",
              isLight ? "group-hover:stroke-indigo-600" : "group-hover:stroke-purple-400 group-hover:stroke-opacity-80"
            )}
          />
          {/* Top highlight bar */}
          <line
            x1="8"
            y1="4"
            x2="122"
            y2="4"
            stroke={`url(#trapezoidBorder-${theme})`}
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>

        {/* Text Content inside the Trapezoid */}
        <div className="relative z-10 text-center flex flex-col items-center justify-center px-1 pt-0.5 space-y-0.5 pointer-events-none">
          <span className={cn(
            "text-[9.5px] font-bold tracking-tight whitespace-nowrap block truncate max-w-full px-1",
            isLight ? "text-indigo-950" : "text-purple-200/90"
          )}>
            {title}
          </span>
          <span className={cn(
            "text-sm sm:text-base font-black tabular-nums tracking-tight block leading-tight",
            isLight ? "text-slate-900 font-extrabold" : "text-white"
          )}>
            {amount}
          </span>
          <span className={cn(
            "text-[10px] font-bold block leading-tight",
            isLight ? "text-purple-700" : "text-slate-400"
          )}>
            {percentage}
          </span>
        </div>
      </div>
    </div>
  );
};

export const RecoveryFunnelInsightsCard: React.FC = () => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const steps = [
    { title: 'Revenue at Risk', amount: '₹18.42L', percentage: '100%' },
    { title: 'Identified Recoverable', amount: '₹11.76L', percentage: '63.8%' },
    { title: 'Actioned', amount: '₹9.38L', percentage: '50.9%' },
    { title: 'Recovered', amount: '₹7.82L', percentage: '42.4%' },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.15 }}
      className="w-full h-full"
    >
      <Card className={cn(
        "rounded-2xl p-3.5 sm:p-4 shadow-xl backdrop-blur-md overflow-hidden h-full flex flex-col justify-between transition-colors border",
        isLight
          ? "bg-white border-slate-200 text-slate-900 shadow-sm"
          : "border-slate-800 bg-[#0B101D]/95 text-white shadow-2xl"
      )}>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5 items-center my-auto">
          {/* Left: Recovery Funnel (approx 58% width = 7 cols) */}
          <div className="md:col-span-7 space-y-2">
            <div className="flex items-center gap-1.5">
              <CardTitle className={cn("text-xs sm:text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <span>Recovery Funnel</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 cursor-pointer" />
                    </TooltipTrigger>
                    <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                      <p>Full-funnel conversion efficiency from gross failure to captured recovery</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </CardTitle>
            </div>

            {/* 4 Trapezoid Cards with Right Arrows */}
            <div className="flex items-center justify-between gap-1 sm:gap-1.5 pt-0.5 overflow-x-auto scrollbar-none">
              {steps.map((step, idx) => (
                <React.Fragment key={step.title}>
                  <FunnelTrapezoid
                    title={step.title}
                    amount={step.amount}
                    percentage={step.percentage}
                    theme={theme}
                  />
                  {idx < steps.length - 1 && (
                    <div className={cn(
                      "shrink-0 px-0.5 text-[11px] font-bold select-none",
                      isLight ? "text-slate-400" : "text-slate-500"
                    )}>
                      →
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Right: Key Insights + Growth Artwork (approx 42% width = 5 cols) */}
          <div className={cn(
            "md:col-span-5 pl-0 md:pl-2 space-y-2 border-t md:border-t-0 pt-2 md:pt-0",
            isLight ? "border-slate-100" : "border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <CardTitle className={cn("text-xs sm:text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <span>Key Insights</span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 cursor-pointer" />
                    </TooltipTrigger>
                    <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                      <p>Statistical benchmarks computed over current evaluation cycle</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </CardTitle>
            </div>

            <div className="flex items-center justify-between gap-2">
              {/* Checklist */}
              <ul className="space-y-1 text-[11px] flex-1">
                <li className="flex items-center gap-1.5">
                  <CheckCircle2 className={cn("w-3 h-3 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400 fill-emerald-400/20")} />
                  <span className={cn("text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    WAPSI recovers <strong className={cn("font-bold", isLight ? "text-emerald-700 font-extrabold" : "text-emerald-400")}>37.7%</strong> more vs baseline
                  </span>
                </li>
                <li className="flex items-center gap-1.5">
                  <CheckCircle2 className={cn("w-3 h-3 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400 fill-emerald-400/20")} />
                  <span className={cn("text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    <strong className={cn("font-bold", isLight ? "text-emerald-700 font-extrabold" : "text-emerald-400")}>40.7%</strong> fewer attempts used
                  </span>
                </li>
                <li className="flex items-center gap-1.5">
                  <CheckCircle2 className={cn("w-3 h-3 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400 fill-emerald-400/20")} />
                  <span className={cn("text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    <strong className={cn("font-bold", isLight ? "text-emerald-700 font-extrabold" : "text-emerald-400")}>61.4%</strong> fewer contacts made
                  </span>
                </li>
                <li className="flex items-center gap-1.5">
                  <CheckCircle2 className={cn("w-3 h-3 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400 fill-emerald-400/20")} />
                  <span className={cn("text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    <strong className={cn("font-bold", isLight ? "text-emerald-700 font-extrabold" : "text-emerald-400")}>2.5x</strong> more recovery per contact
                  </span>
                </li>
                <li className="flex items-center gap-1.5">
                  <CheckCircle2 className={cn("w-3 h-3 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400 fill-emerald-400/20")} />
                  <span className={cn("text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    AI decisions have <strong className={cn("font-bold", isLight ? "text-emerald-700 font-extrabold" : "text-emerald-400")}>91%</strong> median confidence
                  </span>
                </li>
              </ul>

              {/* Stylized Growth Trend Graphic */}
              <div className="shrink-0 w-14 h-14 sm:w-16 sm:h-16 flex items-center justify-center relative">
                <svg viewBox="0 0 80 80" className="w-full h-full drop-shadow-[0_0_10px_rgba(168,85,247,0.25)]">
                  <defs>
                    <linearGradient id={`barGradCompact-${theme}`} x1="0%" y1="1" x2="0%" y2="0">
                      <stop offset="0%" stopColor={isLight ? "#C7D2FE" : "#3B1D6E"} stopOpacity={isLight ? 0.6 : 0.4} />
                      <stop offset="100%" stopColor={isLight ? "#6366F1" : "#A855F7"} stopOpacity={0.9} />
                    </linearGradient>
                    <linearGradient id={`arrowGradCompact-${theme}`} x1="0%" y1="1" x2="1" y2="0">
                      <stop offset="0%" stopColor={isLight ? "#6366F1" : "#A855F7"} />
                      <stop offset="100%" stopColor={isLight ? "#8B5CF6" : "#C084FC"} />
                    </linearGradient>
                  </defs>
                  <rect x="10" y="55" width="8" height="15" rx="2" fill={`url(#barGradCompact-${theme})`} />
                  <rect x="22" y="45" width="8" height="25" rx="2" fill={`url(#barGradCompact-${theme})`} />
                  <rect x="34" y="35" width="8" height="35" rx="2" fill={`url(#barGradCompact-${theme})`} />
                  <rect x="46" y="25" width="8" height="45" rx="2" fill={`url(#barGradCompact-${theme})`} />
                  <rect x="58" y="15" width="8" height="55" rx="2" fill={`url(#barGradCompact-${theme})`} />

                  <path
                    d="M 12 50 Q 35 40, 64 16"
                    fill="none"
                    stroke={`url(#arrowGradCompact-${theme})`}
                    strokeWidth="3"
                    strokeLinecap="round"
                  />
                  <polygon
                    points="56,12 70,14 66,28"
                    fill={isLight ? "#7C3AED" : "#C084FC"}
                  />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </motion.div>
  );
};
