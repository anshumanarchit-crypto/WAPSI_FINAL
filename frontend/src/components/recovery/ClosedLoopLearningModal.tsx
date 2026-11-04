import React from 'react';
import { 
  X, 
  CheckCircle2, 
  RotateCw, 
  ArrowRight, 
  Sparkles, 
  ShieldCheck, 
  Activity,
  Layers,
  Database
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { formatINR } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

export const ClosedLoopLearningModal: React.FC = () => {
  const isLearningModalOpen = useDemoStore((state) => state.isLearningModalOpen);
  const closeLearningModal = useDemoStore((state) => state.closeLearningModal);
  const lastLearningResult = useDemoStore((state) => state.lastLearningResult);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  if (!isLearningModalOpen || !lastLearningResult) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeLearningModal}
          className="fixed inset-0 bg-black/75 backdrop-blur-md"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 15 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 15 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          className={cn(
            "relative w-full max-w-xl rounded-2xl shadow-2xl border overflow-hidden flex flex-col z-10 select-none text-xs",
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
                  <RotateCw className="w-3.5 h-3.5 text-emerald-400" />
                  Closed-Loop Feedback Loop
                </span>
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                  isLight ? "bg-emerald-50 text-emerald-800 border-emerald-300" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                )}>
                  State Persisted
                </span>
              </div>
              <h2 className="text-lg font-black tracking-tight text-white flex items-center gap-2">
                Simulated Outcome & Prior Update
              </h2>
            </div>

            <button
              onClick={closeLearningModal}
              className={cn(
                "p-2 rounded-xl transition-colors cursor-pointer",
                isLight ? "text-slate-400 hover:text-slate-800 hover:bg-slate-200" : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-4">
            {/* Outcome Announcement */}
            <div className={cn(
              "p-4 rounded-xl border text-center space-y-1.5 shadow-sm",
              lastLearningResult.recovered 
                ? isLight ? "bg-emerald-50 border-emerald-300 text-emerald-950" : "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
                : isLight ? "bg-rose-50 border-rose-300 text-rose-950" : "bg-rose-950/40 border-rose-500/40 text-rose-300"
            )}>
              <div className="flex items-center justify-center gap-2 font-black text-sm">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Payment Successfully Recovered: {formatINR(lastLearningResult.amount)}</span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium">
                Executed via <strong>{lastLearningResult.actionLabel}</strong> on case {lastLearningResult.caseId}.
              </p>
            </div>

            {/* Before vs After Bayesian Shift Matrix */}
            <div className={cn(
              "p-4 rounded-xl border space-y-3",
              isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"
            )}>
              <span className="font-bold text-xs text-white block uppercase tracking-wider">
                Bayesian Prior & LinUCB Weight Shift
              </span>

              <div className="grid grid-cols-2 gap-3">
                {/* Before */}
                <div className={cn(
                  "p-3 rounded-lg border space-y-1",
                  isLight ? "bg-white border-slate-200" : "bg-slate-950 border-slate-800"
                )}>
                  <span className="text-[10px] font-bold text-slate-500 uppercase block">Before Outcome</span>
                  <div className="space-y-1 text-[11px] font-mono">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Response Rate:</span>
                      <span className="font-bold text-slate-200">{(lastLearningResult.beforeStats.responseRate * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Attempts:</span>
                      <span className="font-bold text-slate-200">{lastLearningResult.beforeStats.attempts}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Confidence:</span>
                      <span className="font-bold text-slate-200">{Math.round(lastLearningResult.beforeStats.confidence * 100)}%</span>
                    </div>
                  </div>
                </div>

                {/* After */}
                <div className={cn(
                  "p-3 rounded-lg border space-y-1",
                  isLight ? "bg-emerald-50/60 border-emerald-200" : "bg-emerald-950/30 border-emerald-500/40"
                )}>
                  <span className="text-[10px] font-bold text-emerald-400 uppercase block">After Outcome (Learned)</span>
                  <div className="space-y-1 text-[11px] font-mono">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Response Rate:</span>
                      <span className="font-black text-emerald-400">{(lastLearningResult.afterStats.responseRate * 100).toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Attempts:</span>
                      <span className="font-bold text-emerald-300">{lastLearningResult.afterStats.attempts}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Confidence:</span>
                      <span className="font-black text-emerald-300">{Math.round(lastLearningResult.afterStats.confidence * 100)}%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Feedback Loop Explanation */}
              <p className="text-[11px] text-slate-400 leading-relaxed pt-1">
                {lastLearningResult.nextDecisionImpact} The next decision for similar customers will incorporate this higher channel affinity.
              </p>
            </div>

            {/* Audit Chain Entry */}
            <div className={cn(
              "p-3 rounded-lg border font-mono text-[10px] flex items-center justify-between text-slate-400",
              isLight ? "bg-slate-100 border-slate-200" : "bg-slate-950 border-slate-800"
            )}>
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Audit Ledger Block: {lastLearningResult.auditHash}</span>
              </span>
              <span>Enclave Verified</span>
            </div>
          </div>

          {/* Footer */}
          <div className={cn(
            "p-4 border-t flex items-center justify-end",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <Button
              variant="primary"
              size="sm"
              onClick={closeLearningModal}
              className="px-5 font-bold cursor-pointer"
            >
              Continue to Dashboard
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
