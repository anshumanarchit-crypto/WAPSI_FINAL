import React, { useState } from 'react';
import { 
  X, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  Clock, 
  TrendingUp, 
  BarChart2, 
  Layers, 
  Sparkles, 
  Zap, 
  RotateCw, 
  MessageSquare, 
  History,
  Copy,
  Check,
  Building2,
  Lock,
  ArrowUpRight,
  ExternalLink,
  ChevronRight,
  UserCheck,
  Link as LinkIcon,
  Send
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { useCaseDetail } from '../../hooks/useRecovery';
import { recoveryService } from '../../services/recoveryService';
import { Button } from '../ui/Button';
import { StatusBadge } from '../shared/StatusBadge';
import { formatINR, formatPercent } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { OperatorApprovalModal } from './OperatorApprovalModal';
import { motion, AnimatePresence } from 'framer-motion';

export const CaseDrawer: React.FC = () => {
  const isCaseDrawerOpen = useDemoStore((state) => state.isCaseDrawerOpen);
  const closeCaseDrawer = useDemoStore((state) => state.closeCaseDrawer);
  const selectedCaseId = useDemoStore((state) => state.selectedCaseId);
  const cases = useDemoStore((state) => state.cases);
  const caseDetails = useDemoStore((state) => state.caseDetails);
  const theme = useDemoStore((state) => state.theme);
  
  const approveCase = useDemoStore((state) => state.approveCase);
  const reviewCase = useDemoStore((state) => state.reviewCase);
  const rejectCase = useDemoStore((state) => state.rejectCase);
  const simulateRecovery = useDemoStore((state) => state.simulateRecovery);
  const isPolicyCheckRunning = useDemoStore((state) => state.isPolicyCheckRunning);
  const policyCheckProgress = useDemoStore((state) => state.policyCheckProgress);
  const openCounterfactualModal = useDemoStore((state) => state.openCounterfactualModal);
  const openLearningModal = useDemoStore((state) => state.openLearningModal);

  const [copied, setCopied] = useState(false);
  const [selectedActionPreview, setSelectedActionPreview] = useState<string | null>(null);
  const [isApprovalModalOpen, setIsApprovalModalOpen] = useState(false);
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);
  const [isDispatchingWa, setIsDispatchingWa] = useState(false);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [recipientPhone, setRecipientPhone] = useState<string>('+916260055671');
  const [dispatchErrorDetail, setDispatchErrorDetail] = useState<string | null>(null);
  const [customToken, setCustomToken] = useState<string>('');
  const [showTokenInput, setShowTokenInput] = useState<boolean>(false);

  // Unconditional hook call according to React Rules of Hooks
  const { data: liveDetail } = useCaseDetail(isCaseDrawerOpen && selectedCaseId ? selectedCaseId : null);

  if (!isCaseDrawerOpen || !selectedCaseId) return null;

  const currentCase = cases.find((c) => c.caseId === selectedCaseId) || cases[0];
  const detail = liveDetail || caseDetails[selectedCaseId] || caseDetails['RX-48291'];

  const handleCopyId = () => {
    navigator.clipboard.writeText(currentCase.caseId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyLink = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handleGenerateLink = async () => {
    setIsGeneratingLink(true);
    setActionSuccessMessage(null);
    try {
      const res = await recoveryService.createPaymentLink(currentCase.caseId);
      if (res) {
        setActionSuccessMessage(`Payment Link generated: ${res.payment_link_id}`);
        setTimeout(() => setActionSuccessMessage(null), 4000);
      }
    } finally {
      setIsGeneratingLink(false);
    }
  };

  const handleDispatchWhatsApp = async () => {
    setIsDispatchingWa(true);
    setActionSuccessMessage(null);
    setDispatchErrorDetail(null);
    try {
      const res = await recoveryService.dispatchWhatsApp(
        currentCase.caseId,
        undefined,
        recipientPhone,
        customToken.trim() || undefined
      );
      if (res) {
        if (res.is_live_dispatched) {
          setActionSuccessMessage(`WhatsApp sent LIVE to ${res.recipient_phone}! Message ID: ${res.whatsapp_message_id}`);
        } else if (res.provider_error) {
          setActionSuccessMessage(`WhatsApp recorded (ID: ${res.whatsapp_message_id})`);
          setDispatchErrorDetail(res.provider_error);
        } else {
          setActionSuccessMessage(`WhatsApp reminder dispatched: ${res.whatsapp_message_id}`);
        }
        setTimeout(() => setActionSuccessMessage(null), 8000);
      }
    } finally {
      setIsDispatchingWa(false);
    }
  };

  const isLight = theme === 'light';

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Dimmed Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={closeCaseDrawer}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
      />

      {/* Main Drawer Panel */}
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 280 }}
        className={cn(
          "relative w-full max-w-[560px] shadow-2xl z-50 flex flex-col h-full overflow-hidden text-xs select-none transition-colors border-l",
          isLight
            ? "bg-white border-slate-200 text-slate-900"
            : "bg-[#080D1A] border-slate-800/90 text-slate-100"
        )}
      >
        {/* Drawer Header */}
        <div className={cn(
          "p-5 border-b flex items-start justify-between relative overflow-hidden transition-colors",
          isLight ? "bg-slate-50 border-slate-200" : "bg-[#0B0F19] border-slate-800/80"
        )}>
          {/* Subtle Ambient Background Aura */}
          <div className="absolute top-0 right-0 w-48 h-48 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />

          <div className="space-y-1.5 min-w-0 flex-1 pr-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn(
                "text-[11px] font-bold uppercase tracking-wider",
                isLight ? "text-slate-500" : "text-slate-400"
              )}>
                Recovery Intelligence
              </span>
              <StatusBadge status={currentCase.status} />
              {currentCase.isOOD && (
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                  isLight
                    ? "bg-purple-50 text-purple-700 border-purple-300"
                    : "bg-purple-500/20 text-purple-300 border-purple-500/40"
                )}>
                  OOD Prior
                </span>
              )}
              <span className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
                isLight 
                  ? "bg-slate-100 text-slate-700 border-slate-300" 
                  : "bg-slate-800 text-slate-300 border-slate-700"
              )}>
                {currentCase.domain}
              </span>
            </div>

            <div className="flex items-baseline justify-between pt-1">
              <div className="flex items-center gap-2">
                <h2 className={cn(
                  "text-xl font-black font-mono tracking-tight",
                  isLight ? "text-slate-900" : "text-white"
                )}>
                  {currentCase.caseId}
                </h2>
                <button
                  onClick={handleCopyId}
                  className={cn(
                    "p-1 rounded-md transition-colors cursor-pointer",
                    isLight ? "text-slate-400 hover:text-slate-800 hover:bg-slate-200" : "text-slate-400 hover:text-white hover:bg-slate-800"
                  )}
                  title="Copy Case ID"
                >
                  {copied ? (
                    <span className="text-[10px] text-emerald-600 font-bold flex items-center gap-0.5">
                      <Check className="w-3 h-3" /> Copied!
                    </span>
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>

              <div className="text-right">
                <span className={cn(
                  "text-lg font-black tabular-nums block",
                  isLight ? "text-emerald-700 font-black" : "text-emerald-400"
                )}>
                  {formatINR(currentCase.amount)}
                </span>
              </div>
            </div>

            <div className={cn(
              "flex items-center justify-between text-[11px] pt-0.5",
              isLight ? "text-slate-600 font-medium" : "text-slate-400"
            )}>
              <span>{currentCase.customerName} ({currentCase.customerHandle})</span>
              <span className={cn(
                "font-bold px-2 py-0.5 rounded border",
                isLight
                  ? "bg-rose-50 text-rose-700 border-rose-200"
                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
              )}>
                {currentCase.failureReason}
              </span>
            </div>
          </div>

          <button
            onClick={closeCaseDrawer}
            className={cn(
              "p-2 rounded-xl border transition-all shrink-0 cursor-pointer",
              isLight
                ? "bg-white border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-100 shadow-sm"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
            )}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable Intelligence Body */}
        <div className={cn("flex-1 overflow-y-auto p-5 space-y-4", isLight ? "bg-slate-50/50" : "")}>
          {/* AI Recommendation Hero Card */}
          <div className={cn(
            "p-4 rounded-2xl border shadow-xl space-y-3.5 relative overflow-hidden transition-colors",
            isLight
              ? "bg-gradient-to-br from-indigo-50/95 via-purple-50/90 to-indigo-100/90 border-indigo-200 text-slate-900 shadow-indigo-100/60"
              : "bg-gradient-to-br from-indigo-950/80 via-[#0B1120] to-purple-950/60 border-indigo-500/40 shadow-indigo-950/30"
          )}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={cn(
                  "p-1.5 rounded-lg border shadow-inner",
                  isLight
                    ? "bg-indigo-100 text-indigo-700 border-indigo-200"
                    : "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                )}>
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <span className={cn(
                    "font-extrabold text-xs uppercase tracking-wider block",
                    isLight ? "text-indigo-950" : "text-white"
                  )}>
                    AI Causal Recommendation
                  </span>
                  <span className={cn("text-[10px]", isLight ? "text-indigo-800 font-medium" : "text-indigo-300")}>
                    Optimal treatment with maximum expected lift
                  </span>
                </div>
              </div>
              <span className={cn(
                "text-[10px] font-bold px-2.5 py-1 rounded-lg border shadow-sm",
                isLight
                  ? "bg-indigo-100 text-indigo-800 border-indigo-300"
                  : "bg-indigo-900/80 text-indigo-200 border-indigo-500/40"
              )}>
                {currentCase.optimalWindow}
              </span>
            </div>

            <div className={cn(
              "grid grid-cols-2 gap-3 p-3 rounded-xl border",
              isLight
                ? "bg-white border-indigo-100 shadow-sm"
                : "bg-slate-950/80 border-indigo-500/20"
            )}>
              <div>
                <span className={cn(
                  "text-[10px] uppercase font-bold tracking-wider block mb-0.5",
                  isLight ? "text-slate-500" : "text-slate-400"
                )}>
                  Prescribed Treatment
                </span>
                <div className={cn(
                  "text-base font-extrabold flex items-center gap-1.5",
                  isLight ? "text-slate-900" : "text-white"
                )}>
                  <span>{currentCase.recommendedActionLabel}</span>
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                </div>
              </div>
              <div className="text-right">
                <span className={cn(
                  "text-[10px] uppercase font-bold tracking-wider block mb-0.5",
                  isLight ? "text-slate-500" : "text-slate-400"
                )}>
                  Optimal Timing Window
                </span>
                <div className={cn(
                  "text-xs font-bold flex items-center justify-end gap-1",
                  isLight ? "text-indigo-700" : "text-indigo-300"
                )}>
                  <Clock className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />
                  <span>{currentCase.recommendedTime}</span>
                </div>
              </div>
            </div>

            {/* 4 Causal Uplift Metrics Grid */}
            <div className="grid grid-cols-4 gap-2 text-center pt-1">
              <div className={cn(
                "p-2.5 rounded-xl border shadow-sm",
                isLight ? "bg-white border-slate-200" : "bg-slate-900/90 border-slate-800"
              )}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-slate-500" : "text-slate-400")}>No Action (P₀)</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-slate-900" : "text-slate-300")}>
                  {Math.round(currentCase.naturalRecoveryProbability * 100)}%
                </span>
                <span className={cn("text-[8.5px]", isLight ? "text-slate-500 font-medium" : "text-slate-500")}>Natural rate</span>
              </div>
              <div className={cn(
                "p-2.5 rounded-xl border shadow-sm",
                isLight ? "bg-purple-50 border-purple-200" : "bg-indigo-950/60 border-indigo-500/30"
              )}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-purple-800" : "text-indigo-300")}>With Action (Pt)</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-purple-900 font-black" : "text-indigo-200")}>
                  {Math.round(currentCase.treatmentProbability * 100)}%
                </span>
                <span className={cn("text-[8.5px] font-semibold", isLight ? "text-purple-700" : "text-indigo-400/80")}>With WAPSI</span>
              </div>
              <div className={cn(
                "p-2.5 rounded-xl border shadow-sm",
                isLight ? "bg-emerald-50 border-emerald-200" : "bg-emerald-950/60 border-emerald-500/40"
              )}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-emerald-800" : "text-emerald-400")}>Inc. Uplift (τ)</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-emerald-800 font-black" : "text-emerald-300")}>
                  {formatPercent(currentCase.incrementalUplift * 100)}
                </span>
                <span className={cn("text-[8.5px] font-semibold", isLight ? "text-emerald-700" : "text-emerald-400/80")}>Pure lift</span>
              </div>
              <div className={cn(
                "p-2.5 rounded-xl border shadow-sm",
                isLight ? "bg-white border-slate-200" : "bg-slate-900/90 border-slate-800"
              )}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-slate-500" : "text-slate-400")}>Confidence</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-slate-900" : "text-white")}>
                  {Math.round(currentCase.decisionConfidence * 100)}%
                </span>
                <span className={cn("text-[8.5px]", isLight ? "text-slate-500 font-medium" : "text-slate-500")}>Conformal</span>
              </div>
            </div>
          </div>

          {/* Expected Net Recovery Value & Unit Economics */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md relative overflow-hidden",
            isLight
              ? "bg-white border-emerald-200 text-slate-900"
              : "bg-emerald-950/20 border-emerald-500/30 text-slate-100"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-emerald-700" : "text-emerald-400")}>
                <Sparkles className="w-3.5 h-3.5" />
                Expected Net Recovery Value (Decision Objective)
              </span>
              <span className={cn(
                "text-[10px] font-bold px-2 py-0.5 rounded border",
                isLight ? "bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
              )}>
                ArgMax Net Value
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div className={cn("p-2.5 rounded-xl border", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-slate-500" : "text-slate-400")}>Gross Expected</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-slate-900" : "text-slate-200")}>
                  {formatINR(currentCase.expectedRecoveredValue || Math.round(currentCase.amount * currentCase.treatmentProbability))}
                </span>
                <span className="text-[8.5px] text-slate-500 font-mono">P(t) × Amount</span>
              </div>

              <div className={cn("p-2.5 rounded-xl border", isLight ? "bg-rose-50 border-rose-200" : "bg-rose-950/30 border-rose-500/30")}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-rose-700" : "text-rose-300")}>Total Cost</span>
                <span className="text-sm font-black tabular-nums block mt-0.5 text-rose-500">
                  -{formatINR(currentCase.interventionCost || 6)}
                </span>
                <span className="text-[8.5px] text-rose-500/80 font-mono">Fees + Risk</span>
              </div>

              <div className={cn("p-2.5 rounded-xl border", isLight ? "bg-emerald-50 border-emerald-300" : "bg-emerald-900/40 border-emerald-500/50")}>
                <span className={cn("text-[9px] block font-bold uppercase", isLight ? "text-emerald-800" : "text-emerald-300")}>Expected Net</span>
                <span className={cn("text-sm font-black tabular-nums block mt-0.5", isLight ? "text-emerald-700" : "text-emerald-400")}>
                  {formatINR(currentCase.expectedNetRecoveryValue || (Math.round(currentCase.amount * currentCase.treatmentProbability) - (currentCase.interventionCost || 6)))}
                </span>
                <span className="text-[8.5px] text-emerald-600 dark:text-emerald-400 font-mono">Gross - Cost</span>
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              className={cn(
                "w-full flex items-center justify-center gap-2 py-2 rounded-xl font-bold text-xs border transition-all shadow-sm cursor-pointer",
                isLight
                  ? "bg-purple-50 hover:bg-purple-100 text-purple-900 border-purple-300"
                  : "bg-purple-950/40 hover:bg-purple-900/60 text-purple-200 border-purple-500/40"
              )}
              onClick={() => openCounterfactualModal(currentCase.caseId)}
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Simulate Counterfactual "What If?" Treatments</span>
              <ArrowUpRight className="w-3.5 h-3.5 ml-auto opacity-70" />
            </Button>
          </div>

          {/* Action Comparison Bars */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-slate-900/80 border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <BarChart2 className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />
                Action Comparison Matrix (vs No Action)
              </span>
              <span className={cn("text-[10px]", isLight ? "text-slate-500" : "text-slate-400")}>Recovery Prob | Net Value</span>
            </div>

            <div className="space-y-2.5">
              {detail.actionScores.map((score) => {
                const isBest = score.action === detail.bestAction;
                const netVal = score.expectedNetRecoveryValue ?? score.estimatedValue ?? Math.round(score.recoveryProbability * currentCase.amount - (score.totalCost || 0));
                return (
                  <div 
                    key={score.action} 
                    className={cn(
                      'p-2.5 rounded-xl transition-all border',
                      isLight
                        ? isBest ? 'bg-indigo-50/80 border-indigo-200' : 'bg-slate-50 border-slate-100 hover:border-slate-200'
                        : isBest ? 'bg-indigo-950/40 border-indigo-500/30' : 'bg-slate-950/40 border-transparent hover:border-slate-800'
                    )}
                  >
                    <div className="flex items-center justify-between text-[11px] mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className={cn('font-semibold', isLight ? (isBest ? 'text-indigo-950 font-bold' : 'text-slate-700') : (isBest ? 'text-white font-bold' : 'text-slate-300'))}>
                          {score.label}
                        </span>
                        {isBest && (
                          <span className={cn(
                            "text-[9px] font-bold px-1.5 py-0.2 rounded border",
                            isLight
                              ? "bg-indigo-100 text-indigo-800 border-indigo-300"
                              : "bg-indigo-500/30 text-indigo-200 border-indigo-400/30"
                          )}>
                            ★ OPTIMAL NET VALUE
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={cn("tabular-nums font-bold", isLight ? "text-slate-900" : "text-slate-300")}>
                          {Math.round(score.recoveryProbability * 100)}%
                        </span>
                        <span className={cn(
                          "tabular-nums font-bold px-1.5 py-0.2 rounded border text-[10px]",
                          isLight
                            ? "text-emerald-800 bg-emerald-100 border-emerald-300"
                            : "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                        )}>
                          Net: {formatINR(netVal)}
                        </span>
                      </div>
                    </div>
                    <div className={cn("h-2 w-full rounded-full overflow-hidden", isLight ? "bg-slate-200" : "bg-slate-800/80")}>
                      <div
                        className={cn(
                          'h-full rounded-full transition-all duration-300',
                          isBest
                            ? 'bg-gradient-to-r from-indigo-500 via-indigo-400 to-purple-500 shadow-sm'
                            : score.action === 'NO_ACTION'
                            ? (isLight ? 'bg-slate-400' : 'bg-slate-600')
                            : 'bg-indigo-400/50'
                        )}
                        style={{ width: `${score.recoveryProbability * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>


          {/* Why WAPSI Chose This (SHAP Feature Attribution) */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-slate-900/80 border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <TrendingUp className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />
                Why WAPSI Chose This (SHAP Causal Weights)
              </span>
              <span className={cn("text-[10px]", isLight ? "text-slate-500" : "text-slate-400")}>Feature impact</span>
            </div>

            <div className="space-y-2">
              {detail.explanation.map((item) => {
                const isPositive = item.contribution > 0;
                return (
                  <div key={item.featureName} className={cn(
                    "p-2.5 rounded-xl border space-y-1",
                    isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800/80"
                  )}>
                    <div className="flex items-center justify-between text-[11px]">
                      <span className={cn("font-medium", isLight ? "text-slate-700" : "text-slate-300")}>{item.label}</span>
                      <span
                        className={cn(
                          'font-bold tabular-nums text-xs',
                          isPositive ? (isLight ? 'text-emerald-700' : 'text-emerald-400') : (isLight ? 'text-rose-700' : 'text-rose-400')
                        )}
                      >
                        {item.displayValue}
                      </span>
                    </div>
                    <div className={cn("h-1.5 w-full rounded-full overflow-hidden", isLight ? "bg-slate-200" : "bg-slate-800")}>
                      <div
                        className={cn(
                          'h-full rounded-full',
                          isPositive ? 'bg-emerald-500' : 'bg-rose-500'
                        )}
                        style={{ width: `${Math.min(100, Math.abs(item.contribution) * 400)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Autonomous Payment Link & WhatsApp Dispatch */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-slate-900/80 border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <Zap className="w-3.5 h-3.5 text-amber-500" />
                Autonomous Channel Execution
              </span>
              <span className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded border",
                currentCase.paymentLinkId
                  ? isLight ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                  : isLight ? "bg-slate-100 text-slate-600 border-slate-200" : "bg-slate-800 text-slate-400 border-slate-700"
              )}>
                {currentCase.paymentLinkId ? "Link Active" : "No Link Yet"}
              </span>
            </div>

            {actionSuccessMessage && (
              <div className="p-2.5 rounded-xl border text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span>{actionSuccessMessage}</span>
              </div>
            )}

            {dispatchErrorDetail && (
              <div className="p-2.5 rounded-xl border text-[10.5px] bg-amber-500/10 text-amber-300 border-amber-500/20 leading-relaxed space-y-1">
                <span className="font-bold block">Meta WhatsApp Cloud Status:</span>
                <p className="font-mono text-[10px] break-all opacity-90">{dispatchErrorDetail}</p>
                <p className="text-[10px] opacity-80 pt-0.5">
                  💡 Tip: In Meta Business Suite, assign WhatsApp Account <strong>969727602419694</strong> to System User <strong>WAPSI-WhatsApp-Integration</strong> with Full Control.
                </p>
              </div>
            )}

            {/* Recipient Phone Selector */}
            <div className={cn(
              "p-2.5 rounded-xl border flex items-center justify-between gap-2 text-[11px]",
              isLight ? "bg-slate-50 border-slate-200" : "bg-slate-950/60 border-slate-800"
            )}>
              <span className={isLight ? "text-slate-500 font-medium" : "text-slate-400 font-medium"}>
                Target WhatsApp:
              </span>
              <div className="flex items-center gap-1.5 flex-1 max-w-[220px]">
                <input
                  type="text"
                  value={recipientPhone}
                  onChange={(e) => setRecipientPhone(e.target.value)}
                  placeholder="+91..."
                  className={cn(
                    "w-full px-2 py-1 rounded-lg text-xs font-mono font-semibold border outline-none text-right",
                    isLight
                      ? "bg-white border-slate-300 text-slate-900 focus:border-emerald-500"
                      : "bg-slate-900 border-slate-700 text-slate-100 focus:border-emerald-500"
                  )}
                />
              </div>
            </div>

            {/* Optional Meta Access Token Override */}
            <div className="space-y-1.5 pt-0.5">
              <button
                type="button"
                onClick={() => setShowTokenInput(!showTokenInput)}
                className="text-[10px] text-indigo-400 hover:text-indigo-300 underline flex items-center gap-1 cursor-pointer"
              >
                <span>{showTokenInput ? '− Hide Meta Token Override' : '+ Use Custom / Fresh Meta Developer Token'}</span>
              </button>

              {showTokenInput && (
                <div className={cn(
                  "p-2.5 rounded-xl border space-y-1 text-left",
                  isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/90 border-slate-700"
                )}>
                  <div className="flex items-center justify-between text-[10.5px]">
                    <span className={isLight ? "text-slate-600 font-semibold" : "text-slate-300 font-semibold"}>Meta Access Token:</span>
                    <span className="text-[9.5px] text-slate-500 font-mono">EAAN...</span>
                  </div>
                  <input
                    type="password"
                    value={customToken}
                    onChange={(e) => setCustomToken(e.target.value)}
                    placeholder="Paste 24-hr token from Meta WhatsApp > API Setup"
                    className={cn(
                      "w-full px-2 py-1 rounded-lg text-[10.5px] font-mono border outline-none",
                      isLight
                        ? "bg-white border-slate-300 text-slate-900 focus:border-indigo-500"
                        : "bg-slate-950 border-slate-700 text-slate-200 focus:border-indigo-500"
                    )}
                  />
                  <p className="text-[9.5px] text-slate-400 leading-normal">
                    💡 If your System User lacks asset permissions, you can paste the temporary 24-hr token from Meta App Dashboard &gt; WhatsApp &gt; API Setup.
                  </p>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                size="sm"
                className={cn(
                  "flex items-center justify-center gap-1.5 py-2 text-xs font-semibold rounded-xl cursor-pointer",
                  isLight
                    ? "bg-indigo-50/70 border-indigo-200 text-indigo-700 hover:bg-indigo-100"
                    : "bg-indigo-950/40 border-indigo-500/30 text-indigo-300 hover:bg-indigo-900/40"
                )}
                disabled={isGeneratingLink || currentCase.status === 'RECOVERED'}
                onClick={handleGenerateLink}
              >
                {isGeneratingLink ? (
                  <RotateCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <LinkIcon className="w-3.5 h-3.5" />
                )}
                <span>Generate Razorpay Link</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                className={cn(
                  "flex items-center justify-center gap-1.5 py-2 text-xs font-semibold rounded-xl cursor-pointer",
                  isLight
                    ? "bg-emerald-50/70 border-emerald-200 text-emerald-700 hover:bg-emerald-100"
                    : "bg-emerald-950/40 border-emerald-500/30 text-emerald-300 hover:bg-emerald-900/40"
                )}
                disabled={isDispatchingWa || currentCase.status === 'RECOVERED'}
                onClick={handleDispatchWhatsApp}
              >
                {isDispatchingWa ? (
                  <RotateCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                <span>Dispatch WhatsApp</span>
              </Button>
            </div>

            {(currentCase.paymentLinkId || currentCase.whatsappMessageId) && (
              <div className={cn(
                "p-2.5 rounded-xl border space-y-1.5 text-[11px]",
                isLight ? "bg-slate-50 border-slate-200" : "bg-slate-950/60 border-slate-800"
              )}>
                {currentCase.paymentLinkId && (
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className={isLight ? "text-slate-500" : "text-slate-400"}>Payment Link:</span>
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                        {currentCase.paymentLinkId}
                      </span>
                      {currentCase.paymentLinkUrl && (
                        <button
                          type="button"
                          onClick={() => handleCopyLink(currentCase.paymentLinkUrl!)}
                          className="hover:text-slate-900 dark:hover:text-white cursor-pointer"
                          title="Copy Link URL"
                        >
                          {copiedLink ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3 text-slate-400" />}
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {currentCase.whatsappMessageId && (
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className={isLight ? "text-slate-500" : "text-slate-400"}>WhatsApp Msg ID:</span>
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                      {currentCase.whatsappMessageId}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Evidence & Signal Weighting */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-slate-900/80 border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <Layers className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />
                Evidence Attribution & Bayesian Prior
              </span>
              <span className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded border",
                isLight
                  ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                  : "bg-indigo-500/10 text-indigo-300 border-indigo-500/20"
              )}>
                Cross-Merchant Network
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className={cn(
                "p-3 rounded-xl border text-center",
                isLight ? "bg-indigo-50/70 border-indigo-200 text-indigo-950" : "bg-indigo-950/30 border-indigo-500/20"
              )}>
                <span className={cn("text-[10px] uppercase font-bold block", isLight ? "text-indigo-700" : "text-indigo-300")}>Network Prior</span>
                <span className={cn("text-base font-black tabular-nums block my-0.5", isLight ? "text-slate-900" : "text-white")}>
                  {Math.round(detail.networkPrior.networkWeight * 100)}%
                </span>
                <span className={cn("text-[9px] block", isLight ? "text-slate-500" : "text-slate-400")}>12.8M sample points</span>
              </div>
              <div className={cn(
                "p-3 rounded-xl border text-center",
                isLight ? "bg-slate-50 border-slate-200 text-slate-900" : "bg-slate-950/80 border-slate-800"
              )}>
                <span className={cn("text-[10px] uppercase font-bold block", isLight ? "text-slate-600" : "text-slate-400")}>Merchant History</span>
                <span className={cn("text-base font-black tabular-nums block my-0.5", isLight ? "text-slate-900" : "text-white")}>
                  {Math.round(detail.networkPrior.merchantWeight * 100)}%
                </span>
                <span className={cn("text-[9px] block", isLight ? "text-slate-500" : "text-slate-400")}>200 sample points</span>
              </div>
            </div>
            <p className={cn(
              "text-[11px] italic p-2.5 rounded-xl border leading-relaxed",
              isLight ? "bg-slate-50 text-slate-700 border-slate-200" : "bg-slate-950/50 text-slate-400 border-slate-800/80"
            )}>
              "{detail.networkPrior.coldStartBenefit}"
            </p>
          </div>

          {/* Policy Compliance Checklist */}
          <div className={cn(
            "p-4 rounded-2xl border space-y-3 shadow-md",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-slate-900/80 border-slate-800"
          )}>
            <div className="flex items-center justify-between">
              <span className={cn("font-bold text-xs flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                Policy Validation ({detail.policy.checksPassed}/{detail.policy.checksTotal} Passed)
              </span>
              <span className={cn(
                "text-[10px] font-bold px-2 py-0.5 rounded border flex items-center gap-1",
                isLight
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              )}>
                <Lock className="w-3 h-3" /> TEE Simulated
              </span>
            </div>

            <div className="space-y-1.5">
              {detail.policy.checks.map((check, i) => (
                <div key={i} className={cn(
                  "flex items-center justify-between text-[11px] p-2.5 rounded-xl border",
                  isLight ? "bg-slate-50 border-slate-200" : "bg-slate-950/60 border-slate-800/80"
                )}>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                    <span className={cn("font-medium", isLight ? "text-slate-800" : "text-slate-300")}>{check.rule}</span>
                  </div>
                  <span className={cn("tabular-nums font-mono text-[10px]", isLight ? "text-slate-500 font-semibold" : "text-slate-400")}>
                    {check.currentValue}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer Action Buttons */}
        <div className={cn(
          "p-4 border-t space-y-2 transition-colors",
          isLight ? "bg-slate-50 border-slate-200" : "bg-[#0B0F19] border-slate-800"
        )}>
          {isPolicyCheckRunning ? (
            <div className={cn(
              "p-3.5 rounded-xl border text-center space-y-2",
              isLight ? "bg-indigo-50 border-indigo-200 text-indigo-900" : "bg-indigo-950/80 border-indigo-500/40 text-indigo-200"
            )}>
              <div className="flex items-center justify-center gap-2 text-xs font-bold">
                <RotateCw className="w-4 h-4 animate-spin text-indigo-600 dark:text-indigo-400" />
                <span>Enforcing Policy Bounds & Dispatching ({policyCheckProgress}%)...</span>
              </div>
              <div className={cn("w-full h-1.5 rounded-full overflow-hidden", isLight ? "bg-slate-200" : "bg-slate-800")}>
                <div 
                  className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-300 rounded-full" 
                  style={{ width: `${policyCheckProgress}%` }}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {currentCase.status !== 'RECOVERED' && (
                <>
                  <div className="flex gap-2">
                    <Button
                      variant="success"
                      className="flex-1 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 text-white gap-1.5 py-2.5 rounded-xl cursor-pointer"
                      onClick={() => setIsApprovalModalOpen(true)}
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      Approve Action
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className={cn(
                        "text-xs font-semibold px-4 rounded-xl cursor-pointer",
                        isLight ? "border-slate-300 hover:bg-slate-200 text-slate-800 bg-white" : "border-slate-700 hover:bg-slate-800 text-slate-200"
                      )}
                      onClick={() => reviewCase(currentCase.caseId)}
                    >
                      Review
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="text-xs font-semibold px-4 rounded-xl cursor-pointer"
                      onClick={() => rejectCase(currentCase.caseId)}
                    >
                      Reject
                    </Button>
                  </div>

                  <Button
                    variant="primary"
                    className="w-full text-xs font-bold py-2 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 shadow-md shadow-emerald-600/20 gap-1.5 cursor-pointer text-white"
                    onClick={() => simulateRecovery(currentCase.caseId)}
                  >
                    <Zap className="w-3.5 h-3.5 text-amber-300" />
                    Simulate Outcome & Closed-Loop Learning Update
                  </Button>
                </>
              )}

              {currentCase.status === 'RECOVERED' && (
                <div className="space-y-2">
                  <div className={cn(
                    "w-full p-3 rounded-xl border text-center font-bold text-xs flex items-center justify-center gap-2 shadow-md",
                    isLight
                      ? "bg-emerald-50 border-emerald-300 text-emerald-800"
                      : "bg-gradient-to-r from-emerald-950/80 to-teal-950/80 border-emerald-500/40 text-emerald-300"
                  )}>
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    <span>Successfully Recovered ({formatINR(currentCase.amount)})</span>
                  </div>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-full text-xs font-semibold py-2 rounded-xl cursor-pointer",
                      isLight ? "bg-white border-slate-300 text-slate-800 hover:bg-slate-100" : "bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800"
                    )}
                    onClick={() => openLearningModal()}
                  >
                    View Closed-Loop Bayesian Prior Shift
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        <OperatorApprovalModal
          caseData={currentCase}
          isOpen={isApprovalModalOpen}
          onClose={() => setIsApprovalModalOpen(false)}
          onSuccess={(res) => {
            approveCase(currentCase.caseId);
          }}
        />
      </motion.div>
    </div>
  );
};
