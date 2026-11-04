import React, { useState, useMemo } from 'react';
import { Topbar } from '../components/layout/Topbar';
import { MetricCard } from '../components/shared/MetricCard';
import { StatusBadge } from '../components/shared/StatusBadge';
import { ActionPill } from '../components/shared/ActionPill';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/Tooltip';
import { 
  Search, 
  Filter, 
  Sparkles, 
  Star, 
  ChevronLeft, 
  ChevronRight, 
  ArrowUpDown,
  ShieldAlert,
  Clock, 
  Layers,
  RefreshCw,
  CreditCard,
  Building2,
  TrendingUp,
  CheckCircle2,
  ArrowRight,
  Zap
} from 'lucide-react';
import { useRecoveryCases } from '../hooks/useRecovery';
import { useDemoStore } from '../store/demoStore';
import { formatINR, formatPercent } from '../lib/formatting';
import { cn } from '../lib/utils';
import { RecoveryCase } from '../types';
import { motion } from 'framer-motion';
import { OperatorApprovalModal } from '../components/recovery/OperatorApprovalModal';

export const RecoveryCenterPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'amount' | 'uplift' | 'confidence' | 'caseId' | 'none'>('none');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const [approvingCase, setApprovingCase] = useState<any | null>(null);
  const pageSize = 8;
  
  const { data: rawCases = [], isLoading } = useRecoveryCases(activeTab, undefined, searchQuery);
  const overviewMetrics = useDemoStore((state) => state.overviewMetrics);
  const openCaseDrawer = useDemoStore((state) => state.openCaseDrawer);
  const selectedCaseId = useDemoStore((state) => state.selectedCaseId);
  const approveCase = useDemoStore((state) => state.approveCase);
  const reviewCase = useDemoStore((state) => state.reviewCase);
  const allCases = useDemoStore((state) => state.cases);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  // Dynamic tab counts directly from the active dataset
  const tabCounts = useMemo(() => {
    return {
      All: allCases.length,
      Subscriptions: allCases.filter((c) => c.domain === 'SUBSCRIPTIONS').length,
      Checkout: allCases.filter((c) => c.domain === 'CHECKOUT').length,
      B2B: allCases.filter((c) => c.domain === 'RECEIVABLES_B2B').length,
      'Needs Review': allCases.filter((c) => c.status === 'REVIEW' || c.status === 'SCORED' || c.isOOD).length,
      'High Impact': allCases.filter((c) => c.amount > 5000 || c.incrementalUplift > 0.20).length,
      'Promise-to-Pay': allCases.filter((c) => c.recommendedAction === 'WHATSAPP' || c.recommendedAction === 'VOICE' || c.status === 'MONITORING').length,
    };
  }, [allCases]);

  const tabs = [
    { label: 'All', count: tabCounts.All, tooltip: 'All actionable recovery opportunities' },
    { label: 'Subscriptions', count: tabCounts.Subscriptions, tooltip: 'Recurring auto-debit and mandate failures' },
    { label: 'Checkout', count: tabCounts.Checkout, tooltip: 'One-time cart & e-commerce gateway drops' },
    { label: 'B2B', count: tabCounts.B2B, tooltip: 'Invoice receivables and high-ticket B2B mandates' },
    { label: 'Needs Review', count: tabCounts['Needs Review'], tooltip: 'Out-of-distribution or edge-case decisions flagged for human audit' },
    { label: 'High Impact', count: tabCounts['High Impact'], tooltip: 'High expected value or high uplift opportunities (> ₹5k or > 20% lift)' },
    { label: 'Promise-to-Pay', count: tabCounts['Promise-to-Pay'], tooltip: 'Customers with confirmed intent scheduled for reminder nudge' },
  ];

  // Sorting Logic
  const sortedCases = [...rawCases].sort((a, b) => {
    if (sortBy === 'amount') {
      return sortOrder === 'asc' ? a.amount - b.amount : b.amount - a.amount;
    }
    if (sortBy === 'uplift') {
      return sortOrder === 'asc' ? a.incrementalUplift - b.incrementalUplift : b.incrementalUplift - a.incrementalUplift;
    }
    if (sortBy === 'confidence') {
      return sortOrder === 'asc' ? a.decisionConfidence - b.decisionConfidence : b.decisionConfidence - a.decisionConfidence;
    }
    if (sortBy === 'caseId') {
      return sortOrder === 'asc' ? a.caseId.localeCompare(b.caseId) : b.caseId.localeCompare(a.caseId);
    }
    return 0;
  });

  const totalPages = Math.ceil(sortedCases.length / pageSize) || 1;
  const paginatedCases = sortedCases.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const handleSort = (column: 'amount' | 'uplift' | 'confidence' | 'caseId') => {
    if (sortBy === column) {
      if (sortOrder === 'desc') {
        setSortOrder('asc');
      } else {
        setSortBy('none');
      }
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-4 w-full"
    >
      <Topbar
        title="Recovery Center"
        subtitle="Mission Control for Causal Revenue Recovery"
      />

      {/* Top 4 KPI Cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-2.5 sm:gap-3">
        <MetricCard
          title="Revenue at Risk"
          value={formatINR(overviewMetrics.revenueAtRisk, true)}
          delta={`${formatPercent(overviewMetrics.revenueAtRiskDelta)}`}
          deltaType="warning"
          deltaSubtext="vs last 7 days"
          accentColor="rose"
          sparklineData={[14, 16, 15, 17, 18, 17, 18.4]}
          infoTooltip="Total gross transaction volume in failed state requiring causal action"
        />
        <MetricCard
          title="Recoverable (Actionable)"
          value={formatINR(overviewMetrics.recoverable, true)}
          delta={`${formatPercent(overviewMetrics.recoverableDelta)}`}
          deltaType="positive"
          deltaSubtext="vs last 7 days"
          accentColor="amber"
          sparklineData={[8, 9, 9.5, 10.2, 11, 11.5, 11.76]}
          infoTooltip="Volume where causal uplift model identifies positive payoff above No Action"
        />
        <MetricCard
          title="Incremental Recovery"
          value={formatINR(overviewMetrics.incrementalRecovery, true)}
          delta={`${formatPercent(overviewMetrics.incrementalRecoveryDelta)}`}
          deltaType="positive"
          deltaSubtext="vs baseline"
          accentColor="cyan"
          subtext="Value added by WAPSI"
          sparklineData={[1.2, 1.4, 1.6, 1.8, 1.9, 2.0, 2.14]}
          infoTooltip="Pure causal uplift generated above counterfactual baseline"
        />
        <MetricCard
          title="Actions Ready"
          value={String(allCases.length)}
          delta="+12.4%"
          deltaType="positive"
          deltaSubtext="vs last 7 days"
          accentColor="purple"
          subtext="91% median conf."
          sparklineData={[90, 98, 105, 112, 120, 125, allCases.length]}
          infoTooltip="Cases queued for optimal execution during peak timing windows"
        />
      </div>

      {/* Main Table Card */}
      <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
        <Card className={cn(
          "rounded-2xl p-3.5 sm:p-4 space-y-3 transition-colors border",
          isLight ? "bg-white border-slate-200 shadow-sm text-slate-900" : "border-slate-800 bg-[#0B111E]/95 shadow-2xl text-white"
        )}>
          {/* Filter Tabs & Search Row */}
          <div className={cn("flex flex-wrap items-center justify-between gap-2.5 border-b pb-3", isLight ? "border-slate-100" : "border-slate-800/80")}>
            {/* Tabs with descriptive Tooltips */}
            <TooltipProvider delayDuration={150}>
              <div className={cn(
                "flex flex-wrap items-center gap-1 p-1 rounded-xl border transition-colors",
                isLight ? "bg-slate-100/90 border-slate-200" : "bg-slate-950/90 border-slate-800"
              )}>
                {tabs.map((t) => (
                  <Tooltip key={t.label}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => {
                          setActiveTab(t.label);
                          setCurrentPage(1);
                        }}
                        className={cn(
                          'px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all flex items-center gap-1.5 cursor-pointer',
                          activeTab === t.label
                            ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-sm shadow-indigo-600/30 font-bold'
                            : (isLight ? 'text-slate-600 hover:text-slate-900 hover:bg-white' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/80')
                        )}
                      >
                        <span>{t.label}</span>
                        <span
                          className={cn(
                            'px-1.5 py-0.2 rounded-full text-[9.5px] font-bold border transition-colors',
                            activeTab === t.label
                              ? 'bg-white/20 text-white border-white/30'
                              : (isLight ? 'bg-white text-slate-700 border-slate-300 shadow-xs' : 'bg-slate-900 text-slate-400 border-slate-800')
                          )}
                        >
                          {t.count}
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className={cn("text-xs", isLight ? "bg-white text-slate-900 border-slate-200 shadow-md" : "bg-slate-900 border-slate-700 text-white")}>
                      <p>{t.tooltip}</p>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </TooltipProvider>

            {/* Search Input */}
            <div className="relative min-w-[200px] sm:min-w-[240px]">
              <Search className={cn("w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2", isLight ? "text-slate-400" : "text-slate-500")} />
              <input
                type="text"
                placeholder="Search customer, case ID, reason..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className={cn(
                  "w-full pl-7 pr-7 py-1 text-xs rounded-xl border focus:outline-none transition-all",
                  isLight
                    ? "bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    : "bg-slate-950/80 border-slate-800 text-white placeholder:text-slate-500 focus:border-indigo-500/60"
                )}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-xs cursor-pointer"
                >
                  ×
                </button>
              )}
            </div>
          </div>

          {/* Recovery Table */}
          <div className={cn(
            "overflow-x-auto rounded-xl border transition-colors",
            isLight ? "border-slate-200 bg-white shadow-sm" : "border-slate-800/80 bg-slate-950/50 shadow-xl"
          )}>
            <table className="w-full text-left text-[11px] border-collapse">
              <thead>
                <tr className={cn(
                  "border-b font-bold uppercase tracking-wider text-[10px] select-none",
                  isLight ? "bg-slate-50 border-slate-200 text-slate-500" : "border-slate-800 text-slate-400 bg-slate-900/90"
                )}>
                  <th 
                    className="py-2.5 px-2.5 cursor-pointer hover:text-indigo-600 dark:hover:text-white transition-colors"
                    onClick={() => handleSort('caseId')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Case ID</span>
                      <ArrowUpDown className="w-2.5 h-2.5 text-slate-400" />
                    </div>
                  </th>
                  <th className="py-2.5 px-2.5">Customer</th>
                  <th className="py-2.5 px-2.5">Domain</th>
                  <th className="py-2.5 px-2.5">Failure Reason</th>
                  <th 
                    className="py-2.5 px-2.5 cursor-pointer hover:text-indigo-600 dark:hover:text-white transition-colors"
                    onClick={() => handleSort('amount')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Amount</span>
                      <ArrowUpDown className="w-2.5 h-2.5 text-slate-400" />
                    </div>
                  </th>
                  <th className="py-2.5 px-2.5">Recommended Action</th>
                  <th 
                    className="py-2.5 px-2.5 cursor-pointer hover:text-indigo-600 dark:hover:text-white transition-colors"
                    onClick={() => handleSort('uplift')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Inc. Uplift (τ)</span>
                      <ArrowUpDown className="w-2.5 h-2.5 text-slate-400" />
                    </div>
                  </th>
                  <th 
                    className="py-2.5 px-2.5 cursor-pointer hover:text-indigo-600 dark:hover:text-white transition-colors"
                    onClick={() => handleSort('confidence')}
                  >
                    <div className="flex items-center gap-1">
                      <span>Confidence</span>
                      <ArrowUpDown className="w-2.5 h-2.5 text-slate-400" />
                    </div>
                  </th>
                  <th className="py-2.5 px-2.5">Evidence</th>
                  <th className="py-2.5 px-2.5">Status</th>
                  <th className="py-2.5 px-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className={cn("divide-y", isLight ? "divide-slate-100" : "divide-slate-800/60")}>
                {paginatedCases.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="py-8 text-center text-slate-400">
                      No recovery cases found matching current filters.
                    </td>
                  </tr>
                ) : (
                  paginatedCases.map((c: RecoveryCase, idx: number) => {
                    const isSelected = selectedCaseId === c.caseId;

                    return (
                      <motion.tr
                        key={c.caseId}
                        initial={{ opacity: 0, y: 3 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.15, delay: idx * 0.015 }}
                        onClick={() => openCaseDrawer(c.caseId)}
                        className={cn(
                          'cursor-pointer transition-all duration-150 group relative',
                          isLight
                            ? isSelected ? 'bg-indigo-50/90 ring-1 ring-indigo-300' : idx % 2 === 1 ? 'bg-slate-50/60 hover:bg-indigo-50/40' : 'bg-white hover:bg-indigo-50/40'
                            : isSelected ? 'bg-indigo-950/50 ring-1 ring-indigo-500/50' : idx % 2 === 1 ? 'bg-slate-900/20 hover:bg-indigo-950/30' : 'bg-transparent hover:bg-indigo-950/30'
                        )}
                      >
                        {/* Case ID */}
                        <td className="py-2 px-2.5 font-semibold whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span className={cn(
                              "font-mono font-bold transition-colors text-[11px] px-1.5 py-0.5 rounded border",
                              isLight
                                ? "bg-indigo-50 text-indigo-700 border-indigo-200 group-hover:text-indigo-900"
                                : "bg-indigo-950/50 text-indigo-300 border-indigo-500/30 group-hover:text-indigo-200"
                            )}>
                              {c.caseId}
                            </span>
                            {c.amount > 5000 && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Star className="w-3 h-3 fill-amber-400 text-amber-400 shrink-0" />
                                  </TooltipTrigger>
                                  <TooltipContent className="bg-slate-900 border border-slate-700 text-[10px]">
                                    <p>High Impact (&gt; ₹5,000)</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        </td>

                        {/* Customer */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-indigo-600 to-purple-700 text-white font-bold text-[9px] flex items-center justify-center shrink-0 border border-indigo-400/30">
                              {c.customerName.split(' ').map((n) => n[0]).join('').slice(0, 2)}
                            </div>
                            <div className="min-w-0">
                              <span className={cn("font-bold text-[11px] block truncate max-w-[110px] transition-colors", isLight ? "text-slate-900 group-hover:text-indigo-700" : "text-white group-hover:text-indigo-200")}>
                                {c.customerName}
                              </span>
                              <span className="text-[9px] text-slate-400 font-mono block truncate max-w-[110px]">
                                {c.customerHandle}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* Domain */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <span
                            className={cn(
                              'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9.5px] font-bold border tracking-wide',
                              c.domain === 'SUBSCRIPTIONS'
                                ? (isLight ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30')
                                : c.domain === 'CHECKOUT'
                                ? (isLight ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-amber-500/15 text-amber-300 border-amber-500/30')
                                : (isLight ? 'bg-cyan-50 text-cyan-700 border-cyan-200' : 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30')
                            )}
                          >
                            {c.domain === 'SUBSCRIPTIONS' ? (
                              <RefreshCw className="w-2.5 h-2.5 shrink-0" />
                            ) : c.domain === 'CHECKOUT' ? (
                              <CreditCard className="w-2.5 h-2.5 shrink-0" />
                            ) : (
                              <Building2 className="w-2.5 h-2.5 shrink-0" />
                            )}
                            <span>
                              {c.domain === 'SUBSCRIPTIONS'
                                ? 'Sub'
                                : c.domain === 'CHECKOUT'
                                ? 'Cart'
                                : 'B2B'}
                            </span>
                          </span>
                        </td>

                        {/* Failure Reason */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <span className={cn("text-[10.5px] font-medium truncate max-w-[120px] block", isLight ? "text-slate-700" : "text-slate-300")}>
                            {c.failureReason}
                          </span>
                        </td>

                        {/* Amount */}
                        <td className={cn("py-2 px-2.5 font-bold tabular-nums text-xs whitespace-nowrap", isLight ? "text-slate-900" : "text-white")}>
                          {formatINR(c.amount)}
                        </td>

                        {/* Recommended Action */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <div className="space-y-0.5">
                            <ActionPill action={c.recommendedAction} label={c.recommendedActionLabel} />
                            <div className="text-[9.5px] flex items-center gap-1">
                              <Clock className="w-2.5 h-2.5 text-indigo-500 shrink-0" />
                              <span className={cn("font-medium", isLight ? "text-slate-600" : "text-slate-300")}>{c.recommendedTime}</span>
                            </div>
                          </div>
                        </td>

                        {/* Incremental Uplift */}
                        <td className="py-2 px-2.5 font-bold tabular-nums whitespace-nowrap">
                          {c.recommendedAction === 'NO_ACTION' ? (
                            <span className="text-slate-400 text-[10.5px]">+2.1%</span>
                          ) : c.incrementalUplift ? (
                            <span className={cn(
                              "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10.5px] font-black border",
                              isLight
                                ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            )}>
                              +{Math.round(c.incrementalUplift * 100)}%
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>

                        {/* Decision Confidence */}
                        <td className="py-2 px-2.5 font-semibold tabular-nums whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <div className={cn("w-10 h-1.5 rounded-full overflow-hidden border", isLight ? "bg-slate-200 border-slate-300" : "bg-slate-900 border-slate-800")}>
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  c.decisionConfidence >= 0.9
                                    ? 'bg-emerald-500'
                                    : c.decisionConfidence >= 0.75
                                    ? 'bg-indigo-500'
                                    : 'bg-amber-500'
                                )}
                                style={{ width: `${Math.round(c.decisionConfidence * 100)}%` }}
                              />
                            </div>
                            <span className={cn("text-[10.5px] font-bold font-mono", isLight ? "text-slate-900" : "text-slate-200")}>
                              {Math.round(c.decisionConfidence * 100)}%
                            </span>
                          </div>
                        </td>

                        {/* Evidence Source */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <span className={cn("text-[9.5px] font-medium flex items-center gap-1", isLight ? "text-slate-600" : "text-slate-400")}>
                            <Layers className="w-2.5 h-2.5 text-indigo-500 shrink-0" />
                            {c.decisionSource === 'NETWORK_MERCHANT'
                              ? 'Net+Merch'
                              : c.isOOD
                              ? 'OOD'
                              : 'Network'}
                          </span>
                        </td>

                        {/* Status */}
                        <td className="py-2 px-2.5 whitespace-nowrap">
                          <StatusBadge status={c.status} />
                        </td>

                        {/* Quick Action Column */}
                        <td className="py-2 px-2.5 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            {c.status === 'READY' && (
                              <button
                                onClick={() => setApprovingCase(c)}
                                className={cn(
                                  "px-2 py-1 rounded-lg border text-[10px] font-bold transition-all flex items-center gap-0.5 cursor-pointer",
                                  isLight
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-300 hover:bg-emerald-100"
                                    : "bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border-emerald-500/40"
                                )}
                                title="Approve"
                              >
                                <CheckCircle2 className="w-3 h-3" />
                                Approve
                              </button>
                            )}
                            <button
                              onClick={() => openCaseDrawer(c.caseId)}
                              className={cn(
                                "px-2 py-1 rounded-lg border text-[10px] font-bold transition-all flex items-center gap-0.5 cursor-pointer group/btn",
                                isLight
                                  ? "bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border-indigo-200"
                                  : "bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border-indigo-500/40"
                              )}
                            >
                              <span>Inspect</span>
                              <ArrowRight className="w-3 h-3 group-hover/btn:translate-x-0.5 transition-transform" />
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Footer / Pagination & Legend */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-slate-800 text-xs text-slate-400">
            <div className="flex flex-wrap items-center gap-3 text-[10.5px]">
              <span className="flex items-center gap-1">
                <Star className="w-3 h-3 text-amber-400 fill-amber-400/20" />
                <strong className="text-slate-300">High Impact:</strong> &gt; ₹5,000
              </span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <strong className="text-slate-300">Inc. Uplift:</strong> Causal addition
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[10.5px] text-slate-400">
                {sortedCases.length > 0 ? (currentPage - 1) * pageSize + 1 : 0}–
                {Math.min(currentPage * pageSize, sortedCases.length)} of {sortedCases.length}
              </span>
              <div className="flex items-center gap-1 ml-1">
                <button
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="p-1 rounded-md bg-slate-900 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <ChevronLeft className="w-3 h-3" />
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={cn(
                      'w-5 h-5 rounded-md text-[10.5px] font-bold flex items-center justify-center transition-all cursor-pointer',
                      currentPage === page
                        ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/40'
                        : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-white'
                    )}
                  >
                    {page}
                  </button>
                ))}
                <button
                  disabled={currentPage === totalPages || totalPages === 0}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="p-1 rounded-md bg-slate-900 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-40 transition-colors cursor-pointer"
                >
                  <ChevronRight className="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </Card>
      </motion.div>

      <OperatorApprovalModal
        caseData={approvingCase}
        isOpen={!!approvingCase}
        onClose={() => setApprovingCase(null)}
        onSuccess={() => {
          if (approvingCase) {
            approveCase(approvingCase.caseId);
          }
          setApprovingCase(null);
        }}
      />
    </motion.div>
  );
};

