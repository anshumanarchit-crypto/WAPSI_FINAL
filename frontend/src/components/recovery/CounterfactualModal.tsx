import React, { useState } from 'react';
import { 
  X, 
  HelpCircle, 
  TrendingUp, 
  IndianRupee, 
  ShieldCheck, 
  AlertCircle, 
  ArrowRight,
  Sliders,
  CheckCircle2,
  Sparkles,
  RefreshCw,
  Coins
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { formatINR, formatPercent } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { ActionType } from '../../types';

export const CounterfactualModal: React.FC = () => {
  const isCounterfactualModalOpen = useDemoStore((state) => state.isCounterfactualModalOpen);
  const closeCounterfactualModal = useDemoStore((state) => state.closeCounterfactualModal);
  const selectedCaseId = useDemoStore((state) => state.selectedCaseId) || 'RX-48291';
  const caseDetails = useDemoStore((state) => state.caseDetails);
  const rawTransactions = useDemoStore((state) => state.rawTransactions);
  const updateTransactionAmount = useDemoStore((state) => state.updateTransactionAmount);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const currentTx = rawTransactions[selectedCaseId] || rawTransactions['RX-48291'];
  const detail = caseDetails[selectedCaseId] || caseDetails['RX-48291'];

  const [testAmount, setTestAmount] = useState<number>(currentTx?.amount || 8999);

  if (!isCounterfactualModalOpen || !detail || !currentTx) return null;

  const handleAmountChange = (newAmount: number) => {
    setTestAmount(newAmount);
    updateTransactionAmount(selectedCaseId, newAmount);
  };

  const selectedScore = detail.selectedActionScore || detail.actionScores[0];

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeCounterfactualModal}
          className="fixed inset-0 bg-black/75 backdrop-blur-md"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 15 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 15 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          className={cn(
            "relative w-full max-w-4xl rounded-2xl shadow-2xl border overflow-hidden flex flex-col max-h-[90vh] z-10 select-none text-xs",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-[#090D18] border-slate-800 text-slate-100"
          )}
        >
          {/* Header */}
          <div className={cn(
            "p-5 border-b flex items-center justify-between transition-colors",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Counterfactual &quot;What If?&quot; Engine
                </span>
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                  isLight ? "bg-emerald-50 text-emerald-800 border-emerald-300" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                )}>
                  Single Source of Truth
                </span>
              </div>
              <h2 className="text-lg font-black tracking-tight text-white flex items-center gap-2">
                Simulating All 6 Actions for {currentTx.transaction_id}
                <span className="text-slate-400 text-xs font-normal">({currentTx.customer_name})</span>
              </h2>
            </div>

            <button
              onClick={closeCounterfactualModal}
              className={cn(
                "p-2 rounded-xl transition-colors cursor-pointer",
                isLight ? "text-slate-400 hover:text-slate-800 hover:bg-slate-200" : "text-slate-400 hover:text-white hover:bg-slate-800"
              )}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Interactive Sensitivity Bar */}
          <div className={cn(
            "px-6 py-3 border-b flex flex-wrap items-center justify-between gap-4",
            isLight ? "bg-indigo-50/50 border-indigo-100" : "bg-indigo-950/20 border-slate-800/80"
          )}>
            <div className="flex items-center gap-3">
              <span className="font-bold text-xs flex items-center gap-1.5 text-slate-300">
                <Sliders className="w-3.5 h-3.5 text-indigo-400" />
                Live Sensitivity Test:
              </span>
              <span className="text-[11px] text-slate-400">Transaction Value:</span>
              <div className="flex items-center gap-1.5">
                {[1999, 4999, 8999, 15000].map((amt) => (
                  <button
                    key={amt}
                    onClick={() => handleAmountChange(amt)}
                    className={cn(
                      "px-2.5 py-1 rounded-lg font-mono text-[11px] font-bold border transition-all cursor-pointer",
                      testAmount === amt
                        ? "bg-indigo-600 border-indigo-400 text-white shadow-md shadow-indigo-600/30"
                        : isLight ? "bg-white border-slate-200 text-slate-700 hover:border-indigo-400" : "bg-slate-900 border-slate-700 text-slate-300 hover:border-indigo-500/50"
                    )}
                  >
                    ₹{amt.toLocaleString('en-IN')}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3 text-right">
              <span className="text-[11px] text-slate-400">Natural Organic Recovery (P₀):</span>
              <span className="font-mono font-black text-sm text-indigo-300">
                {Math.round(detail.naturalRecoveryProbability * 100)}%
              </span>
            </div>
          </div>

          {/* Content Body: Action Comparison Matrix */}
          <div className="p-6 overflow-y-auto space-y-4 flex-1">
            {/* The Core Truth Banner */}
            <div className={cn(
              "p-3.5 rounded-xl border flex items-start gap-3",
              isLight ? "bg-amber-50/80 border-amber-200 text-amber-900" : "bg-amber-950/30 border-amber-500/30 text-amber-200"
            )}>
              <Coins className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div className="text-[11px] leading-relaxed">
                <span className="font-bold">Core Causal Story: </span>
                <span>
                  WAPSI does <span className="font-bold underline">not</span> blindly choose the action with highest recovery probability. 
                  Although <strong>Incentive Offer</strong> yields {Math.round((detail.actionScores.find(s => s.action === 'INCENTIVE')?.recoveryProbability || 0.88) * 100)}% probability, 
                  its discount cost erodes net margin. WAPSI selects <strong>{selectedScore.label}</strong> because it maximizes 
                  <strong> Expected Net Recovery Value (₹{(selectedScore.expectedNetRecoveryValue ?? (selectedScore.recoveryProbability * currentTx.amount - (selectedScore.totalCost || 0))).toLocaleString('en-IN')})</strong>.
                </span>
              </div>
            </div>

            {/* Matrix Table */}
            <div className={cn(
              "rounded-xl border overflow-hidden shadow-sm",
              isLight ? "border-slate-200 bg-white" : "border-slate-800 bg-slate-900/60"
            )}>
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className={cn(
                    "border-b font-mono text-[10.5px] uppercase tracking-wider",
                    isLight ? "bg-slate-100 text-slate-600 border-slate-200" : "bg-slate-950/80 text-slate-400 border-slate-800"
                  )}>
                    <th className="py-3 px-4">Action Channel</th>
                    <th className="py-3 px-3 text-right">Recovery Prob (Pt)</th>
                    <th className="py-3 px-3 text-right">Causal Uplift (τ)</th>
                    <th className="py-3 px-3 text-right">Gross Expected Value</th>
                    <th className="py-3 px-3 text-right">Cost Breakdown</th>
                    <th className="py-3 px-4 text-right">Expected Net Value</th>
                    <th className="py-3 px-4 text-center">Decision Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {detail.actionScores.map((score) => {
                    const isSelected = score.action === detail.bestAction;
                    const grossVal = score.grossRecoveredValue ?? Math.round(score.recoveryProbability * currentTx.amount);
                    const costVal = (score.totalCost ?? 0) + (score.riskPenalty ?? 0);
                    const incentiveCostVal = score.incentiveCost ?? 0;
                    const riskPenaltyVal = score.riskPenalty ?? 0;
                    const netVal = score.expectedNetRecoveryValue ?? (grossVal - costVal);

                    return (
                      <tr 
                        key={score.action}
                        className={cn(
                          "transition-colors",
                          isSelected
                            ? isLight ? "bg-indigo-50/80 font-bold" : "bg-indigo-950/40 font-bold"
                            : isLight ? "hover:bg-slate-50" : "hover:bg-slate-800/40"
                        )}
                      >
                        {/* Channel Name */}
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            {isSelected && <Sparkles className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                            <div>
                              <span className={cn(
                                "text-xs font-bold block",
                                isSelected ? (isLight ? "text-indigo-900" : "text-white") : (isLight ? "text-slate-800" : "text-slate-300")
                              )}>
                                {score.label}
                              </span>
                              <span className="text-[10px] text-slate-500 font-normal">
                                {score.action === 'NO_ACTION' ? 'Holdout Baseline' : score.action}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* Recovery Probability */}
                        <td className="py-3.5 px-3 text-right font-mono font-bold text-xs">
                          <span className={cn(
                            score.recoveryProbability >= 0.85 ? "text-emerald-400 font-black" : isLight ? "text-slate-800" : "text-slate-300"
                          )}>
                            {Math.round(score.recoveryProbability * 100)}%
                          </span>
                        </td>

                        {/* Causal Uplift */}
                        <td className="py-3.5 px-3 text-right font-mono font-bold text-xs">
                          {score.action === 'NO_ACTION' ? (
                            <span className="text-slate-500">—</span>
                          ) : (
                            <span className="text-emerald-400">
                              +{Math.round(score.incrementalUplift * 100)}%
                            </span>
                          )}
                        </td>

                        {/* Gross Expected Value */}
                        <td className="py-3.5 px-3 text-right font-mono text-xs">
                          <span className={isLight ? "text-slate-700" : "text-slate-300"}>
                            ₹{grossVal.toLocaleString('en-IN')}
                          </span>
                        </td>

                        {/* Cost Breakdown */}
                        <td className="py-3.5 px-3 text-right font-mono text-xs">
                          {costVal === 0 ? (
                            <span className="text-slate-500">₹0</span>
                          ) : (
                            <div className="text-[10.5px]">
                              <span className="text-rose-400 font-semibold">
                                -₹{costVal.toFixed(0)}
                              </span>
                              {incentiveCostVal > 0 && (
                                <span className="block text-[9.5px] text-amber-400/80">
                                  (₹{incentiveCostVal.toFixed(0)} discount)
                                </span>
                              )}
                              {riskPenaltyVal > 0 && (
                                <span className="block text-[9.5px] text-rose-400/80">
                                  (₹{riskPenaltyVal.toFixed(0)} fatigue)
                                </span>
                              )}
                            </div>
                          )}
                        </td>

                        {/* Expected Net Value */}
                        <td className="py-3.5 px-4 text-right font-mono">
                          <span className={cn(
                            "text-sm font-black",
                            isSelected 
                              ? "text-emerald-400 text-base underline decoration-emerald-500 decoration-2" 
                              : isLight ? "text-slate-800" : "text-slate-200"
                          )}>
                            ₹{netVal.toLocaleString('en-IN')}
                          </span>
                        </td>

                        {/* Decision Status */}
                        <td className="py-3.5 px-4 text-center">
                          {isSelected ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20">
                              <CheckCircle2 className="w-3 h-3" />
                              SELECTED
                            </span>
                          ) : score.action === 'INCENTIVE' ? (
                            <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                              Margin Loss
                            </span>
                          ) : score.action === 'VOICE' ? (
                            <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                              Cost Erode
                            </span>
                          ) : score.action === 'NO_ACTION' ? (
                            <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-500/10 text-slate-400 border border-slate-700">
                              Holdout
                            </span>
                          ) : (
                            <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400">
                              Sub-optimal
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Why Alternatives Were Rejected Section */}
            <div className="space-y-2 pt-2">
              <h3 className="font-bold text-xs text-slate-300 uppercase tracking-wider">
                Why WAPSI Rejected The Alternatives
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {detail.rejectedAlternatives?.map((alt) => (
                  <div 
                    key={alt.action}
                    className={cn(
                      "p-3 rounded-xl border text-[11px] leading-relaxed",
                      isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/40 border-slate-800/80"
                    )}
                  >
                    <div className="flex items-center justify-between font-bold mb-1">
                      <span className={isLight ? "text-slate-800" : "text-slate-200"}>{alt.label}</span>
                      <span className="text-slate-500 font-mono">{Math.round(alt.recoveryProbability * 100)}% Prob</span>
                    </div>
                    <p className="text-slate-400">{alt.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className={cn(
            "p-4 border-t flex items-center justify-between",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <div className="flex items-center gap-2 text-slate-400 text-[11px]">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Conformal Confidence: {Math.round(detail.confidence * 100)}% (95% Coverage)</span>
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={closeCounterfactualModal}
              className="px-5 font-bold cursor-pointer"
            >
              Close What-If Analysis
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
