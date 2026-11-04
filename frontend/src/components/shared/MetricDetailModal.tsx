import React from 'react';
import { Button } from '../ui/Button';
import { 
  X, 
  TrendingUp, 
  ShieldCheck, 
  BrainCircuit, 
  HelpCircle, 
  CheckCircle2, 
  ArrowUpRight,
  DollarSign
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export interface MetricDetailData {
  title: string;
  value: string;
  delta: string;
  deltaType: 'positive' | 'warning' | 'info';
  accentColor: 'rose' | 'amber' | 'emerald' | 'purple' | 'cyan';
  significance: string;
  causalMethod: string;
  businessImpact: string;
  breakdown: { label: string; value: string; share: string }[];
}

interface MetricDetailModalProps {
  data: MetricDetailData | null;
  onClose: () => void;
}

export const MetricDetailModal: React.FC<MetricDetailModalProps> = ({ data, onClose }) => {
  if (!data) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.2 }}
          className="relative w-full max-w-xl rounded-3xl bg-[#0B111E]/90 border border-slate-700/80 shadow-2xl p-6 space-y-5 overflow-hidden backdrop-blur-xl text-slate-100"
        >
          {/* Ambient Glow */}
          <div className="absolute -right-20 -top-20 w-64 h-64 bg-indigo-500/20 blur-3xl pointer-events-none" />

          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase font-bold tracking-widest text-indigo-400">
                  METRIC INTELLIGENCE & CAUSAL SIGNIFICANCE
                </span>
              </div>
              <h2 className="text-xl font-black text-white">{data.title}</h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Large Metric Display Banner */}
          <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs text-slate-400 block font-medium">Current Value (30-Day Window)</span>
              <span className="text-3xl font-black text-white tabular-nums tracking-tight">{data.value}</span>
            </div>
            <div className="text-right">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                <ArrowUpRight className="w-3.5 h-3.5" />
                {data.delta}
              </span>
              <span className="text-[10px] text-slate-400 block mt-1">vs counterfactual baseline</span>
            </div>
          </div>

          {/* Significance in Plain Words */}
          <div className="space-y-3 text-xs">
            <div className="p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-500/20 space-y-1">
              <span className="font-bold text-indigo-200 flex items-center gap-1.5">
                <HelpCircle className="w-3.5 h-3.5 text-indigo-400" />
                What does this mean in simple words?
              </span>
              <p className="text-slate-300 leading-relaxed pl-5 text-[11px]">{data.significance}</p>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
              <span className="font-bold text-slate-200 flex items-center gap-1.5">
                <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
                How WAPSI calculates this using Causal AI:
              </span>
              <p className="text-slate-400 leading-relaxed pl-5 text-[11px]">{data.causalMethod}</p>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
              <span className="font-bold text-slate-200 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Strategic business impact:
              </span>
              <p className="text-slate-400 leading-relaxed pl-5 text-[11px]">{data.businessImpact}</p>
            </div>
          </div>

          {/* Domain Breakdown Table */}
          <div className="space-y-2 pt-1">
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block">
              Contribution by Product Domain
            </span>
            <div className="grid grid-cols-3 gap-2">
              {data.breakdown.map((item, idx) => (
                <div key={idx} className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-center">
                  <span className="text-[10px] text-slate-400 block">{item.label}</span>
                  <span className="text-sm font-bold text-white block mt-0.5">{item.value}</span>
                  <span className="text-[9px] text-indigo-400 font-semibold">{item.share}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end pt-3 border-t border-slate-800">
            <Button variant="primary" size="sm" onClick={onClose}>
              Close Intelligence
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
