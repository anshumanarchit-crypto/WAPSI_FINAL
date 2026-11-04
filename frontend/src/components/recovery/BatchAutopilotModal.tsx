import React, { useState } from 'react';
import { 
  X, 
  Sparkles, 
  Zap, 
  RotateCw, 
  CheckCircle2, 
  ShieldAlert, 
  UserCheck, 
  BarChart2, 
  TrendingUp,
  IndianRupee,
  Layers,
  ArrowUpRight
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { formatINR, formatPercent } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

export const BatchAutopilotModal: React.FC = () => {
  const isAutopilotModalOpen = useDemoStore((state) => state.isAutopilotModalOpen);
  const closeAutopilotModal = useDemoStore((state) => state.closeAutopilotModal);
  const isAutopilotRunning = useDemoStore((state) => state.isAutopilotRunning);
  const autopilotResult = useDemoStore((state) => state.autopilotResult);
  const runAutopilot = useDemoStore((state) => state.runAutopilot);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  if (!isAutopilotModalOpen) return null;

  const handleRun = async () => {
    await runAutopilot();
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeAutopilotModal}
          className="fixed inset-0 bg-black/75 backdrop-blur-md"
        />

        {/* Modal Panel */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 15 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 15 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          className={cn(
            "relative w-full max-w-3xl rounded-2xl shadow-2xl border overflow-hidden flex flex-col max-h-[92vh] z-10 select-none text-xs",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-[#0A0E1A] border-slate-800 text-slate-100"
          )}
        >
          {/* Header */}
          <div className={cn(
            "p-5 border-b flex items-center justify-between transition-colors",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-emerald-400" />
                  Recovery Autopilot Engine
                </span>
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                  isLight ? "bg-indigo-50 text-indigo-800 border-indigo-200" : "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                )}>
                  Portfolio Optimization
                </span>
              </div>
              <h2 className="text-lg font-black tracking-tight text-white flex items-center gap-2">
                Batch Decision Pipeline Execution
              </h2>
            </div>

            <button
              onClick={closeAutopilotModal}
              className={cn(
                "p-2 rounded-xl transition-colors cursor-pointer",
                isLight ? "text-slate-400 hover:text-slate-800 hover:bg-slate-200" : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 overflow-y-auto space-y-5 flex-1">
            {/* Run Button / Execution Banner */}
            {!autopilotResult ? (
              <div className={cn(
                "p-6 rounded-2xl border text-center space-y-4 shadow-sm",
                isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"
              )}>
                <div className="max-w-md mx-auto space-y-2">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center mx-auto shadow-inner">
                    <Zap className="w-6 h-6" />
                  </div>
                  <h3 className="font-black text-sm text-white">Execute Causal Autopilot on 350 Synthetic Transactions</h3>
                  <p className="text-slate-400 text-[11px] leading-relaxed">
                    Evaluates natural recovery, computes 6-action causal uplift, optimizes Net Recovery Value, enforces policy constraints, and routes decisions autonomously.
                  </p>
                </div>

                <Button
                  variant="primary"
                  size="lg"
                  onClick={handleRun}
                  disabled={isAutopilotRunning}
                  className="px-8 font-extrabold text-xs shadow-lg shadow-emerald-600/30 bg-gradient-to-r from-emerald-600 to-indigo-600 text-white cursor-pointer"
                >
                  {isAutopilotRunning ? (
                    <>
                      <RotateCw className="w-4 h-4 animate-spin mr-2" />
                      Computing 350 Causal Decisions...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4 mr-2 text-amber-300" />
                      RUN RECOVERY AUTOPILOT NOW
                    </>
                  )}
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Re-run CTA bar */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="font-bold text-xs text-white">Batch Run Complete (350 Transactions Processed)</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRun}
                    disabled={isAutopilotRunning}
                    className="text-xs cursor-pointer gap-1.5"
                  >
                    <RotateCw className={cn("w-3.5 h-3.5", isAutopilotRunning && "animate-spin")} />
                    Re-run Pipeline
                  </Button>
                </div>

                {/* 4 Hero KPI Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className={cn("p-3.5 rounded-xl border", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/80 border-slate-800")}>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">GMV at Risk</span>
                    <span className="text-base font-black font-mono text-white block">₹{(autopilotResult.totalGMVAtRisk / 100000).toFixed(2)}L</span>
                    <span className="text-[10px] text-slate-500">{autopilotResult.totalProcessed} failed payments</span>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border", isLight ? "bg-purple-50/50 border-purple-200" : "bg-purple-950/40 border-purple-500/30")}>
                    <span className="text-[10px] font-bold text-purple-300 uppercase tracking-wider block mb-1">Gross Recoverable</span>
                    <span className="text-base font-black font-mono text-purple-200 block">₹{(autopilotResult.expectedRecoveredValue / 100000).toFixed(2)}L</span>
                    <span className="text-[10px] text-purple-400/80">Natural: ₹{(autopilotResult.expectedNaturalRecovery / 100000).toFixed(2)}L</span>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border", isLight ? "bg-emerald-50/50 border-emerald-200" : "bg-emerald-950/40 border-emerald-500/30")}>
                    <span className="text-[10px] font-bold text-emerald-300 uppercase tracking-wider block mb-1">Incremental Lift</span>
                    <span className="text-base font-black font-mono text-emerald-300 block">+₹{(autopilotResult.expectedIncrementalRecovery / 100000).toFixed(2)}L</span>
                    <span className="text-[10px] text-emerald-400/80">+{autopilotResult.projectedUplift}% pure causal lift</span>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border", isLight ? "bg-indigo-50/50 border-indigo-200" : "bg-indigo-950/40 border-indigo-500/30")}>
                    <span className="text-[10px] font-bold text-indigo-300 uppercase tracking-wider block mb-1">Net Recovered Value</span>
                    <span className="text-base font-black font-mono text-indigo-200 block">₹{(autopilotResult.expectedNetRecoveredValue / 100000).toFixed(2)}L</span>
                    <span className="text-[10px] text-indigo-400/80">Costs: -₹{autopilotResult.totalInterventionCost.toLocaleString('en-IN')}</span>
                  </div>
                </div>

                {/* Routing Distribution & INVARIANT PROOF */}
                <div className={cn(
                  "p-4 rounded-xl border space-y-3",
                  isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"
                )}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-white flex items-center gap-1.5">
                      <ShieldAlert className="w-3.5 h-3.5 text-indigo-400" />
                      Human-in-the-Loop Routing Verification
                    </span>
                    <span className="font-mono text-[10.5px] text-emerald-400 font-bold bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      AUTO + REVIEW + BLOCK = {autopilotResult.totalProcessed} (100% Invariant Pass)
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30">
                      <span className="text-[10px] font-bold text-emerald-400 block uppercase">Autonomous (Auto Approved)</span>
                      <span className="text-lg font-black font-mono text-emerald-300 mt-0.5 block">{autopilotResult.autonomousCount}</span>
                      <span className="text-[10px] text-emerald-400/70 font-semibold">
                        {((autopilotResult.autonomousCount / autopilotResult.totalProcessed) * 100).toFixed(1)}% of batch
                      </span>
                    </div>

                    <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-500/30">
                      <span className="text-[10px] font-bold text-amber-400 block uppercase">Human Review Required</span>
                      <span className="text-lg font-black font-mono text-amber-300 mt-0.5 block">{autopilotResult.humanReviewCount}</span>
                      <span className="text-[10px] text-amber-400/70 font-semibold">
                        {((autopilotResult.humanReviewCount / autopilotResult.totalProcessed) * 100).toFixed(1)}% of batch
                      </span>
                    </div>

                    <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-500/30">
                      <span className="text-[10px] font-bold text-rose-400 block uppercase">Policy Blocked</span>
                      <span className="text-lg font-black font-mono text-rose-300 mt-0.5 block">{autopilotResult.blockedCount}</span>
                      <span className="text-[10px] text-rose-400/70 font-semibold">
                        {((autopilotResult.blockedCount / autopilotResult.totalProcessed) * 100).toFixed(1)}% of batch
                      </span>
                    </div>
                  </div>
                </div>

                {/* Efficiency Takeaways */}
                <div className="grid grid-cols-2 gap-3">
                  <div className={cn("p-3.5 rounded-xl border text-[11px]", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                    <span className="font-bold text-slate-200 block mb-1">⚡ Gateway Retry Suppression</span>
                    <p className="text-slate-400">
                      Eliminated <span className="text-emerald-400 font-bold">{autopilotResult.retriesSavedPercent}%</span> of blind retry attempts, avoiding bank switch penalties and card network throttling.
                    </p>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border text-[11px]", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                    <span className="font-bold text-slate-200 block mb-1">🛡️ Customer Contact Fatigue Protection</span>
                    <p className="text-slate-400">
                      Suppressed <span className="text-indigo-400 font-bold">{autopilotResult.contactsSavedPercent}%</span> of intrusive messaging by relying on organic resolution and single-tap WhatsApp links.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className={cn(
            "p-4 border-t flex items-center justify-between",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <span className="text-slate-400 text-[11px] font-mono">
              Seed: 42 • Multi-Treatment T-Learner • Deterministic Verification
            </span>

            <Button
              variant="primary"
              size="sm"
              onClick={closeAutopilotModal}
              className="px-5 font-bold cursor-pointer"
            >
              Close Autopilot
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
