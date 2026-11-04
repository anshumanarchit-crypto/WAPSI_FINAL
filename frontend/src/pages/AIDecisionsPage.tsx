import React, { useState } from 'react';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/Tooltip';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip as RechartsTooltip, 
  BarChart, 
  Bar, 
  Cell,
  ReferenceLine
} from 'recharts';
import { 
  TrendingUp, 
  Clock, 
  Layers, 
  Info,
  Ban,
  RefreshCw,
  MessageSquare,
  PhoneCall,
  Gift,
  CheckCircle2,
  ChevronDown,
  Sparkles,
  HelpCircle,
  ShieldCheck,
  Check,
  AlertTriangle
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { CyberBrainIcon } from '../components/shared/CyberBrainIcon';
import { formatINR, formatPercent } from '../lib/formatting';
import { cn } from '../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { useDemoStore } from '../store/demoStore';
import { useModelHealth, useDecisionsOverview } from '../hooks/useAIDecisions';
import { useRecoveryCases } from '../hooks/useRecovery';
import { getHeroTransaction, makeRecoveryDecision } from '../services/causalEngine';

interface TreatmentOption {
  id: string;
  name: string;
  prob: number;
  uplift: number;
  upliftLabel: string;
  color: string;
  hoverBg: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  isBaseline?: boolean;
}

export const AIDecisionsPage: React.FC = () => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const approveCase = useDemoStore((state) => state.approveCase);
  const storeCases = useDemoStore((state) => state.cases);
  const driftReport = useDemoStore((state) => state.driftReport);
  const setDriftLevel = useDemoStore((state) => state.setDriftLevel);
  const engineState = useDemoStore((state) => state.engineState);
  const rawTransactions = useDemoStore((state) => state.rawTransactions);
  const caseDetails = useDemoStore((state) => state.caseDetails);
  const overviewMetrics = useDemoStore((state) => state.overviewMetrics);
  const openCounterfactualModal = useDemoStore((state) => state.openCounterfactualModal);

  const { data: liveCases } = useRecoveryCases();
  const queueCases = (liveCases && liveCases.length > 0) ? liveCases : storeCases;

  const { data: modelHealth } = useModelHealth();
  const { data: decisionsOverview } = useDecisionsOverview();

  // Hero case decision
  const heroCase = storeCases.find(c => c.amount === 8999) || storeCases[0];
  const heroTx = rawTransactions[heroCase?.caseId || ''] || getHeroTransaction();
  const heroDecision = caseDetails[heroCase?.caseId || ''] || makeRecoveryDecision(heroTx, engineState);

  const [activeTab, setActiveTab] = useState('uplift');
  const [selectedTreatment, setSelectedTreatment] = useState<string>('WhatsApp');
  const [comparisonBaseline, setComparisonBaseline] = useState<'No Action' | 'Standard Rules'>('No Action');
  const [isBaselineDropdownOpen, setIsBaselineDropdownOpen] = useState<boolean>(false);
  const [hoveredBar, setHoveredBar] = useState<string | null>(null);
  const [showWhyTimingModal, setShowWhyTimingModal] = useState<boolean>(false);
  const [activeTimingHour, setActiveTimingHour] = useState<string>('18h');

  const tabs = [
    { id: 'queue', label: 'Decision Queue', tooltip: 'Live queue of pending transactions undergoing causal evaluation' },
    { id: 'uplift', label: 'Uplift Intelligence', tooltip: 'Incremental treatment probability comparisons across all communication channels' },
    { id: 'timing', label: 'Timing Intelligence', tooltip: 'Hazard model survival curves identifying optimal execution hours' },
    { id: 'network', label: 'Network Prior', tooltip: 'Cross-merchant 12.8M transaction intelligence blended with local evidence' },
    { id: 'health', label: 'Model Health', tooltip: 'AUUC, Qini, Conformal Coverage (95.1%) and drift monitoring' },
  ];

  // Baseline probability & metrics based on comparison selection derived directly from engine
  const baselineProb = comparisonBaseline === 'No Action' 
    ? Math.round(heroDecision.naturalRecoveryProbability * 100) 
    : Math.round(Math.min(95, (heroDecision.naturalRecoveryProbability + 0.08) * 100));

  const avgUplift = comparisonBaseline === 'No Action' 
    ? `+${Math.round(heroDecision.incrementalUplift * 100)}%` 
    : `+${Math.max(0, Math.round((heroDecision.incrementalUplift - 0.08) * 100))}%`;
  const avgUpliftSubtext = comparisonBaseline === 'No Action' ? '+12.4% vs counterfactual' : 'Net lift over legacy rules';
  const incRecoveryEst = overviewMetrics?.incrementalRecovery ? formatINR(overviewMetrics.incrementalRecovery) : '₹2.14L';
  const incRecoverySubtext = comparisonBaseline === 'No Action' ? '+37.6% vs baseline' : '+₹1.42L above rule heuristics';

  // Dynamic Treatments matching baseline comparison mode, built directly from heroDecision.actionScores
  const actionMeta: Record<string, { id: string; name: string; color: string; hoverBg: string; icon: React.ComponentType<{ className?: string }>; iconColor: string }> = {
    RETRY: { 
      id: 'Retry', 
      name: 'Retry', 
      color: '#3B82F6', 
      hoverBg: 'rgba(59, 130, 246, 0.15)', 
      icon: RefreshCw, 
      iconColor: 'text-blue-500' 
    },
    WHATSAPP: { 
      id: 'WhatsApp', 
      name: 'WhatsApp', 
      color: '#10B981', 
      hoverBg: 'rgba(16, 185, 129, 0.15)', 
      icon: MessageSquare, 
      iconColor: 'text-emerald-500' 
    },
    VOICE: { 
      id: 'Voice Call', 
      name: 'Voice Call', 
      color: '#8B5CF6', 
      hoverBg: 'rgba(139, 92, 246, 0.15)', 
      icon: PhoneCall, 
      iconColor: 'text-purple-500' 
    },
    INCENTIVE: { 
      id: 'Incentive Link', 
      name: 'Incentive Link', 
      color: '#F59E0B', 
      hoverBg: 'rgba(245, 158, 11, 0.15)', 
      icon: Gift, 
      iconColor: 'text-amber-500' 
    },
  };

  const treatments: TreatmentOption[] = [
    { 
      id: 'Baseline', 
      name: comparisonBaseline, 
      prob: baselineProb, 
      uplift: 0, 
      upliftLabel: 'Baseline', 
      color: '#64748B', 
      hoverBg: 'rgba(100, 116, 139, 0.15)', 
      icon: comparisonBaseline === 'No Action' ? Ban : ShieldCheck, 
      iconColor: 'text-slate-400', 
      isBaseline: true 
    },
    ...(['RETRY', 'WHATSAPP', 'VOICE', 'INCENTIVE'] as const).map((key) => {
      const score = (heroDecision.actionScores || []).find((s) => s.action === key);
      const meta = actionMeta[key];
      const prob = score ? Math.round(score.recoveryProbability * 100) : 70;
      const upliftVal = Math.max(0, prob - baselineProb);
      return {
        id: meta.id,
        name: meta.name,
        prob,
        uplift: upliftVal,
        upliftLabel: `+${upliftVal}% uplift`,
        color: meta.color,
        hoverBg: meta.hoverBg,
        icon: meta.icon,
        iconColor: meta.iconColor,
      };
    }),
  ];

  // Timing Intelligence Data directly connected to heroDecision.timing.curvePoints
  const timingPoints = (heroDecision.timing?.curvePoints || []).length > 0
    ? heroDecision.timing.curvePoints.map((cp) => ({
        hour: `${cp.hour}h`,
        prob: Math.round(cp.probability * 100),
        isPeak: cp.hour === (heroDecision.timing?.recommendedHour ?? 10),
      }))
    : [
        { hour: '0h', prob: 22 },
        { hour: '6h', prob: 50 },
        { hour: '12h', prob: 62 },
        { hour: '18h', prob: 72, isPeak: true },
        { hour: '24h', prob: 66 },
        { hour: '36h', prob: 58 },
        { hour: '48h', prob: 38 },
        { hour: '72h', prob: 18 },
      ];

  // Dynamic Segment impacts based on selected treatment & baseline
  const getSegmentImpacts = () => {
    const isRules = comparisonBaseline === 'Standard Rules';
    
    if (selectedTreatment === 'WhatsApp') {
      return [
        { segment: 'Insufficient Funds (1-2 attempts)', uplift: isRules ? '+20.4%' : '+28.3%', impact: 'High impact', width: '92%', color: 'bg-emerald-500' },
        { segment: 'Salary Window (T+1 to T+3)', uplift: isRules ? '+18.1%' : '+25.7%', impact: 'High impact', width: '84%', color: 'bg-emerald-500' },
        { segment: 'First Time Failures', uplift: isRules ? '+15.6%' : '+22.1%', impact: 'Medium impact', width: '72%', color: 'bg-cyan-500' },
        { segment: 'High Historic Payer Score', uplift: isRules ? '+13.2%' : '+18.9%', impact: 'Medium impact', width: '62%', color: 'bg-cyan-500' },
        { segment: 'Small Ticket (< ₹2,000)', uplift: isRules ? '+8.5%' : '+12.4%', impact: 'Low impact', width: '42%', color: 'bg-slate-500' },
      ];
    }
    if (selectedTreatment === 'Retry') {
      return [
        { segment: 'Technical Gateway Drop / Timeout', uplift: isRules ? '+26.8%' : '+34.2%', impact: 'High impact', width: '94%', color: 'bg-blue-500' },
        { segment: 'Server Busy / Bank Downtime', uplift: isRules ? '+24.1%' : '+31.5%', impact: 'High impact', width: '86%', color: 'bg-blue-500' },
        { segment: 'Insufficient Funds (Pre-Salary)', uplift: isRules ? '+12.4%' : '+18.4%', impact: 'Medium impact', width: '64%', color: 'bg-cyan-500' },
        { segment: 'e-Mandate Debit Window Lapsed', uplift: isRules ? '+10.1%' : '+15.2%', impact: 'Medium impact', width: '54%', color: 'bg-cyan-500' },
        { segment: 'Card Limit Exceeded', uplift: isRules ? '+5.3%' : '+8.6%', impact: 'Low impact', width: '35%', color: 'bg-slate-500' },
      ];
    }
    if (selectedTreatment === 'Voice Call') {
      return [
        { segment: 'High Value Subscriptions (> ₹10,000)', uplift: isRules ? '+24.5%' : '+32.6%', impact: 'High impact', width: '90%', color: 'bg-purple-500' },
        { segment: 'B2B Invoice Mandate Lapsed', uplift: isRules ? '+21.8%' : '+29.4%', impact: 'High impact', width: '82%', color: 'bg-purple-500' },
        { segment: 'Repeat Chronic Inactive Users', uplift: isRules ? '+16.2%' : '+21.8%', impact: 'Medium impact', width: '68%', color: 'bg-purple-500' },
        { segment: 'Senior Demographic Accounts', uplift: isRules ? '+14.0%' : '+18.5%', impact: 'Medium impact', width: '58%', color: 'bg-cyan-500' },
        { segment: 'General Checkout Drops', uplift: isRules ? '+6.1%' : '+9.2%', impact: 'Low impact', width: '38%', color: 'bg-slate-500' },
      ];
    }
    if (selectedTreatment === 'Incentive Link') {
      return [
        { segment: 'Cart Abandonment Checkout', uplift: isRules ? '+30.2%' : '+38.5%', impact: 'High impact', width: '96%', color: 'bg-amber-500' },
        { segment: 'Price-Sensitive Discretionary Users', uplift: isRules ? '+25.7%' : '+33.1%', impact: 'High impact', width: '88%', color: 'bg-amber-500' },
        { segment: 'Churn Risk (3+ Month Inactive)', uplift: isRules ? '+20.5%' : '+27.9%', impact: 'High impact', width: '76%', color: 'bg-amber-500' },
        { segment: 'First-time Subscriptions', uplift: isRules ? '+15.2%' : '+20.4%', impact: 'Medium impact', width: '60%', color: 'bg-cyan-500' },
        { segment: 'Enterprise / B2B Accounts', uplift: isRules ? '+4.1%' : '+6.8%', impact: 'Low impact', width: '28%', color: 'bg-slate-500' },
      ];
    }
    // Baseline / No Action
    return [
      { segment: 'Natural Organic Recovery', uplift: '+0.0%', impact: 'Baseline', width: '48%', color: 'bg-slate-500' },
      { segment: 'Auto-Clearing (Same Day)', uplift: '+0.0%', impact: 'Baseline', width: '45%', color: 'bg-slate-500' },
      { segment: 'Customer Initiated Portal Pay', uplift: '+0.0%', impact: 'Baseline', width: '38%', color: 'bg-slate-500' },
      { segment: 'Subsequent Cycle Rollover', uplift: '+0.0%', impact: 'Baseline', width: '25%', color: 'bg-slate-500' },
      { segment: 'Unassisted Recovery', uplift: '+0.0%', impact: 'Baseline', width: '15%', color: 'bg-slate-500' },
    ];
  };

  const currentSegmentImpacts = getSegmentImpacts();

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-4 max-w-[1600px] mx-auto"
    >
      <Topbar
        title="AI Decisions"
        subtitle="Understand how WAPSI thinks and decides the best recovery action"
      />

      {/* Hero Statement with CyberBrainIcon */}
      <motion.div 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className={cn(
          "p-4 rounded-2xl flex flex-wrap items-center justify-between gap-4 shadow-xl backdrop-blur-md transition-colors border",
          isLight
            ? "bg-gradient-to-r from-indigo-50/90 via-purple-50/80 to-indigo-100/90 border-indigo-200 shadow-indigo-100/50"
            : "bg-gradient-to-r from-indigo-950/80 via-[#0B1120] to-purple-950/70 border-indigo-500/30 shadow-indigo-950/30"
        )}
      >
        <div className="flex items-center gap-3.5">
          <div className={cn(
            "p-2.5 rounded-2xl border flex items-center justify-center shrink-0 shadow-lg",
            isLight
              ? "bg-indigo-100 border-indigo-300 shadow-indigo-200"
              : "bg-gradient-to-br from-indigo-950/90 to-purple-950/90 border-indigo-500/40 shadow-indigo-950/60"
          )}>
            <CyberBrainIcon className={cn("w-8 h-8 animate-pulse", isLight ? "text-indigo-600" : "text-indigo-400")} />
          </div>
          <div>
            <h2 className={cn(
              "text-base font-bold tracking-tight",
              isLight ? "text-slate-900" : "text-white"
            )}>
              WAPSI doesn't predict who pays. It predicts who pays <span className={cn("underline decoration-indigo-500/50", isLight ? "text-indigo-700" : "text-indigo-400")}>because we act</span>.
            </h2>
            <p className={cn(
              "text-xs mt-0.5",
              isLight ? "text-slate-600 font-medium" : "text-slate-300"
            )}>
              Causal Uplift Model • Hazard Timing Engine • Conformal Prediction Bounds
            </p>
          </div>
        </div>

        {/* Top 3 Quick Metrics (Reactivity based on Baseline comparison) */}
        <div className="flex items-center gap-6">
          <div className="text-right">
            <span className={cn("text-[10px] uppercase font-semibold block", isLight ? "text-slate-500" : "text-slate-400")}>Avg. Incremental Uplift</span>
            <span className={cn(
              "text-base font-extrabold tabular-nums",
              isLight ? "text-emerald-700 font-black" : "text-emerald-400"
            )}>
              {decisionsOverview?.backendOverview?.averageUplift 
                ? `+${(decisionsOverview.backendOverview.averageUplift * 100).toFixed(1)}%` 
                : avgUplift}
            </span>
            <span className={cn("text-[9px] block", isLight ? "text-slate-500" : "text-slate-400")}>{avgUpliftSubtext}</span>
          </div>
          <div className={cn("text-right border-l pl-6", isLight ? "border-slate-300" : "border-slate-800")}>
            <span className={cn("text-[10px] uppercase font-semibold block", isLight ? "text-slate-500" : "text-slate-400")}>Decisions Evaluated</span>
            <span className={cn(
              "text-base font-extrabold tabular-nums",
              isLight ? "text-slate-900 font-black" : "text-white"
            )}>
              {decisionsOverview?.backendOverview?.totalDecisions 
                ? decisionsOverview.backendOverview.totalDecisions.toLocaleString('en-IN') 
                : storeCases.length.toLocaleString('en-IN')}
            </span>
            <span className={cn("text-[9px] block", isLight ? "text-slate-500" : "text-slate-400")}>100% causal confidence</span>
          </div>
          <div className={cn("text-right border-l pl-6", isLight ? "border-slate-300" : "border-slate-800")}>
            <span className={cn("text-[10px] uppercase font-semibold block", isLight ? "text-slate-500" : "text-slate-400")}>Incremental Recovery (Est.)</span>
            <span className={cn(
              "text-base font-extrabold tabular-nums",
              isLight ? "text-indigo-700 font-black" : "text-indigo-300"
            )}>
              {overviewMetrics?.incrementalRecovery ? formatINR(overviewMetrics.incrementalRecovery) : incRecoveryEst}
            </span>
            <span className={cn("text-[9px] block", isLight ? "text-slate-500" : "text-slate-400")}>{incRecoverySubtext}</span>
          </div>
        </div>
      </motion.div>

      {/* Tabs with Descriptive Tooltips */}
      <TooltipProvider delayDuration={150}>
        <div className={cn("flex items-center gap-1.5 border-b pb-2 overflow-x-auto", isLight ? "border-slate-200" : "border-slate-800")}>
          {tabs.map((tab) => (
            <Tooltip key={tab.id}>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5',
                    activeTab === tab.id
                      ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/30 font-bold'
                      : isLight
                      ? 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                  )}
                >
                  <span>{tab.label}</span>
                  {tab.id === 'queue' && (
                    <span className={cn(
                      "px-1.5 py-0.2 text-[9.5px] rounded-full font-bold border",
                      activeTab === tab.id
                        ? "bg-white/20 text-white border-white/30"
                        : isLight
                        ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                        : "bg-indigo-900/80 text-white border-indigo-400/30"
                    )}>
                      {queueCases.filter(c => c.status !== 'APPROVED' && c.status !== 'RECOVERED').length || queueCases.length}
                    </span>
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className={cn("text-xs max-w-xs", isLight ? "bg-white text-slate-900 border-slate-200 shadow-md" : "bg-slate-900 border-slate-700 text-white")}>
                <p>{tab.tooltip}</p>
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </TooltipProvider>

      {/* Dynamic Tab Content Views */}
      <AnimatePresence mode="wait">
        {/* VIEW 1: DECISION QUEUE TAB */}
        {activeTab === 'queue' && (
          <motion.div
            key="queue-view"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <Card className={cn("p-4 sm:p-5 rounded-2xl space-y-4 shadow-2xl transition-colors border", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white")}>
              <div className={cn("flex flex-wrap items-center justify-between gap-3 border-b pb-3", isLight ? "border-slate-100" : "border-slate-800")}>
                <div>
                  <CardTitle className={cn("text-sm font-bold flex items-center gap-2", isLight ? "text-slate-900" : "text-white")}>
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span>Live Causal Decision Queue</span>
                    <span className={cn("text-xs font-normal", isLight ? "text-slate-500" : "text-slate-400")}>
                      ({queueCases.filter(c => c.status !== 'APPROVED' && c.status !== 'RECOVERED').length || queueCases.length} Pending Real-time Evaluations)
                    </span>
                  </CardTitle>
                  <p className={cn("text-[11px] mt-0.5", isLight ? "text-slate-500" : "text-slate-400")}>
                    Transactions scored by double machine learning model awaiting scheduled dispatch
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn("text-[11px]", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>Auto-Approval Threshold:</span>
                  <span className={cn(
                    "text-xs font-bold px-2 py-0.5 rounded-lg border",
                    isLight ? "text-emerald-800 bg-emerald-50 border-emerald-200" : "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
                  )}>
                    &ge; 75% Confidence
                  </span>
                </div>
              </div>

              {/* Queue Table */}
              <div className={cn("overflow-x-auto rounded-xl border", isLight ? "border-slate-200 bg-white" : "border-slate-800/80 bg-slate-950/50")}>
                <table className="w-full text-left text-[11px] border-collapse">
                  <thead>
                    <tr className={cn(
                      "border-b font-bold uppercase tracking-wider text-[10px]",
                      isLight ? "bg-slate-50 border-slate-200 text-slate-500" : "border-slate-800 text-slate-400 bg-slate-900/90"
                    )}>
                      <th className="py-2.5 px-3">Case ID</th>
                      <th className="py-2.5 px-3">Customer</th>
                      <th className="py-2.5 px-3">Amount</th>
                      <th className="py-2.5 px-3">P(Baseline)</th>
                      <th className="py-2.5 px-3">P(Treatment)</th>
                      <th className="py-2.5 px-3">Causal Uplift (τ)</th>
                      <th className="py-2.5 px-3">Recommendation</th>
                      <th className="py-2.5 px-3">Confidence Bounds</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className={cn("divide-y", isLight ? "divide-slate-100" : "divide-slate-800/60")}>
                    {queueCases.slice(0, 8).map((row) => {
                      const p0 = row.naturalRecoveryProbability 
                        ? `${Math.round(row.naturalRecoveryProbability * 100)}%` 
                        : '24%';
                      const pt = row.treatmentProbability 
                        ? `${Math.round(row.treatmentProbability * 100)}%` 
                        : `${Math.min(95, Math.round((0.24 + row.incrementalUplift) * 100))}%`;
                      const tau = `+${Math.round(row.incrementalUplift * 100)}%`;
                      const timingText = row.recommendedTime || row.optimalWindow || '18h';
                      const confPct = Math.round(row.decisionConfidence * 100);
                      const confInterval = `${confPct}% [${Math.max(10, confPct - 5)}-${Math.min(99, confPct + 4)}%]`;
                      const isApproved = row.status === 'APPROVED';

                      return (
                        <tr key={row.caseId} className={cn("transition-colors", isLight ? "hover:bg-slate-50" : "hover:bg-indigo-950/20")}>
                          <td className={cn("py-2.5 px-3 font-mono font-bold", isLight ? "text-indigo-700" : "text-indigo-300")}>{row.caseId}</td>
                          <td className={cn("py-2.5 px-3 font-medium", isLight ? "text-slate-900" : "text-white")}>{row.customerName}</td>
                          <td className={cn("py-2.5 px-3 font-bold tabular-nums", isLight ? "text-slate-900" : "text-white")}>{formatINR(row.amount)}</td>
                          <td className={cn("py-2.5 px-3 tabular-nums", isLight ? "text-slate-500" : "text-slate-400")}>{p0}</td>
                          <td className={cn("py-2.5 px-3 font-bold tabular-nums", isLight ? "text-emerald-700" : "text-emerald-400")}>{pt}</td>
                          <td className={cn("py-2.5 px-3 font-black tabular-nums", isLight ? "text-emerald-800" : "text-emerald-300")}>{tau}</td>
                          <td className="py-2.5 px-3">
                            <span className={cn(
                              "px-2 py-0.5 rounded-md text-[10px] font-bold border",
                              isLight ? "bg-indigo-50 text-indigo-700 border-indigo-200" : "bg-indigo-500/15 text-indigo-300 border-indigo-500/30"
                            )}>
                              {row.recommendedActionLabel || row.recommendedAction} • {timingText}
                            </span>
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono text-[10px]", isLight ? "text-slate-600" : "text-slate-300")}>{confInterval}</td>
                          <td className="py-2.5 px-3 text-right">
                            {isApproved ? (
                              <span className="px-2.5 py-1 rounded-lg border text-[10px] font-bold bg-emerald-950/60 text-emerald-300 border-emerald-500/40 inline-flex items-center gap-1">
                                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                                <span>Dispatched</span>
                              </span>
                            ) : (
                              <button 
                                onClick={() => approveCase(row.caseId)}
                                className={cn(
                                  "px-2.5 py-1 rounded-lg border text-[10px] font-bold transition-all cursor-pointer shadow-sm",
                                  isLight ? "bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border-emerald-500/40"
                                )}
                              >
                                Approve Dispatch
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </motion.div>
        )}

        {/* VIEW 2: UPLIFT INTELLIGENCE TAB */}
        {activeTab === 'uplift' && (
          <motion.div
            key="uplift-view"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Treatment Uplift Comparison Card */}
              <div className="lg:col-span-7">
                <Card className={cn("p-4 sm:p-5 rounded-2xl space-y-4 shadow-2xl backdrop-blur-md transition-colors border", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white")}>
                  {/* Header: Title + Subtitle + vs Baseline dropdown */}
                  <div className={cn("flex items-center justify-between pb-3 border-b", isLight ? "border-slate-100" : "border-slate-800/80")}>
                    <div>
                      <CardTitle className={cn("text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                        <span>Treatment Uplift Comparison</span>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className={cn("w-3.5 h-3.5 cursor-pointer", isLight ? "text-slate-400 hover:text-slate-600" : "text-slate-400 hover:text-slate-200")} />
                            </TooltipTrigger>
                            <TooltipContent className={cn("text-xs", isLight ? "bg-white text-slate-900 border-slate-200 shadow-md" : "bg-slate-900 border-slate-700 text-white")}>
                              <p>Incremental lift of each channel over the counterfactual baseline ({comparisonBaseline})</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </CardTitle>
                      <p className={cn("text-[11px] mt-0.5", isLight ? "text-slate-500" : "text-slate-400")}>
                        Select a treatment to see segment-level impact
                      </p>
                    </div>

                    {/* Baseline Dropdown Selector */}
                    <div className="relative">
                      <button 
                        onClick={() => setIsBaselineDropdownOpen(!isBaselineDropdownOpen)}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer shadow-xs",
                          isLight
                            ? "bg-slate-50 hover:bg-slate-100 border-slate-300 text-slate-800 hover:border-slate-400"
                            : "bg-slate-950 border-slate-800 text-slate-200 hover:border-slate-700"
                        )}
                      >
                        <span>vs {comparisonBaseline}</span>
                        <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", isBaselineDropdownOpen && "rotate-180", isLight ? "text-slate-500" : "text-slate-400")} />
                      </button>

                      {/* Dropdown Menu */}
                      <AnimatePresence>
                        {isBaselineDropdownOpen && (
                          <motion.div
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 5 }}
                            className={cn(
                              "absolute right-0 top-full mt-1.5 w-48 rounded-xl border p-1 z-30 shadow-xl backdrop-blur-md",
                              isLight ? "bg-white border-slate-200 text-slate-900 shadow-slate-300/50" : "bg-[#090D18] border-slate-800 text-white"
                            )}
                          >
                            <button
                              onClick={() => {
                                setComparisonBaseline('No Action');
                                setIsBaselineDropdownOpen(false);
                              }}
                              className={cn(
                                "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center justify-between cursor-pointer transition-colors",
                                comparisonBaseline === 'No Action'
                                  ? isLight ? "bg-indigo-50 text-indigo-900 font-bold" : "bg-indigo-950/70 text-indigo-300"
                                  : isLight ? "hover:bg-slate-100 text-slate-700" : "hover:bg-slate-900 text-slate-300"
                              )}
                            >
                              <div>
                                <span className="block font-bold">vs No Action</span>
                                <span className={cn("text-[9.5px]", isLight ? "text-slate-500" : "text-slate-400")}>Organic baseline (48%)</span>
                              </div>
                              {comparisonBaseline === 'No Action' && <Check className={cn("w-3.5 h-3.5", isLight ? "text-indigo-600" : "text-indigo-400")} />}
                            </button>
                            <button
                              onClick={() => {
                                setComparisonBaseline('Standard Rules');
                                setIsBaselineDropdownOpen(false);
                              }}
                              className={cn(
                                "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center justify-between cursor-pointer transition-colors mt-0.5",
                                comparisonBaseline === 'Standard Rules'
                                  ? isLight ? "bg-indigo-50 text-indigo-900 font-bold" : "bg-indigo-950/70 text-indigo-300"
                                  : isLight ? "hover:bg-slate-100 text-slate-700" : "hover:bg-slate-900 text-slate-300"
                              )}
                            >
                              <div>
                                <span className="block font-bold">vs Standard Rules</span>
                                <span className={cn("text-[9.5px]", isLight ? "text-slate-500" : "text-slate-400")}>Heuristic retry rules (56%)</span>
                              </div>
                              {comparisonBaseline === 'Standard Rules' && <Check className={cn("w-3.5 h-3.5", isLight ? "text-indigo-600" : "text-indigo-400")} />}
                            </button>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  {/* 5 Selectable Treatment Option Cards */}
                  <div className="grid grid-cols-5 gap-2">
                    {treatments.map((t) => {
                      const Icon = t.icon;
                      const isSelected = selectedTreatment === t.id || (t.isBaseline && selectedTreatment === 'Baseline');

                      return (
                        <motion.div
                          key={t.id}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          onClick={() => setSelectedTreatment(t.id === 'Baseline' ? 'Baseline' : t.name)}
                          className={cn(
                            'relative p-2.5 rounded-xl cursor-pointer transition-all duration-200 flex flex-col justify-between select-none shadow-xs',
                            isSelected
                              ? isLight
                                ? t.name === 'WhatsApp'
                                  ? 'bg-emerald-50/90 border-2 border-emerald-500 text-emerald-950 shadow-emerald-100 ring-1 ring-emerald-500/40'
                                  : t.name === 'Retry'
                                  ? 'bg-blue-50/90 border-2 border-blue-500 text-blue-950 shadow-blue-100 ring-1 ring-blue-500/40'
                                  : t.name === 'Voice Call'
                                  ? 'bg-purple-50/90 border-2 border-purple-500 text-purple-950 shadow-purple-100 ring-1 ring-purple-500/40'
                                  : t.name === 'Incentive Link'
                                  ? 'bg-amber-50/90 border-2 border-amber-500 text-amber-950 shadow-amber-100 ring-1 ring-amber-500/40'
                                  : 'bg-slate-100 border-2 border-slate-500 text-slate-900'
                                : t.name === 'WhatsApp'
                                ? 'bg-[#0F1E1A] border-2 border-emerald-500/80 ring-1 ring-emerald-500/30 text-white'
                                : t.name === 'Retry'
                                ? 'bg-[#0E1B2E] border-2 border-blue-500/80 ring-1 ring-blue-500/30 text-white'
                                : t.name === 'Voice Call'
                                ? 'bg-[#18112C] border-2 border-purple-500/80 ring-1 ring-purple-500/30 text-white'
                                : t.name === 'Incentive Link'
                                ? 'bg-[#22170D] border-2 border-amber-500/80 ring-1 ring-amber-500/30 text-white'
                                : 'bg-slate-900/90 border-2 border-slate-600 text-white'
                              : isLight
                              ? 'bg-slate-50/80 border border-slate-200 hover:border-slate-300 hover:bg-slate-100 text-slate-800'
                              : 'bg-[#0D1424]/90 border border-slate-800 hover:border-slate-700 hover:bg-[#121B30] text-slate-300'
                          )}
                        >
                          {/* Top Right Green Checkmark for Active Selection */}
                          {isSelected && (
                            <div className={cn(
                              "absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center shadow-md ring-2",
                              isLight ? "ring-white" : "ring-[#0B101D]"
                            )}>
                              <CheckCircle2 className="w-3 h-3 fill-emerald-500 text-white" />
                            </div>
                          )}

                          {/* Top row: Icon + Name */}
                          <div className="flex items-center gap-1.5">
                            <Icon className={cn('w-3.5 h-3.5 shrink-0', t.iconColor)} />
                            <span className={cn(
                              "text-[10px] font-bold truncate",
                              isLight ? "text-slate-800" : "text-slate-200"
                            )}>
                              {t.name}
                            </span>
                          </div>

                          {/* Big Value */}
                          <div className="my-1.5 text-center">
                            <span className={cn(
                              "text-lg sm:text-xl font-black tabular-nums tracking-tight",
                              isLight ? "text-slate-900" : "text-white"
                            )}>
                              {t.prob}%
                            </span>
                          </div>

                          {/* Bottom Uplift Badge */}
                          <div className="text-center">
                            {t.isBaseline ? (
                              <span className={cn("text-[9.5px] font-bold", isLight ? "text-slate-500" : "text-slate-400")}>
                                Baseline
                              </span>
                            ) : (
                              <span 
                                className="text-[10px] font-black" 
                                style={{ color: t.color }}
                              >
                                {t.upliftLabel}
                              </span>
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>

                  {/* Bar Chart Area */}
                  <div className="pt-2">
                    <div className={cn("flex items-center justify-between text-[11px] font-semibold mb-2", isLight ? "text-slate-600" : "text-slate-400")}>
                      <span>Recovery Probability (%)</span>
                      <span className="flex items-center gap-1 text-[10.5px]">
                        <span>Hover for details</span>
                        <Info className="w-3 h-3 text-slate-400" />
                      </span>
                    </div>

                    <div className="h-48 w-full relative">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart 
                          data={treatments} 
                          margin={{ top: 22, right: 10, left: -20, bottom: 0 }}
                          onMouseMove={(state) => {
                            if (state && state.activePayload && state.activePayload.length > 0) {
                              setHoveredBar(state.activePayload[0].payload.name);
                            }
                          }}
                          onMouseLeave={() => setHoveredBar(null)}
                        >
                          <XAxis 
                            dataKey="name" 
                            stroke={isLight ? '#475569' : '#64748B'} 
                            fontSize={11} 
                            tickLine={false} 
                            axisLine={{ stroke: isLight ? '#CBD5E1' : '#1E293B' }} 
                          />
                          <YAxis 
                            stroke={isLight ? '#475569' : '#64748B'} 
                            fontSize={10.5} 
                            tickLine={false} 
                            axisLine={{ stroke: isLight ? '#CBD5E1' : '#1E293B' }} 
                            domain={[0, 100]} 
                            ticks={[0, 25, 50, 75, 100]} 
                            tickFormatter={(v) => `${v}%`} 
                          />
                          <RechartsTooltip
                            cursor={{ fill: isLight ? 'rgba(0, 0, 0, 0.04)' : 'rgba(255, 255, 255, 0.08)', radius: 8 }}
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const data = payload[0].payload as TreatmentOption;
                                return (
                                  <div className={cn(
                                    "p-3 rounded-xl border shadow-2xl backdrop-blur-xl text-xs space-y-1 min-w-[170px] z-50 ring-1",
                                    isLight
                                      ? "bg-white border-slate-200 text-slate-800 ring-slate-100 shadow-slate-200"
                                      : "bg-[#090D16] border-slate-700 text-white ring-white/10"
                                  )}>
                                    <div className={cn(
                                      "font-bold text-[12.5px] flex items-center justify-between border-b pb-1.5",
                                      isLight ? "text-slate-900 border-slate-200" : "text-white border-slate-800"
                                    )}>
                                      <span>{data.name}</span>
                                      <span 
                                        className="w-2.5 h-2.5 rounded-full" 
                                        style={{ backgroundColor: data.color }} 
                                      />
                                    </div>
                                    <div className="flex items-center justify-between pt-0.5">
                                      <span className={isLight ? "text-slate-500" : "text-slate-400"}>Recovery Probability:</span>
                                      <span className="font-extrabold tabular-nums text-xs" style={{ color: data.color }}>
                                        {data.prob}%
                                      </span>
                                    </div>
                                    <div className="flex items-center justify-between text-[10.5px]">
                                      <span className={isLight ? "text-slate-500" : "text-slate-400"}>Causal Impact:</span>
                                      <span className={cn("font-bold", isLight ? "text-emerald-700" : "text-emerald-400")}>
                                        {data.isBaseline ? `Baseline Reference (${comparisonBaseline})` : `+${data.uplift}% uplift`}
                                      </span>
                                    </div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Bar 
                            dataKey="prob" 
                            radius={[6, 6, 0, 0]} 
                            isAnimationActive={true} 
                            animationDuration={600}
                            label={(props: any) => {
                              const { x, y, width, value } = props;
                              return (
                                <text
                                  x={x + width / 2}
                                  y={y - 8}
                                  fill={isLight ? '#0F172A' : '#F8FAFC'}
                                  textAnchor="middle"
                                  dominantBaseline="middle"
                                  fontSize={11.5}
                                  fontWeight={800}
                                  style={{ fontWeight: 800, fill: isLight ? '#0F172A' : '#F8FAFC' }}
                                >
                                  {value}%
                                </text>
                              );
                            }}
                          >
                            {treatments.map((entry) => {
                              const isHovered = hoveredBar === entry.name;
                              const isSelected = selectedTreatment === entry.name || (entry.isBaseline && selectedTreatment === 'Baseline');

                              return (
                                <Cell 
                                  key={entry.id} 
                                  fill={entry.color}
                                  cursor="pointer"
                                  opacity={hoveredBar ? (isHovered ? 1 : 0.6) : 1}
                                  stroke={isSelected ? (isLight ? '#0F172A' : '#FFFFFF') : 'none'}
                                  strokeWidth={isSelected ? 2 : 0}
                                  onClick={() => setSelectedTreatment(entry.id === 'Baseline' ? 'Baseline' : entry.name)}
                                />
                              );
                            })}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </Card>
              </div>

              {/* Segment Impact for Selected Treatment */}
              <div className="lg:col-span-5">
                <Card className={cn(
                  "p-4 sm:p-5 rounded-2xl space-y-3.5 flex flex-col justify-between shadow-2xl h-full transition-colors border",
                  isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white"
                )}>
                  <div>
                    <div className={cn("flex items-center justify-between pb-2.5 border-b", isLight ? "border-slate-100" : "border-slate-800/80")}>
                      <CardTitle className={cn("text-sm font-bold", isLight ? "text-slate-900" : "text-white")}>
                        Segment Impact <span className={cn("font-bold", isLight ? "text-indigo-700" : "text-indigo-400")}>[{selectedTreatment}]</span>
                      </CardTitle>
                      <span className={cn(
                        "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                        isLight ? "text-indigo-700 bg-indigo-50 border-indigo-200" : "text-indigo-300 bg-indigo-500/10 border-indigo-500/30"
                      )}>
                        Top Uplift Segments
                      </span>
                    </div>
                    <p className={cn("text-[11px] mt-1", isLight ? "text-slate-500" : "text-slate-400")}>
                      Top customer segments where {selectedTreatment} demonstrates highest incremental lift vs {comparisonBaseline}
                    </p>

                    <div className="mt-4 space-y-3">
                      {currentSegmentImpacts.map((seg, i) => (
                        <div key={i} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className={cn("font-semibold text-[11px]", isLight ? "text-slate-800" : "text-slate-300")}>{seg.segment}</span>
                            <div className="flex items-center gap-2">
                              <span className={cn("font-extrabold tabular-nums text-xs", isLight ? "text-emerald-700" : "text-emerald-400")}>{seg.uplift}</span>
                              <span className={cn("text-[9.5px]", isLight ? "text-slate-500" : "text-slate-500")}>{seg.impact}</span>
                            </div>
                          </div>
                          <div className={cn("h-1.5 w-full rounded-full overflow-hidden", isLight ? "bg-slate-200" : "bg-slate-800/80")}>
                            <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: seg.width }}
                              transition={{ duration: 0.8, delay: i * 0.08 }}
                              className={`h-full ${seg.color} rounded-full`} 
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button className={cn(
                    "text-xs font-semibold pt-2 text-left block cursor-pointer transition-colors",
                    isLight ? "text-indigo-600 hover:text-indigo-800 hover:underline" : "text-indigo-400 hover:text-indigo-300 hover:underline"
                  )}>
                    View all 14 causal segments →
                  </button>
                </Card>
              </div>
            </div>

            {/* Causal Decision Leaderboard — Multi-Treatment Optimization */}
            <Card className={cn(
              "p-4 sm:p-5 rounded-2xl space-y-4 border shadow-2xl transition-colors",
              isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white"
            )}>
              <div className={cn("flex flex-wrap items-center justify-between gap-3 border-b pb-3", isLight ? "border-slate-100" : "border-slate-800")}>
                <div>
                  <CardTitle className="text-sm font-bold flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <span>Causal Decision Leaderboard — Multi-Treatment Optimization</span>
                    <span className={cn("text-xs font-mono font-normal", isLight ? "text-slate-500" : "text-slate-400")}>
                      (Evaluated for Case {heroDecision.caseId} • {formatINR(heroTx.amount)})
                    </span>
                  </CardTitle>
                  <p className={cn("text-[11px] mt-0.5", isLight ? "text-slate-500" : "text-slate-400")}>
                    Comparing natural recovery baseline against 5 active treatments. WAPSI selects the action maximizing Expected Net Recovery Value, NOT raw recovery probability.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className={cn(
                    "text-xs font-bold gap-1.5 rounded-xl cursor-pointer shadow-sm",
                    isLight ? "border-slate-300 bg-slate-50 text-slate-800 hover:bg-slate-100" : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
                  )}
                  onClick={() => openCounterfactualModal(heroDecision.caseId)}
                >
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  <span>Open What-If Simulator</span>
                </Button>
              </div>

              <div className={cn("overflow-x-auto rounded-xl border", isLight ? "border-slate-200 bg-white" : "border-slate-800/80 bg-slate-950/50")}>
                <table className="w-full text-left text-[11px] border-collapse">
                  <thead>
                    <tr className={cn(
                      "border-b font-bold uppercase tracking-wider text-[10px]",
                      isLight ? "bg-slate-50 border-slate-200 text-slate-500" : "border-slate-800 text-slate-400 bg-slate-900/90"
                    )}>
                      <th className="py-2.5 px-3">Treatment Action</th>
                      <th className="py-2.5 px-3">P(Recovery)</th>
                      <th className="py-2.5 px-3">Incremental Uplift (τ)</th>
                      <th className="py-2.5 px-3">Gross Value</th>
                      <th className="py-2.5 px-3">Intervention Cost</th>
                      <th className="py-2.5 px-3">Expected Net Value</th>
                      <th className="py-2.5 px-3">Confidence (90% Conformal)</th>
                      <th className="py-2.5 px-3 text-right">Engine Verdict</th>
                    </tr>
                  </thead>
                  <tbody className={cn("divide-y", isLight ? "divide-slate-100" : "divide-slate-800/60")}>
                    {(heroDecision.actionScores || []).map((score) => {
                      const isSelected = score.action === (heroDecision.recommendedAction || heroDecision.bestAction);
                      const isBaseline = score.action === 'NO_ACTION';
                      const grossVal = score.grossRecoveredValue ?? Math.round(score.recoveryProbability * heroTx.amount);
                      const totalCost = score.totalCost ?? (score.interventionCost ?? 0);
                      const netVal = score.expectedNetRecoveryValue ?? (grossVal - totalCost);
                      const confInterval = score.confidence ? [Math.round((score.confidence - 0.05) * 100), Math.round((score.confidence + 0.04) * 100)] : [88, 96];

                      return (
                        <tr
                          key={score.action}
                          className={cn(
                            "transition-colors",
                            isSelected
                              ? (isLight ? "bg-indigo-50/80 font-bold" : "bg-indigo-950/40 font-bold")
                              : (isLight ? "hover:bg-slate-50" : "hover:bg-slate-900/40")
                          )}
                        >
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <span className={cn(isSelected ? (isLight ? "text-indigo-950 font-black" : "text-indigo-300 font-black") : (isLight ? "text-slate-800" : "text-slate-300"))}>
                                {score.label}
                              </span>
                              {isSelected && (
                                <span className={cn(
                                  "text-[9px] px-1.5 py-0.2 rounded font-mono font-bold border",
                                  isLight ? "bg-indigo-100 text-indigo-800 border-indigo-300" : "bg-indigo-500/20 text-indigo-300 border-indigo-500/40"
                                )}>
                                  SELECTED
                                </span>
                              )}
                            </div>
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono font-bold tabular-nums", isLight ? "text-slate-900" : "text-white")}>
                            {Math.round(score.recoveryProbability * 100)}%
                          </td>
                          <td className="py-2.5 px-3 font-mono font-bold tabular-nums">
                            {isBaseline ? (
                              <span className="text-slate-500">—</span>
                            ) : (
                              <span className={isLight ? "text-emerald-700" : "text-emerald-400"}>
                                +{Math.round(score.incrementalUplift * 100)}%
                              </span>
                            )}
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono tabular-nums", isLight ? "text-slate-700" : "text-slate-300")}>
                            {formatINR(grossVal)}
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono tabular-nums", isLight ? "text-rose-700 font-semibold" : "text-rose-400 font-semibold")}>
                            {totalCost > 0 ? `-${formatINR(totalCost)}` : '₹0'}
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono font-black tabular-nums text-xs", isLight ? "text-emerald-700" : "text-emerald-400")}>
                            {formatINR(netVal)}
                          </td>
                          <td className={cn("py-2.5 px-3 font-mono text-[10px]", isLight ? "text-slate-600" : "text-slate-400")}>
                            {isBaseline ? 'Baseline Reference' : `${Math.round((score.confidence || 0.92) * 100)}% [${confInterval.join('-')}%]`}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {isSelected ? (
                              <span className={cn(
                                "px-2 py-0.5 rounded text-[10px] font-bold border inline-flex items-center gap-1",
                                isLight ? "bg-emerald-100 text-emerald-800 border-emerald-300" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                              )}>
                                <CheckCircle2 className="w-3 h-3" />
                                <span>Optimal Net Value</span>
                              </span>
                            ) : isBaseline ? (
                              <span className={cn("text-[10px]", isLight ? "text-slate-500" : "text-slate-500")}>
                                Counterfactual Ref
                              </span>
                            ) : (
                              <span className={cn("text-[10px]", isLight ? "text-slate-500" : "text-slate-400")}>
                                Suboptimal Net Value
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Why This Decision vs Why Not Alternatives Deep Dive */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div className={cn(
                  "p-3.5 rounded-xl border space-y-2",
                  isLight ? "bg-emerald-50/70 border-emerald-200" : "bg-emerald-950/20 border-emerald-500/30"
                )}>
                  <span className={cn("text-xs font-bold flex items-center gap-1.5", isLight ? "text-emerald-950" : "text-emerald-300")}>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    Why {heroDecision.recommendedActionLabel || heroDecision.bestActionLabel}? (Causal Rationale)
                  </span>
                  <ul className="space-y-1 text-[11px]">
                    {(heroDecision.decisionReasons || [
                      '+28.6% incremental causal uplift over organic holdout rate (48%).',
                      'Expected Net Recovery Value of ₹6,880 is highest among all compliant actions.',
                      'Action cost (₹6.00) preserves 99.9% of recovered value.',
                      'All 5 policy governance and regulatory constraints passed.'
                    ]).map((reason, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span className={isLight ? "text-slate-800" : "text-slate-200"}>{reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className={cn(
                  "p-3.5 rounded-xl border space-y-2",
                  isLight ? "bg-amber-50/70 border-amber-200" : "bg-amber-950/20 border-amber-500/30"
                )}>
                  <span className={cn("text-xs font-bold flex items-center gap-1.5", isLight ? "text-amber-950" : "text-amber-300")}>
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    Why Not The Alternatives? (Economic Disqualification)
                  </span>
                  <ul className="space-y-1 text-[11px]">
                    {(heroDecision.rejectedAlternatives || [
                      { reason: 'Incentive Offer: Achieves 87.7% raw recovery but ₹1,605 discount cost erodes net recovery value down to ₹6,289 (₹591 worse than WhatsApp).' },
                      { reason: 'IVR Voice Call: High recovery (78.9%) but telephone fees & fatigue penalty reduce net value to ₹6,406.' },
                      { reason: 'Smart Retry: Zero direct fees but produces lower recovery (71.5%, net ₹6,434) due to unresolved customer-side issue.' }
                    ]).map((alt, idx) => {
                      const text = typeof alt === 'string' ? alt : alt.reason;
                      return (
                        <li key={idx} className="flex items-start gap-1.5">
                          <span className="text-amber-500 font-bold">•</span>
                          <span className={isLight ? "text-slate-800" : "text-slate-200"}>{text}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>
            </Card>
          </motion.div>
        )}

        {/* VIEW 3: TIMING INTELLIGENCE TAB */}
        {activeTab === 'timing' && (
          <motion.div
            key="timing-view"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-8">
                <Card className={cn("p-4 sm:p-5 rounded-2xl space-y-3 shadow-2xl transition-colors border", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white")}>
                  <div className="flex items-center justify-between pb-1">
                    <CardTitle className={cn("text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                      <span>Hazard Survival Timing Curve ({selectedTreatment === 'Baseline' ? 'Retry' : selectedTreatment})</span>
                      <Info className={cn("w-3.5 h-3.5", isLight ? "text-slate-400" : "text-slate-400")} />
                    </CardTitle>
                  </div>
                  <p className={cn("text-[11px]", isLight ? "text-slate-500" : "text-slate-400")}>
                    Continuous-time hazard function optimizing recovery payoff window
                  </p>

                  <div className="h-60 my-2 relative">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart 
                        data={timingPoints} 
                        margin={{ top: 28, right: 12, left: -22, bottom: 0 }}
                        onMouseMove={(e) => {
                          if (e && e.activeLabel) {
                            setActiveTimingHour(e.activeLabel);
                          }
                        }}
                        onMouseLeave={() => setActiveTimingHour('18h')}
                      >
                        <defs>
                          <linearGradient id="timingPurpleGradientBig" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#A855F7" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#6366F1" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="hour" stroke={isLight ? '#475569' : '#64748B'} fontSize={11} tickLine={false} axisLine={{ stroke: isLight ? '#CBD5E1' : '#1E293B' }} />
                        <YAxis stroke={isLight ? '#475569' : '#64748B'} fontSize={10.5} tickLine={false} axisLine={{ stroke: isLight ? '#CBD5E1' : '#1E293B' }} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} />
                        <ReferenceLine x={activeTimingHour} stroke="#A855F7" strokeDasharray="3 3" strokeWidth={1.8} strokeOpacity={0.9} />
                        <RechartsTooltip
                          cursor={false}
                          content={({ active, payload }) => {
                            if (active && payload && payload.length) {
                              const data = payload[0].payload;
                              return (
                                <div className={cn(
                                  "rounded-xl px-2.5 py-1 text-center shadow-xl ring-1 pointer-events-none -mt-4 transition-colors",
                                  isLight
                                    ? "bg-white border-2 border-purple-500 text-slate-900 ring-purple-200 shadow-purple-200"
                                    : "bg-[#0B0F1E]/95 border border-purple-500/80 text-white ring-purple-500/40 shadow-purple-950/80"
                                )}>
                                  <span className={cn("text-[10.5px] font-bold block leading-tight", isLight ? "text-purple-700" : "text-purple-300")}>{data.hour}</span>
                                  <span className={cn("text-xs font-black block leading-tight", isLight ? "text-slate-900" : "text-white")}>{data.prob}%</span>
                                </div>
                              );
                            }
                            return null;
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="prob"
                          stroke="#A855F7"
                          strokeWidth={2.8}
                          fill="url(#timingPurpleGradientBig)"
                          dot={(props: any) => {
                            const { cx, cy, payload } = props;
                            const isActive = payload.hour === activeTimingHour;
                            return (
                              <g key={`dot-${payload.hour}`}>
                                {isActive && (
                                  <>
                                    <circle cx={cx} cy={cy} r={8} fill="#A855F7" fillOpacity={0.25} className="animate-ping" />
                                    <circle cx={cx} cy={cy} r={5} fill="#A855F7" fillOpacity={0.5} />
                                    <circle cx={cx} cy={cy} r={3} fill="#FFFFFF" />
                                  </>
                                )}
                              </g>
                            );
                          }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>

                  <div className={cn(
                    "p-3 rounded-xl text-xs flex items-center justify-between gap-3 border transition-colors shadow-xs",
                    isLight
                      ? "bg-purple-50/80 border-purple-200 text-slate-900"
                      : "bg-[#0F1424] border-purple-500/30 text-slate-300"
                  )}>
                    <div className="flex items-center gap-2.5">
                      <div className={cn(
                        "w-8 h-8 rounded-full border flex items-center justify-center shrink-0",
                        isLight
                          ? "bg-purple-100 border-purple-300 text-purple-700"
                          : "bg-purple-950/70 border border-purple-500/50 text-purple-300"
                      )}>
                        <Clock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                      </div>
                      <div>
                        <span className={cn(
                          "font-semibold block text-xs",
                          isLight ? "text-slate-900" : "text-slate-200"
                        )}>
                          Recommended action: <strong className={isLight ? "text-purple-700 font-extrabold" : "text-purple-300 font-bold"}>Retry in 18 hours</strong>
                        </span>
                        <p className={cn("text-[10.5px]", isLight ? "text-slate-600" : "text-slate-400")}>Issuer success rate peaks at 72% in this window</p>
                      </div>
                    </div>
                    <button onClick={() => setShowWhyTimingModal(true)} className={cn(
                      "px-3 py-1.5 rounded-lg border text-xs font-semibold shadow-xs cursor-pointer transition-colors",
                      isLight ? "bg-white hover:bg-slate-100 border-slate-300 text-slate-800" : "bg-slate-900 border-slate-800 text-slate-300 hover:text-white"
                    )}>
                      Why 18 hours? ⓘ
                    </button>
                  </div>
                </Card>
              </div>

              <div className="lg:col-span-4 space-y-4">
                <Card className={cn("p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-3 transition-colors", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white")}>
                  <CardTitle className={cn("text-sm font-bold", isLight ? "text-slate-900" : "text-white")}>Banking Batch Windows</CardTitle>
                  <div className="space-y-2 text-xs">
                    <div className={cn("p-2.5 rounded-xl border flex justify-between", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                      <span className={isLight ? "text-slate-700 font-medium" : "text-slate-300"}>Overnight Salary Settlement</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">06:00 – 09:00 AM</span>
                    </div>
                    <div className={cn("p-2.5 rounded-xl border flex justify-between", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                      <span className={isLight ? "text-slate-700 font-medium" : "text-slate-300"}>NACH/e-Mandate Clearing</span>
                      <span className="font-bold text-blue-600 dark:text-cyan-400">11:00 – 02:00 PM</span>
                    </div>
                    <div className={cn("p-2.5 rounded-xl border flex justify-between", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                      <span className={isLight ? "text-slate-700 font-medium" : "text-slate-300"}>UPI Velocity Cooldown</span>
                      <span className="font-bold text-purple-600 dark:text-purple-400">4 Hours minimum</span>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          </motion.div>
        )}

        {/* VIEW 4: NETWORK PRIOR TAB */}
        {activeTab === 'network' && (
          <motion.div
            key="network-view"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-7">
                <Card className={cn("p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-3.5 transition-colors", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white")}>
                  <div className={cn("flex items-center justify-between pb-2 border-b", isLight ? "border-slate-100" : "border-slate-800/80")}>
                    <CardTitle className={cn("text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                      <Layers className="w-4 h-4 text-indigo-500" />
                      <span>Razorpay Network Hierarchical Prior</span>
                    </CardTitle>
                    <span className={cn("text-[10px] font-bold px-2.5 py-0.5 rounded-full border", isLight ? "text-indigo-700 bg-indigo-50 border-indigo-200" : "text-indigo-300 bg-indigo-500/10 border-indigo-500/30")}>
                      12.8M Network Priors
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div className="space-y-2">
                      <div className={cn("p-3 rounded-xl border text-center shadow-xs", isLight ? "bg-purple-50/70 border-purple-200" : "bg-[#14122E] border-purple-500/30")}>
                        <span className={cn("text-[10px] font-extrabold uppercase tracking-wider block", isLight ? "text-purple-700" : "text-purple-300")}>RAZORPAY NETWORK</span>
                        <span className={cn("text-base font-black tabular-nums block mt-0.5", isLight ? "text-slate-900" : "text-white")}>12,842,931</span>
                        <span className="text-[9px] text-slate-500 block">historical cases</span>
                      </div>
                      <div className="flex flex-col items-center">
                        <div className={cn("w-[1px] h-2", isLight ? "bg-indigo-300" : "bg-indigo-500/50")} />
                        <span className={cn("text-[9px] font-extrabold px-2 py-0.5 rounded-md border", isLight ? "text-indigo-700 bg-indigo-50 border-indigo-200" : "text-indigo-300 bg-indigo-950/80 border-indigo-500/40")}>NETWORK PRIOR</span>
                        <div className={cn("w-[1px] h-2", isLight ? "bg-indigo-300" : "bg-indigo-500/50")} />
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 text-center">
                        <div className={cn("p-2 rounded-lg border shadow-xs", isLight ? "bg-blue-50/70 border-blue-200" : "bg-[#0E1A2E] border-cyan-500/30")}>
                          <span className={cn("text-[10px] font-bold block", isLight ? "text-slate-800" : "text-slate-300")}>Merchant A</span>
                          <span className={cn("text-xs font-black tabular-nums block", isLight ? "text-blue-700" : "text-cyan-400")}>200 cases</span>
                          <span className="text-[8.5px] text-slate-500 block mt-1">Less data (Network leads)</span>
                        </div>
                        <div className={cn("p-2 rounded-lg border shadow-xs", isLight ? "bg-emerald-50/70 border-emerald-200" : "bg-[#0F221D] border-emerald-500/30")}>
                          <span className={cn("text-[10px] font-bold block", isLight ? "text-slate-800" : "text-slate-300")}>Merchant B</span>
                          <span className={cn("text-xs font-black tabular-nums block", isLight ? "text-emerald-700" : "text-emerald-400")}>2,000 cases</span>
                          <span className="text-[8.5px] text-slate-500 block mt-1">More data (Merchant leads)</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-center pt-1">
                        <div className={cn("w-[1px] h-2", isLight ? "bg-purple-300" : "bg-purple-500/50")} />
                        <div className={cn("w-full p-2.5 rounded-xl border text-center flex items-center justify-center gap-1.5 shadow-xs", isLight ? "bg-purple-50/80 border-purple-200" : "bg-[#14122E] border-purple-500/30")}>
                          <span>🛡️</span>
                          <div>
                            <span className={cn("text-[10px] font-bold block uppercase", isLight ? "text-purple-900" : "text-purple-200")}>FINAL BLENDED DECISION</span>
                            <span className="text-[9px] text-slate-500 block">Optimal shrinkage estimate</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3 flex flex-col justify-between">
                      <div className={cn("p-3.5 rounded-xl border space-y-2 shadow-xs", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                        <span className={cn("text-xs font-bold block", isLight ? "text-slate-800" : "text-slate-300")}>Signal Weighting</span>
                        <div className="relative pt-1 pb-1">
                          <div className={cn("h-2.5 w-full rounded-full flex overflow-hidden border", isLight ? "bg-slate-100 border-slate-200" : "bg-slate-900 border-slate-800")}>
                            <div className="w-[70%] bg-gradient-to-r from-purple-600 to-indigo-500" />
                            <div className="w-[30%] bg-gradient-to-r from-emerald-500 to-teal-400" />
                          </div>
                          <div className="absolute top-[2px] left-[70%] -translate-x-1/2 w-4 h-4 rounded-full bg-blue-500 border-2 border-white shadow-md" />
                        </div>
                        <div className="flex justify-between pt-1 text-xs">
                          <span className={cn("font-bold", isLight ? "text-purple-700" : "text-purple-400")}>70% Network</span>
                          <span className={cn("font-bold", isLight ? "text-emerald-700" : "text-emerald-400")}>30% Merchant</span>
                        </div>
                      </div>

                      <div className={cn("p-3.5 rounded-xl border shadow-xs", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                        <span className={cn("text-xs font-bold block mb-1", isLight ? "text-slate-900" : "text-white")}>Cold-Start Acceleration</span>
                        <p className={cn("text-[11px] leading-relaxed", isLight ? "text-slate-600" : "text-slate-300")}>
                          New merchants achieve <strong>+18.4% uplift on Day 1</strong> by borrowing statistical strength from 12.8M network episodes.
                        </p>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>

              <div className="lg:col-span-5 space-y-4">
                <Card className={cn("p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-3 transition-colors", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white")}>
                  <CardTitle className={cn("text-sm font-bold", isLight ? "text-slate-900" : "text-white")}>Cross-Merchant Transfer Learning</CardTitle>
                  <p className={cn("text-xs leading-relaxed", isLight ? "text-slate-600" : "text-slate-300")}>
                    WAPSI uses Empirical Bayes to shrink merchant estimates toward the network mean, dynamically adjusting weights as local merchant sample size increases.
                  </p>
                </Card>
              </div>
            </div>
          </motion.div>
        )}

        {/* VIEW 5: MODEL HEALTH TAB */}
        {activeTab === 'health' && (
          <motion.div
            key="health-view"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-7">
                <Card className={cn("p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-3.5 transition-colors", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white")}>
                  <div className={cn("p-3.5 rounded-xl border space-y-2 shadow-xs", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                    <span className={cn("text-xs font-bold block", isLight ? "text-slate-900" : "text-white")}>Uplift Model Performance</span>
                    <div className="grid grid-cols-12 gap-2 items-center">
                      <div className={cn("col-span-3 p-2.5 rounded-lg border text-center shadow-xs", isLight ? "bg-white border-slate-200" : "bg-[#090E1A] border-slate-800")}>
                        <span className={cn("text-[10px] font-bold uppercase block", isLight ? "text-slate-500" : "text-slate-400")}>AUUC</span>
                        <span className={cn("text-lg font-black tabular-nums block", isLight ? "text-cyan-700" : "text-cyan-400")}>
                          {modelHealth?.auuc ? Number(modelHealth.auuc).toFixed(3) : '0.784'}
                        </span>
                      </div>
                      <div className={cn("col-span-3 p-2.5 rounded-lg border text-center shadow-xs", isLight ? "bg-white border-slate-200" : "bg-[#090E1A] border-slate-800")}>
                        <span className={cn("text-[10px] font-bold uppercase block", isLight ? "text-slate-500" : "text-slate-400")}>QINI</span>
                        <span className={cn("text-lg font-black tabular-nums block", isLight ? "text-cyan-700" : "text-cyan-400")}>
                          {modelHealth?.qini ? Number(modelHealth.qini).toFixed(3) : '0.692'}
                        </span>
                      </div>
                      <div className="col-span-6 h-14">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={[{ v: 0.12 }, { v: 0.18 }, { v: 0.16 }, { v: 0.24 }, { v: 0.22 }, { v: 0.32 }, { v: 0.31 }, { v: 0.37 }]}>
                            <Area type="monotone" dataKey="v" stroke="#38BDF8" strokeWidth={2} fill="#38BDF8" fillOpacity={0.2} dot={{ r: 2 }} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border space-y-2 shadow-xs", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                    <span className={cn("text-xs font-bold block", isLight ? "text-slate-900" : "text-white")}>Confidence & Calibration</span>
                    <div className="flex justify-between text-xs">
                      <div>
                        <span className={cn("text-[10px] block", isLight ? "text-slate-500" : "text-slate-400")}>Median Confidence</span>
                        <span className={cn("text-base font-black tabular-nums block", isLight ? "text-emerald-700" : "text-emerald-400")}>
                          {modelHealth?.medianConfidence ? `${Math.round(modelHealth.medianConfidence * 100)}%` : '94%'}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className={cn("text-[10px] block", isLight ? "text-slate-500" : "text-slate-400")}>Conformal Coverage</span>
                        <span className={cn("text-base font-black tabular-nums block", isLight ? "text-emerald-700" : "text-emerald-400")}>
                          {modelHealth?.conformalCoverage ? `${(modelHealth.conformalCoverage * 100).toFixed(1)}%` : '91.2%'}
                        </span>
                      </div>
                    </div>
                    <div className="pt-1 pb-1 relative">
                      <div className={cn("h-2 w-full rounded-full border overflow-hidden", isLight ? "bg-slate-200 border-slate-300" : "bg-slate-900 border-slate-800")}>
                        <div 
                          className="h-full bg-gradient-to-r from-purple-600 via-indigo-500 to-blue-400 rounded-full" 
                          style={{ width: `${modelHealth?.conformalCoverage ? (modelHealth.conformalCoverage * 100) : 91.2}%` }} 
                        />
                      </div>
                      <div className={cn("absolute top-0 bottom-3 w-0.5 border-r border-dashed", isLight ? "border-slate-500" : "border-white")} style={{ left: '90%' }} />
                      <span className={cn("text-[9px] block text-center font-medium mt-1", isLight ? "text-slate-500" : "text-slate-400")}>90% Target</span>
                    </div>
                  </div>

                  <div className={cn("p-3.5 rounded-xl border space-y-2 shadow-xs", isLight ? "bg-slate-50 border-slate-200" : "bg-[#0D1424] border-slate-800")}>
                    <span className={cn("text-xs font-bold block", isLight ? "text-slate-900" : "text-white")}>Key Insights</span>
                    <ul className={cn("space-y-1 text-[11px]", isLight ? "text-slate-700" : "text-slate-300")}>
                      <li className="flex items-center gap-2">
                        <CheckCircle2 className={cn("w-3.5 h-3.5 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400")} />
                        <span>WhatsApp and Incentive show highest uplift.</span>
                      </li>
                      <li className="flex items-center gap-2">
                        <CheckCircle2 className={cn("w-3.5 h-3.5 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400")} />
                        <span>Action early in the window for max recovery.</span>
                      </li>
                      <li className="flex items-center gap-2">
                        <CheckCircle2 className={cn("w-3.5 h-3.5 shrink-0", isLight ? "text-emerald-600" : "text-emerald-400")} />
                        <span>Network prior is contributing 70% for this merchant.</span>
                      </li>
                    </ul>
                  </div>
                </Card>
              </div>

              <div className="lg:col-span-5 space-y-4">
                <Card className={cn("p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-3.5 transition-colors", isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white")}>
                  <div className="flex items-center justify-between border-b pb-2.5">
                    <div>
                      <CardTitle className="text-sm font-bold flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-indigo-400" />
                        <span>Covariate Drift Monitor</span>
                      </CardTitle>
                      <span className="text-[10px] text-slate-400">
                        Population Stability Index (PSI) Testing
                      </span>
                    </div>
                    {(() => {
                      const currentDriftStatus = driftReport.status || driftReport.overallStatus;
                      return (
                        <span className={cn(
                          "px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border",
                          currentDriftStatus === 'STABLE'
                            ? (isLight ? "bg-emerald-50 text-emerald-800 border-emerald-300" : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40")
                            : currentDriftStatus === 'WARNING'
                            ? (isLight ? "bg-amber-50 text-amber-800 border-amber-300" : "bg-amber-500/20 text-amber-300 border-amber-500/40")
                            : (isLight ? "bg-rose-50 text-rose-800 border-rose-300" : "bg-rose-500/20 text-rose-300 border-rose-500/40")
                        )}>
                          {currentDriftStatus} (PSI {driftReport.psi})
                        </span>
                      );
                    })()}
                  </div>

                  <p className={cn("text-xs leading-relaxed", isLight ? "text-slate-600" : "text-slate-300")}>
                    Continuous two-sample Kolmogorov-Smirnov and PSI monitoring on incoming features. When <strong>CRITICAL</strong> drift is triggered, autonomous routing is halted and transactions escalate to Human Review.
                  </p>

                  {/* Interactive Drift Test Buttons */}
                  <div className="space-y-1.5 pt-1">
                    <span className={cn("text-[11px] font-bold block", isLight ? "text-slate-700" : "text-slate-300")}>
                      Simulate Production Feature Shift:
                    </span>
                    <div className="grid grid-cols-3 gap-1.5">
                      {(() => {
                        const currentDriftStatus = driftReport.status || driftReport.overallStatus;
                        return (
                          <>
                            <button
                              onClick={() => setDriftLevel('STABLE')}
                              className={cn(
                                "px-2 py-1.5 rounded-lg text-[10px] font-bold border transition-all cursor-pointer text-center",
                                currentDriftStatus === 'STABLE'
                                  ? "bg-emerald-600 text-white border-emerald-500 shadow-sm"
                                  : isLight ? "bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200" : "bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800"
                              )}
                            >
                              Stable (0.04)
                            </button>
                            <button
                              onClick={() => setDriftLevel('WARNING')}
                              className={cn(
                                "px-2 py-1.5 rounded-lg text-[10px] font-bold border transition-all cursor-pointer text-center",
                                currentDriftStatus === 'WARNING'
                                  ? "bg-amber-600 text-white border-amber-500 shadow-sm"
                                  : isLight ? "bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200" : "bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800"
                              )}
                            >
                              Warning (0.14)
                            </button>
                            <button
                              onClick={() => setDriftLevel('CRITICAL')}
                              className={cn(
                                "px-2 py-1.5 rounded-lg text-[10px] font-bold border transition-all cursor-pointer text-center",
                                currentDriftStatus === 'CRITICAL'
                                  ? "bg-rose-600 text-white border-rose-500 shadow-sm"
                                  : isLight ? "bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200" : "bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800"
                              )}
                            >
                              Critical (0.28)
                            </button>
                          </>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Feature Breakdown */}
                  <div className="space-y-1.5 pt-1">
                    <span className={cn("text-[10px] font-bold uppercase tracking-wider block", isLight ? "text-slate-500" : "text-slate-400")}>
                      Feature Stability Metrics
                    </span>
                    <div className="space-y-1 text-[11px]">
                      {Object.entries(driftReport.features || {
                        'Transaction Amount': { psi: 0.021, status: 'STABLE' as const },
                        'Prior Retry Count': { psi: 0.014, status: 'STABLE' as const },
                        'Attempt Hour (IST)': { psi: 0.018, status: 'STABLE' as const },
                        'Payment Method Type': { psi: 0.032, status: 'STABLE' as const },
                      }).map(([feat, data]) => {
                        const featureData = data as { psi: number; status: 'STABLE' | 'WARNING' | 'CRITICAL' };
                        return (
                          <div key={feat} className={cn(
                            "p-2 rounded-lg border flex items-center justify-between",
                            isLight ? "bg-slate-50 border-slate-200" : "bg-slate-950/60 border-slate-800"
                          )}>
                            <span className={cn("font-mono text-[10px]", isLight ? "text-slate-700" : "text-slate-300")}>{feat}</span>
                            <div className="flex items-center gap-2">
                              <span className={cn("font-mono font-bold text-[10px] tabular-nums", isLight ? "text-slate-800" : "text-slate-200")}>
                                PSI {featureData.psi.toFixed(3)}
                              </span>
                              <span className={cn(
                                "text-[9px] px-1.5 py-0.2 rounded font-bold uppercase border",
                                featureData.status === 'STABLE' 
                                  ? (isLight ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "text-emerald-300 bg-emerald-500/10 border-emerald-500/20")
                                  : featureData.status === 'WARNING'
                                  ? (isLight ? "bg-amber-50 text-amber-800 border-amber-200" : "text-amber-300 bg-amber-500/10 border-amber-500/20")
                                  : (isLight ? "bg-rose-50 text-rose-800 border-rose-200" : "text-rose-300 bg-rose-500/10 border-rose-500/20")
                              )}>
                                {featureData.status}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className={cn(
                    "p-3 rounded-xl border text-[11px] leading-relaxed",
                    (driftReport.status || driftReport.overallStatus) === 'CRITICAL'
                      ? (isLight ? "bg-rose-50 border-rose-200 text-rose-900" : "bg-rose-950/40 border-rose-500/40 text-rose-200")
                      : (isLight ? "bg-slate-50 border-slate-200 text-slate-700" : "bg-slate-900/60 border-slate-800 text-slate-300")
                  )}>
                    <strong>Enforced Action:</strong> {driftReport.actionTaken || driftReport.impactOnRouting}
                  </div>
                </Card>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Why 18 Hours Timing Modal */}
      <AnimatePresence>
        {showWhyTimingModal && (
          <div 
            className={cn("fixed inset-0 backdrop-blur-sm z-50 flex items-center justify-center p-4 transition-colors", isLight ? "bg-slate-900/40" : "bg-black/70")}
            onClick={() => setShowWhyTimingModal(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className={cn(
                "border rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl transition-colors",
                isLight ? "bg-white border-slate-200 text-slate-900 shadow-slate-900/20" : "bg-[#0D1322] border-purple-500/40 text-slate-200 shadow-purple-950/50"
              )}
            >
              <div className={cn("flex items-center justify-between border-b pb-3", isLight ? "border-slate-100" : "border-slate-800")}>
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "w-7 h-7 rounded-xl border flex items-center justify-center",
                    isLight ? "bg-purple-50 border-purple-200 text-purple-700" : "bg-purple-950 border-purple-500/40 text-purple-400"
                  )}>
                    <Clock className="w-4 h-4" />
                  </div>
                  <h3 className={cn("text-sm font-bold", isLight ? "text-slate-900" : "text-white")}>Why 18 Hours for Retry?</h3>
                </div>
                <button 
                  onClick={() => setShowWhyTimingModal(false)}
                  className={cn("text-base font-bold cursor-pointer transition-colors", isLight ? "text-slate-400 hover:text-slate-700" : "text-slate-400 hover:text-white")}
                >
                  ✕
                </button>
              </div>

              <div className={cn("space-y-2.5 text-xs leading-relaxed", isLight ? "text-slate-700" : "text-slate-300")}>
                <p>
                  Our continuous-time survival hazard model analyzed <strong>1.4M auto-debit failure cycles</strong> across major Indian banks (HDFC, ICICI, SBI).
                </p>
                <div className={cn(
                  "p-3 rounded-xl border space-y-1",
                  isLight ? "bg-purple-50/80 border-purple-200 text-slate-900" : "bg-purple-950/30 border-purple-500/30 text-slate-300"
                )}>
                  <span className={cn("font-bold text-xs block", isLight ? "text-purple-900" : "text-purple-300")}>Key Drivers of the 18h Peak:</span>
                  <ul className={cn("list-disc pl-4 space-y-1 text-[11px]", isLight ? "text-slate-700" : "text-slate-300")}>
                    <li><strong>Clearing Batch Alignment:</strong> Overnight salary and NEFT/RTGS credit batches clear between 06:00 and 09:00 AM.</li>
                    <li><strong>Issuer Retry Rate Limit:</strong> Immediate retries within 6 hours trigger temporary fraud velocity blocks (drop to 22%).</li>
                    <li><strong>Optimal Window (18h - 24h):</strong> Success probability reaches <strong>72%</strong> before decaying after 36 hours due to mandate expiration.</li>
                  </ul>
                </div>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  onClick={() => setShowWhyTimingModal(false)}
                  className="px-4 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-all cursor-pointer shadow-xs"
                >
                  Got it
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
