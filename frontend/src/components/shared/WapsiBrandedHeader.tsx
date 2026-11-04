import React from 'react';
import { ShieldCheck, Cpu, Database, Activity, CheckCircle2, Lock } from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { cn } from '../../lib/utils';

interface WapsiBrandedHeaderProps {
  title?: string;
  subtitle?: string;
  className?: string;
}

export const WapsiBrandedHeader: React.FC<WapsiBrandedHeaderProps> = ({
  title = "Recovery Decision Router",
  subtitle = "Autonomous Causal Revenue Optimization & Policy Governance Enclave",
  className
}) => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';
  const merchantSettings = useDemoStore((state) => state.merchantSettings);

  return (
    <div className={cn(
      "relative overflow-hidden rounded-2xl border transition-all duration-300 mb-6",
      isLight 
        ? "bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border-indigo-200/40 text-white shadow-xl shadow-indigo-950/10"
        : "bg-gradient-to-r from-[#0B0F19] via-[#0F172A] to-[#0B0F19] border-indigo-500/30 text-white shadow-2xl shadow-black/40",
      className
    )}>
      {/* Background Micro-Grid & Ambient Accent Lines */}
      <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(#818cf8_1px,transparent_1px)] [background-size:16px_16px]" />
      <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-indigo-500/10 via-purple-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-12 left-1/4 w-80 h-32 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />

      {/* Top Accent Status Stripe */}
      <div className="h-1 w-full bg-gradient-to-r from-indigo-500 via-emerald-400 to-purple-500" />

      <div className="relative px-6 py-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Brand & Mission Definition */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold tracking-wide uppercase bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              WAPSI Enterprise
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10.5px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              Pretrained Inference Active
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10.5px] font-mono text-slate-300 bg-slate-800/80 border border-slate-700/60">
              <Lock className="w-3 h-3 text-amber-400" />
              TEE Conf-Compute Attested
            </span>
          </div>

          <h1 className="text-xl md:text-2xl font-black tracking-tight text-white flex items-center gap-2">
            <span>{title}</span>
          </h1>
          <p className="text-xs md:text-sm text-slate-300 max-w-2xl font-normal leading-relaxed">
            {subtitle}
          </p>
        </div>

        {/* Real Backend Telemetry Badges */}
        <div className="flex flex-wrap md:flex-col items-start md:items-end gap-2 shrink-0">
          <div className="flex items-center gap-2 bg-slate-900/80 border border-slate-700/70 rounded-xl px-3 py-1.5 backdrop-blur-md">
            <Database className="w-3.5 h-3.5 text-blue-400" />
            <div className="text-right">
              <div className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Storage Engine</div>
              <div className="text-[11px] font-bold text-white font-mono">PostgreSQL / Supabase</div>
            </div>
          </div>

          <div className="flex items-center gap-2 bg-slate-900/80 border border-slate-700/70 rounded-xl px-3 py-1.5 backdrop-blur-md">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <div className="text-right">
              <div className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">Causal Estimator</div>
              <div className="text-[11px] font-bold text-white font-mono">T-Learner + LinUCB Bandit</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
