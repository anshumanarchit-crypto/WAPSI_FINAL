import React, { useState, useEffect } from 'react';
import { 
  Filter, 
  X, 
  Check, 
  RotateCcw, 
  ShieldCheck, 
  Layers, 
  TrendingUp, 
  CheckCircle2, 
  Sliders,
  Sparkles
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { cn } from '../../lib/utils';

export const FiltersModal: React.FC = () => {
  const isFiltersModalOpen = useDemoStore((state) => state.isFiltersModalOpen);
  const setFiltersModalOpen = useDemoStore((state) => state.setFiltersModalOpen);
  const filtersState = useDemoStore((state) => state.filtersState);
  const updateFiltersState = useDemoStore((state) => state.updateFiltersState);
  const resetFilters = useDemoStore((state) => state.resetFilters);

  const [tempFilters, setTempFilters] = useState(filtersState);

  useEffect(() => {
    setTempFilters(filtersState);
  }, [filtersState, isFiltersModalOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFiltersModalOpen) {
        setFiltersModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFiltersModalOpen, setFiltersModalOpen]);

  if (!isFiltersModalOpen) return null;

  const toggleDomain = (domain: string) => {
    setTempFilters((prev) => ({
      ...prev,
      domains: prev.domains.includes(domain)
        ? prev.domains.filter((d) => d !== domain)
        : [...prev.domains, domain],
    }));
  };

  const toggleStatus = (status: string) => {
    setTempFilters((prev) => ({
      ...prev,
      statuses: prev.statuses.includes(status)
        ? prev.statuses.filter((s) => s !== status)
        : [...prev.statuses, status],
    }));
  };

  const toggleEvidence = (evidence: string) => {
    setTempFilters((prev) => ({
      ...prev,
      evidenceSources: prev.evidenceSources.includes(evidence)
        ? prev.evidenceSources.filter((e) => e !== evidence)
        : [...prev.evidenceSources, evidence],
    }));
  };

  const handleApply = () => {
    updateFiltersState(tempFilters);
    setFiltersModalOpen(false);
  };

  const handleReset = () => {
    resetFilters();
    setTempFilters({
      domains: ['Subscriptions', 'Checkout', 'B2B'],
      minUplift: 10,
      minConfidence: 75,
      evidenceSources: ['Network Data', 'Merchant Prior', 'Enclave Attested'],
      statuses: ['READY', 'REVIEW', 'APPROVED'],
      onlyHighImpact: false,
      regulatoryBoundsVerified: true,
    });
  };

  const domainOptions = ['Subscriptions', 'Checkout', 'B2B'];
  const statusOptions = ['READY', 'REVIEW', 'APPROVED', 'ACTIONED', 'RECOVERED'];
  const evidenceOptions = ['Network Data', 'Merchant Prior', 'Enclave Attested', 'Issuer Prior'];

  return (
    <div 
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-150"
      onClick={() => setFiltersModalOpen(false)}
    >
      <div 
        className="w-full max-w-lg bg-[#0B111E] border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-150 max-h-[85vh] relative text-xs"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 bg-[#0B0F19] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <Filter className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                Configure Global Causal & Policy Filters
              </h3>
              <p className="text-[11px] text-slate-400">
                Refine recovery cases, decision threshold bounds, and telemetry scope
              </p>
            </div>
          </div>
          <button
            onClick={() => setFiltersModalOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs">
          {/* Recovery Domains */}
          <div className="space-y-2">
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
              Payment Domains
            </label>
            <div className="grid grid-cols-3 gap-2">
              {domainOptions.map((domain) => {
                const isChecked = tempFilters.domains.includes(domain);
                return (
                  <button
                    key={domain}
                    type="button"
                    onClick={() => toggleDomain(domain)}
                    className={cn(
                      'p-2.5 rounded-xl border text-xs font-semibold flex items-center justify-between transition-all',
                      isChecked
                        ? 'bg-indigo-950/60 border-indigo-500 text-white shadow-sm ring-1 ring-indigo-500/50'
                        : 'bg-slate-900/80 border-slate-800 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    <span>{domain}</span>
                    {isChecked && <Check className="w-3.5 h-3.5 text-indigo-400" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Causal Uplift & Confidence Sliders */}
          <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] font-bold text-slate-300">
                  Minimum Incremental Uplift Threshold (τ)
                </span>
                <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  +{tempFilters.minUplift}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="30"
                step="5"
                value={tempFilters.minUplift}
                onChange={(e) => setTempFilters({ ...tempFilters, minUplift: parseInt(e.target.value) })}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>0% (All treatments)</span>
                <span>+15% (Recommended)</span>
                <span>+30% (High Lift)</span>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] font-bold text-slate-300">
                  Minimum Decision Confidence
                </span>
                <span className="text-xs font-mono font-bold text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                  {tempFilters.minConfidence}%
                </span>
              </div>
              <input
                type="range"
                min="50"
                max="95"
                step="5"
                value={tempFilters.minConfidence}
                onChange={(e) => setTempFilters({ ...tempFilters, minConfidence: parseInt(e.target.value) })}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>50% (Broad)</span>
                <span>75% (Standard)</span>
                <span>95% (High Certainty)</span>
              </div>
            </div>
          </div>

          {/* Status Checkboxes */}
          <div className="space-y-2">
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
              Case Statuses
            </label>
            <div className="flex flex-wrap gap-2">
              {statusOptions.map((st) => {
                const isChecked = tempFilters.statuses.includes(st);
                return (
                  <button
                    key={st}
                    type="button"
                    onClick={() => toggleStatus(st)}
                    className={cn(
                      'px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all',
                      isChecked
                        ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    {st}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Evidence Sources */}
          <div className="space-y-2">
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
              Evidence Attribution
            </label>
            <div className="grid grid-cols-2 gap-2">
              {evidenceOptions.map((ev) => {
                const isChecked = tempFilters.evidenceSources.includes(ev);
                return (
                  <button
                    key={ev}
                    type="button"
                    onClick={() => toggleEvidence(ev)}
                    className={cn(
                      'p-2.5 rounded-xl border text-xs font-medium flex items-center justify-between transition-all',
                      isChecked
                        ? 'bg-indigo-950/60 border-indigo-500 text-white'
                        : 'bg-slate-900/80 border-slate-800 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    <span>{ev}</span>
                    {isChecked && <Check className="w-3.5 h-3.5 text-indigo-400" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Quick Toggles */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <label className="flex items-center justify-between p-3 rounded-xl bg-slate-900/60 border border-slate-800 cursor-pointer hover:bg-slate-900">
              <div>
                <span className="font-semibold text-slate-200 block text-xs">
                  High Impact Opportunities Only (&gt; ₹5,000)
                </span>
                <span className="text-[10px] text-slate-400">
                  Prioritize high-ticket B2B and annual recurring subscriptions
                </span>
              </div>
              <input
                type="checkbox"
                checked={tempFilters.onlyHighImpact}
                onChange={(e) => setTempFilters({ ...tempFilters, onlyHighImpact: e.target.checked })}
                className="w-4 h-4 rounded text-indigo-600 bg-slate-800 border-slate-700 focus:ring-0 cursor-pointer"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-xl bg-slate-900/60 border border-slate-800 cursor-pointer hover:bg-slate-900">
              <div>
                <span className="font-semibold text-slate-200 block text-xs flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  Regulatory Bounds Verified (NPCI & TRAI)
                </span>
                <span className="text-[10px] text-slate-400">
                  Only show actions passing cooldown, frequency budget, and rate limits
                </span>
              </div>
              <input
                type="checkbox"
                checked={tempFilters.regulatoryBoundsVerified}
                onChange={(e) => setTempFilters({ ...tempFilters, regulatoryBoundsVerified: e.target.checked })}
                className="w-4 h-4 rounded text-indigo-600 bg-slate-800 border-slate-700 focus:ring-0 cursor-pointer"
              />
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-[#0B0F19] border-t border-slate-800 flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReset}
            className="text-slate-400 hover:text-white gap-1 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset Defaults
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFiltersModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              Apply Filters
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
