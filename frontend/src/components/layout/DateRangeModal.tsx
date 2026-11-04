import React, { useState, useEffect } from 'react';
import { 
  Calendar as CalendarIcon, 
  X, 
  Check, 
  Clock, 
  Sparkles,
  ArrowRight,
  TrendingUp
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { cn } from '../../lib/utils';

export const DateRangeModal: React.FC = () => {
  const isDateRangeModalOpen = useDemoStore((state) => state.isDateRangeModalOpen);
  const setDateRangeModalOpen = useDemoStore((state) => state.setDateRangeModalOpen);
  const selectedDateRange = useDemoStore((state) => state.selectedDateRange);
  const setSelectedDateRange = useDemoStore((state) => state.setSelectedDateRange);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const presets = [
    { label: 'Last 7 Days (Aug 22 – Aug 28, 2025)', value: 'Aug 22 – Aug 28, 2025', tag: 'Default', desc: 'Current 7-day rolling evaluation window' },
    { label: 'Today (Aug 28, 2025 - Live)', value: 'Today (Aug 28, 2025)', tag: 'Live Pulse', desc: 'Intraday hourly recovery telemetry' },
    { label: 'Last 14 Days (Aug 15 – Aug 28)', value: 'Aug 15 – Aug 28, 2025', desc: 'Bi-weekly treatment evaluation cycle' },
    { label: 'This Month (August 2025)', value: 'Aug 1 – Aug 28, 2025', tag: 'Billing Cycle', desc: 'Full calendar month-to-date metrics' },
    { label: 'Last Month (July 2025)', value: 'Jul 1 – Jul 31, 2025', desc: 'Settled historical recovery baseline' },
    { label: 'Last 90 Days (Q2/Q3 2025)', value: 'Jun 1 – Aug 28, 2025', desc: 'Quarterly macro causal lift trend' },
    { label: 'Year to Date (2025)', value: 'Jan 1 – Aug 28, 2025', desc: 'Annualized cumulative recovery payoff' },
  ];

  const [tempRange, setTempRange] = useState(selectedDateRange);
  const [startDate, setStartDate] = useState('2025-08-01');
  const [endDate, setEndDate] = useState('2025-08-28');
  const [compareMode, setCompareMode] = useState<'baseline' | 'prev_period' | 'none'>('baseline');

  useEffect(() => {
    setTempRange(selectedDateRange);
  }, [selectedDateRange, isDateRangeModalOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isDateRangeModalOpen) {
        setDateRangeModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDateRangeModalOpen, setDateRangeModalOpen]);

  if (!isDateRangeModalOpen) return null;

  const handleApply = () => {
    setSelectedDateRange(tempRange);
    setDateRangeModalOpen(false);
  };

  return (
    <div 
      className={cn(
        "fixed inset-0 z-50 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-150 transition-colors",
        isLight ? "bg-slate-900/40" : "bg-black/80"
      )}
      onClick={() => setDateRangeModalOpen(false)}
    >
      <div 
        className={cn(
          "w-full max-w-lg border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-in zoom-in-95 duration-150 relative text-xs transition-colors",
          isLight 
            ? "bg-white border-slate-200 text-slate-900 shadow-slate-900/20" 
            : "bg-[#0B111E] border-slate-700/80 text-white"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className={cn(
          "px-5 py-3.5 border-b flex items-center justify-between shrink-0 transition-colors",
          isLight ? "bg-slate-50 border-slate-200" : "bg-[#080D1A] border-slate-800"
        )}>
          <div className="flex items-center gap-2.5">
            <div className={cn(
              "p-1.5 rounded-lg border",
              isLight 
                ? "bg-indigo-50 text-indigo-600 border-indigo-200 shadow-xs" 
                : "bg-indigo-500/20 text-indigo-400 border-indigo-500/30"
            )}>
              <CalendarIcon className="w-4 h-4" />
            </div>
            <div>
              <h3 className={cn(
                "text-sm font-bold flex items-center gap-2",
                isLight ? "text-slate-900" : "text-white"
              )}>
                Select Analysis Timeframe
              </h3>
              <p className={cn("text-[10.5px]", isLight ? "text-slate-500" : "text-slate-400")}>
                Filter causal analytics, queue metrics, and decision windows
              </p>
            </div>
          </div>
          <button
            onClick={() => setDateRangeModalOpen(false)}
            className={cn(
              "p-1.5 rounded-lg transition-colors cursor-pointer",
              isLight ? "text-slate-400 hover:text-slate-700 hover:bg-slate-200/60" : "text-slate-400 hover:text-white hover:bg-slate-800"
            )}
            title="Close (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 text-xs overflow-y-auto">
          {/* Preset Buttons */}
          <div>
            <label className={cn(
              "text-[10px] font-bold uppercase tracking-wider block mb-2",
              isLight ? "text-slate-500" : "text-slate-400"
            )}>
              Timeframe Presets
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {presets.map((preset) => {
                const isSelected = tempRange === preset.value;
                return (
                  <button
                    key={preset.value}
                    onClick={() => setTempRange(preset.value)}
                    className={cn(
                      'p-2.5 rounded-xl border text-left transition-all relative flex flex-col justify-between group cursor-pointer shadow-xs',
                      isSelected
                        ? isLight
                          ? 'bg-indigo-50/90 border-indigo-500 text-indigo-950 ring-1 ring-indigo-500 shadow-indigo-100'
                          : 'bg-indigo-950/70 border-indigo-500 text-white shadow-md shadow-indigo-600/30 ring-1 ring-indigo-500'
                        : isLight
                        ? 'bg-slate-50/80 border-slate-200 text-slate-800 hover:bg-slate-100 hover:border-slate-300'
                        : 'bg-slate-900/80 border-slate-800/90 text-slate-300 hover:bg-slate-850 hover:border-slate-700'
                    )}
                  >
                    <div className="flex items-center justify-between w-full mb-0.5">
                      <span className={cn("font-bold text-xs flex items-center gap-1.5", isSelected && isLight ? "text-indigo-950 font-black" : "")}>
                        {preset.label}
                      </span>
                      {isSelected && (
                        <Check className={cn("w-3.5 h-3.5 shrink-0", isLight ? "text-indigo-600" : "text-indigo-400")} />
                      )}
                    </div>
                    <span className={cn("text-[10px] line-clamp-1", isLight ? "text-slate-500" : "text-slate-400")}>
                      {preset.desc}
                    </span>
                    {preset.tag && (
                      <span className={cn(
                        "inline-block mt-1.5 text-[8.5px] font-bold px-1.5 py-0.2 rounded border w-fit",
                        isLight
                          ? "bg-indigo-100/80 text-indigo-700 border-indigo-200"
                          : "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                      )}>
                        {preset.tag}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Custom Date Range Picker */}
          <div className={cn(
            "p-3 rounded-xl border space-y-2 transition-colors",
            isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/90 border-slate-800"
          )}>
            <label className={cn(
              "text-[10.5px] font-bold flex items-center justify-between",
              isLight ? "text-slate-800" : "text-slate-300"
            )}>
              <span>Or Specify Custom Date Range</span>
              <span className={cn("text-[9.5px] font-mono", isLight ? "text-indigo-600" : "text-indigo-400")}>YYYY-MM-DD</span>
            </label>
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <span className={cn("text-[9.5px] block mb-1 font-medium", isLight ? "text-slate-600" : "text-slate-400")}>Start Date</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => {
                    setStartDate(e.target.value);
                    setTempRange(`${e.target.value} – ${endDate}`);
                  }}
                  className={cn(
                    "w-full rounded-lg px-2.5 py-1 text-xs focus:outline-none transition-colors border",
                    isLight 
                      ? "bg-white border-slate-300 text-slate-900 focus:border-indigo-500 shadow-xs" 
                      : "bg-slate-950 border-slate-700 text-white focus:border-indigo-500"
                  )}
                />
              </div>
              <div>
                <span className={cn("text-[9.5px] block mb-1 font-medium", isLight ? "text-slate-600" : "text-slate-400")}>End Date</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => {
                    setEndDate(e.target.value);
                    setTempRange(`${startDate} – ${e.target.value}`);
                  }}
                  className={cn(
                    "w-full rounded-lg px-2.5 py-1 text-xs focus:outline-none transition-colors border",
                    isLight 
                      ? "bg-white border-slate-300 text-slate-900 focus:border-indigo-500 shadow-xs" 
                      : "bg-slate-950 border-slate-700 text-white focus:border-indigo-500"
                  )}
                />
              </div>
            </div>
          </div>

          {/* Comparison Baseline Toggle */}
          <div className={cn(
            "p-3 rounded-xl border space-y-1.5 transition-colors",
            isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/70 border-slate-800"
          )}>
            <span className={cn("text-[10.5px] font-bold block", isLight ? "text-slate-800" : "text-slate-300")}>
              Counterfactual Baseline Comparison
            </span>
            <div className="grid grid-cols-3 gap-1.5">
              <button
                type="button"
                onClick={() => setCompareMode('baseline')}
                className={cn(
                  'p-1.5 rounded-lg text-center text-xs font-semibold border transition-all cursor-pointer shadow-xs',
                  compareMode === 'baseline'
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                    : isLight
                    ? 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                )}
              >
                Organic Baseline
              </button>
              <button
                type="button"
                onClick={() => setCompareMode('prev_period')}
                className={cn(
                  'p-1.5 rounded-lg text-center text-xs font-semibold border transition-all cursor-pointer shadow-xs',
                  compareMode === 'prev_period'
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                    : isLight
                    ? 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                )}
              >
                Previous Period
              </button>
              <button
                type="button"
                onClick={() => setCompareMode('none')}
                className={cn(
                  'p-1.5 rounded-lg text-center text-xs font-semibold border transition-all cursor-pointer shadow-xs',
                  compareMode === 'none'
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                    : isLight
                    ? 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                )}
              >
                No Baseline
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className={cn(
          "px-5 py-3.5 border-t flex items-center justify-between shrink-0 transition-colors",
          isLight ? "bg-slate-50 border-slate-200" : "bg-[#080D1A] border-slate-800"
        )}>
          <span className={cn("text-[11px] truncate max-w-[200px]", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>
            Selected: <strong className={cn("font-mono font-bold", isLight ? "text-indigo-700" : "text-indigo-300")}>{tempRange}</strong>
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDateRangeModalOpen(false)}
              className={cn(
                "text-xs font-semibold",
                isLight ? "bg-white border-slate-300 text-slate-700 hover:bg-slate-100" : ""
              )}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5 text-xs font-bold shadow-sm"
            >
              <Check className="w-3.5 h-3.5" />
              Apply Range
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
