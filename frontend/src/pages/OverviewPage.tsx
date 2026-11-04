import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Topbar } from '../components/layout/Topbar';
import { MetricCard } from '../components/shared/MetricCard';
import { RadialScoreGauge } from '../components/shared/RadialScoreGauge';
import { InvertedFunnelGraphic } from '../components/shared/InvertedFunnelGraphic';
import { RecoveryHeroArtwork } from '../components/shared/RecoveryHeroArtwork';
import { WapsiBrandedHeader } from '../components/shared/WapsiBrandedHeader';
import { MetricDetailModal, MetricDetailData } from '../components/shared/MetricDetailModal';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/Tooltip';
import { 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip as RechartsTooltip, 
  PieChart, 
  Pie, 
  Cell 
} from 'recharts';
import { 
  TrendingUp, 
  ShieldCheck, 
  Sparkles, 
  CheckCircle2, 
  ArrowRight, 
  Layers, 
  Activity, 
  AlertCircle,
  Briefcase,
  Percent,
  Check,
  MessageSquare,
  RefreshCw,
  Gift,
  PhoneCall,
  Lock,
  ChevronRight,
  Zap,
  Clock,
  Gauge,
  ArrowUpRight,
  Info,
  ChevronDown
} from 'lucide-react';
import { useDecisionsOverview } from '../hooks/useAIDecisions';
import { formatINR, formatPercent } from '../lib/formatting';
import { cn } from '../lib/utils';
import { motion } from 'framer-motion';

// Custom High-Contrast Donut Tooltip
const CustomDomainTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-[#0B0F19] border border-indigo-500/50 rounded-xl p-3 shadow-2xl backdrop-blur-xl text-xs z-50">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: data.color }} />
          <span className="font-bold text-white text-xs">{data.domain}</span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-black text-white">{data.amount || `₹${(7.82 * (data.percentage / 100)).toFixed(2)}L`}</span>
          <span className="text-xs font-bold text-emerald-400">({data.percentage}% Share)</span>
        </div>
      </div>
    );
  }
  return null;
};

// Custom High-Contrast Pulse Tooltip (Appears ONLY on hover)
const CustomPulseTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const recovered = payload.find((p: any) => p.dataKey === 'recovered')?.value || 0;
    const baseline = payload.find((p: any) => p.dataKey === 'baseline')?.value || 0;
    const delta = recovered - baseline;
    const liftPercent = Math.round((delta / (baseline || 1)) * 100);

    return (
      <div className="bg-[#0B0F19] border border-indigo-500/50 rounded-xl p-3 shadow-2xl backdrop-blur-xl text-xs space-y-1.5 z-50">
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
          <span className="text-[11px] font-bold text-white">{label}, 2026</span>
          <span className="text-[10px] text-emerald-400 font-bold">+{liftPercent}% vs baseline</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-slate-300">Recovered (WAPSI):</span>
          <strong className="text-white font-black">₹{recovered.toFixed(2)}L</strong>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-slate-400">Baseline (No Action):</span>
          <strong className="text-slate-300 font-semibold">₹{baseline.toFixed(2)}L</strong>
        </div>
        <div className="flex items-center justify-between gap-4 pt-1 border-t border-slate-800 text-emerald-400 font-bold">
          <span>Incremental Causal Lift:</span>
          <span>+₹{delta.toFixed(2)}L</span>
        </div>
      </div>
    );
  }
  return null;
};

import { useDemoStore } from '../store/demoStore';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const { data, isLoading } = useDecisionsOverview();
  const [selectedMetricDetail, setSelectedMetricDetail] = useState<MetricDetailData | null>(null);

  // Global store synchronization
  const globalDateRange = useDemoStore((state) => state.selectedDateRange);
  const storeOverviewMetrics = useDemoStore((state) => state.overviewMetrics);
  const theme = useDemoStore((state) => state.theme);

  // Dynamic timeline selectors
  const [pulseTimeline, setPulseTimeline] = useState<'week' | 'month' | 'year'>('week');
  const [showPulseTimelineMenu, setShowPulseTimelineMenu] = useState(false);

  const [oppTimeline, setOppTimeline] = useState<'week' | 'month' | 'year'>('week');
  const [showOppTimelineMenu, setShowOppTimelineMenu] = useState(false);

  useEffect(() => {
    if (globalDateRange.includes('Month') || globalDateRange.includes('30 Days') || globalDateRange.includes('Aug 1 – Aug 28')) {
      setPulseTimeline('month');
      setOppTimeline('month');
    } else if (globalDateRange.includes('Year') || globalDateRange.includes('2025') || globalDateRange.includes('Jan 1 – Aug 28')) {
      setPulseTimeline('year');
      setOppTimeline('year');
    } else {
      setPulseTimeline('week');
      setOppTimeline('week');
    }
  }, [globalDateRange]);

  if (isLoading || !data) {
    return (
      <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
        <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
        <span className="text-sm">Loading WAPSI Overview...</span>
      </div>
    );
  }

  const { domains, failureReasons } = data;
  const metrics = storeOverviewMetrics || data.metrics;

  // Dynamic Pulse Data based on Timeline
  const pulseDatasets = {
    week: {
      label: 'This Week',
      data: [
        { day: 'Mon 22', recovered: 0.48, baseline: 0.35 },
        { day: 'Tue 23', recovered: 0.92, baseline: 0.52 },
        { day: 'Wed 24', recovered: 1.25, baseline: 0.68 },
        { day: 'Thu 25', recovered: 1.34, baseline: 0.74 },
        { day: 'Fri 26', recovered: 1.64, baseline: 0.82 },
        { day: 'Sat 27', recovered: 0.98, baseline: 0.79 },
        { day: 'Sun 28', recovered: 1.68, baseline: 1.05 },
      ],
      yDomain: [0, 2.0],
      yTicks: [0, 0.5, 1.0, 1.5, 2.0],
      recovered: '₹7.82L',
      recoveredSub: 'Cumulative 7-day volume',
      baseline: '₹5.68L',
      baselineSub: 'Organic settlement',
      incremental: '₹2.14L (+37.6%)',
      incrementalSub: 'Net Causal Addition',
      hazard: '18h post-failure optimal issuer window.',
      efficiency: '1.38x higher conversion with 40.7% less fatigue.',
      autonomous: '100% bound by NPCI & TRAI limits.',
    },
    month: {
      label: 'This Month',
      data: [
        { day: 'W1 (Aug 1-7)', recovered: 6.84, baseline: 4.95 },
        { day: 'W2 (Aug 8-14)', recovered: 7.42, baseline: 5.38 },
        { day: 'W3 (Aug 15-21)', recovered: 9.37, baseline: 6.79 },
        { day: 'W4 (Aug 22-28)', recovered: 7.82, baseline: 5.68 },
      ],
      yDomain: [0, 12.0],
      yTicks: [0, 3.0, 6.0, 9.0, 12.0],
      recovered: '₹31.45L',
      recoveredSub: 'Month-to-date total',
      baseline: '₹22.80L',
      baselineSub: 'Organic settlement',
      incremental: '₹8.65L (+37.9%)',
      incrementalSub: 'Net Causal Lift',
      hazard: 'Salary window (1st-5th) drives 64% recovery.',
      efficiency: 'Saved ₹48.2K in SMS/WhatsApp provider fees.',
      autonomous: 'Zero policy violations across 1,842 cases.',
    },
    year: {
      label: 'This Year',
      data: [
        { day: 'Jan', recovered: 24.2, baseline: 17.5 },
        { day: 'Feb', recovered: 26.8, baseline: 19.4 },
        { day: 'Mar', recovered: 29.5, baseline: 21.2 },
        { day: 'Apr', recovered: 28.1, baseline: 20.3 },
        { day: 'May', recovered: 32.4, baseline: 23.1 },
        { day: 'Jun', recovered: 34.2, baseline: 24.6 },
        { day: 'Jul', recovered: 36.8, baseline: 26.5 },
        { day: 'Aug', recovered: 36.0, baseline: 25.4 },
      ],
      yDomain: [0, 45.0],
      yTicks: [0, 15.0, 30.0, 45.0],
      recovered: '₹2.48Cr',
      recoveredSub: 'Annualized recovered sum',
      baseline: '₹1.78Cr',
      baselineSub: 'Organic settlement',
      incremental: '₹70.2L (+39.4%)',
      incrementalSub: 'Cumulative Net ROI',
      hazard: 'Network Priors accelerated recovery +41%.',
      efficiency: 'Involuntary churn slashed by 28.4% YoY.',
      autonomous: 'Attested in simulated hardware enclave.',
    },
  };

  const activePulse = pulseDatasets[pulseTimeline];

  // Dynamic AI Opportunities based on Timeline
  const oppDatasets = {
    week: {
      label: 'This Week',
      score: 12,
      maxScore: 15,
      expectedRecovery: '₹84,200',
      medianUplift: '+27%',
      medianConf: '91%',
      vsRuleBased: '1.6x',
      actions: [
        { name: 'WhatsApp Nudge', cases: '6 cases', amount: '₹41,200', icon: MessageSquare, color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
        { name: 'Retry (Smart)', cases: '3 cases', amount: '₹18,100', icon: RefreshCw, color: 'text-purple-400', bg: 'bg-purple-500/20' },
        { name: 'Incentive Link', cases: '2 cases', amount: '₹14,500', icon: Gift, color: 'text-amber-400', bg: 'bg-amber-500/20' },
        { name: 'Voice Call', cases: '1 case', amount: '₹7,400', icon: PhoneCall, color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
      ],
    },
    month: {
      label: 'This Month',
      score: 48,
      maxScore: 55,
      expectedRecovery: '₹3,82,400',
      medianUplift: '+29%',
      medianConf: '93%',
      vsRuleBased: '1.8x',
      actions: [
        { name: 'WhatsApp Nudge', cases: '24 cases', amount: '₹1,86,400', icon: MessageSquare, color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
        { name: 'Retry (Smart)', cases: '14 cases', amount: '₹1,12,000', icon: RefreshCw, color: 'text-purple-400', bg: 'bg-purple-500/20' },
        { name: 'Incentive Link', cases: '7 cases', amount: '₹54,000', icon: Gift, color: 'text-amber-400', bg: 'bg-amber-500/20' },
        { name: 'Voice Call', cases: '3 cases', amount: '₹30,000', icon: PhoneCall, color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
      ],
    },
    year: {
      label: 'This Year',
      score: 580,
      maxScore: 650,
      expectedRecovery: '₹46,50,000',
      medianUplift: '+31%',
      medianConf: '94%',
      vsRuleBased: '2.1x',
      actions: [
        { name: 'WhatsApp Nudge', cases: '290 cases', amount: '₹23.4L', icon: MessageSquare, color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
        { name: 'Retry (Smart)', cases: '170 cases', amount: '₹13.8L', icon: RefreshCw, color: 'text-purple-400', bg: 'bg-purple-500/20' },
        { name: 'Incentive Link', cases: '80 cases', amount: '₹6.2L', icon: Gift, color: 'text-amber-400', bg: 'bg-amber-500/20' },
        { name: 'Voice Call', cases: '40 cases', amount: '₹3.1L', icon: PhoneCall, color: 'text-cyan-400', bg: 'bg-cyan-500/20' },
      ],
    },
  };

  const activeOpp = oppDatasets[oppTimeline];

  const handleOpenDetail = (type: 'risk' | 'recoverable' | 'incremental' | 'recovered' | 'rate') => {
    switch (type) {
      case 'risk':
        setSelectedMetricDetail({
          title: 'Revenue at Risk',
          value: '₹18.42L',
          delta: '+16.7%',
          deltaType: 'warning',
          accentColor: 'rose',
          significance: 'Total value of customer payments that failed across all payment gateways and mandates during this billing cycle.',
          causalMethod: 'Monitored continuously across webhooks, auto-debits, and UPI mandate retries to estimate total exposure.',
          businessImpact: 'Unrecovered revenue at risk turns into involuntary customer churn within 14 days if unaddressed.',
          breakdown: [
            { label: 'Subscriptions', value: '₹9.84L', share: '53.4%' },
            { label: 'Checkout', value: '₹5.12L', share: '27.8%' },
            { label: 'B2B Invoices', value: '₹3.46L', share: '18.8%' },
          ],
        });
        break;
      case 'recoverable':
        setSelectedMetricDetail({
          title: 'Recoverable (Actionable)',
          value: '₹11.76L',
          delta: '+23.4%',
          deltaType: 'positive',
          accentColor: 'amber',
          significance: 'Portion of failed volume where intervention or smart retry has a high statistically proven probability of success.',
          causalMethod: 'Identified by Causal Meta-Learner (EconML-compatible) where incremental uplift exceeds minimum threshold (+5%).',
          businessImpact: 'Focuses engineering and communication bandwidth only on customers who will actually pay when nudged.',
          breakdown: [
            { label: 'Subscriptions', value: '₹6.28L', share: '53.4%' },
            { label: 'Checkout', value: '₹3.42L', share: '29.1%' },
            { label: 'B2B Invoices', value: '₹2.06L', share: '17.5%' },
          ],
        });
        break;
      case 'incremental':
        setSelectedMetricDetail({
          title: 'Incremental Recovery (Est.)',
          value: '₹2.14L',
          delta: '+37.6%',
          deltaType: 'positive',
          accentColor: 'emerald',
          significance: 'Pure incremental revenue generated EXCLUSIVELY by WAPSI that would have been completely lost under baseline/no-action.',
          causalMethod: 'Calculated as tau = Pt (treatment probability) - P0 (natural recovery probability) multiplied by transaction amount.',
          businessImpact: 'Direct bottom-line ROI calculation proving WAPSI incremental revenue addition beyond natural recovery.',
          breakdown: [
            { label: 'Smart Retry', value: '₹1.18L', share: '55.1%' },
            { label: 'WhatsApp Nudge', value: '₹62.4K', share: '29.2%' },
            { label: 'Incentive Link', value: '₹33.6K', share: '15.7%' },
          ],
        });
        break;
      case 'recovered':
        setSelectedMetricDetail({
          title: 'Total Recovered',
          value: '₹7.82L',
          delta: '+21.3%',
          deltaType: 'positive',
          accentColor: 'purple',
          significance: 'Gross total monetary value successfully settled into your bank account through automated recovery executions.',
          causalMethod: 'Sum of all transactions transitioning to RECOVERED state within the 72-hour optimal hazard timing window.',
          businessImpact: 'Reclaims working capital and prevents subscription cancellations without damaging user trust.',
          breakdown: [
            { label: 'Subscriptions', value: '₹4.21L', share: '53.9%' },
            { label: 'Checkout', value: '₹2.16L', share: '27.6%' },
            { label: 'B2B Receivables', value: '₹1.45L', share: '18.5%' },
          ],
        });
        break;
      case 'rate':
        setSelectedMetricDetail({
          title: 'Recovery Rate',
          value: '66.5%',
          delta: '+6.8pp',
          deltaType: 'positive',
          accentColor: 'cyan',
          significance: 'The percentage of all actionable failed transactions that were converted into successful settlements.',
          causalMethod: 'Computed as (Recovered Cases / Actionable Cases) with conformal prediction confidence intervals [63.2%, 69.8%].',
          businessImpact: 'Benchmark outperforming traditional rule-based retries (42.4% industry average) by +24.1 percentage points.',
          breakdown: [
            { label: 'Tier 1 Banks', value: '72.4%', share: 'HDFC/ICICI' },
            { label: 'UPI Mandates', value: '68.1%', share: 'Autodebit' },
            { label: 'Credit Cards', value: '59.2%', share: 'Cards' },
          ],
        });
        break;
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="space-y-5 max-w-[1600px] mx-auto pb-6"
    >
      <Topbar 
        title="Overview"
        subtitle="Operational command and causal revenue pulse"
      />

      <WapsiBrandedHeader
        title="Executive Recovery Operations Command"
        subtitle="Autonomous causal revenue recovery, bandit arbitration, and cryptographic policy governance."
      />

      {/* Greeting & Exact 3D Floating Dashboard Platform Banner */}
      <motion.div 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className={cn(
          "relative overflow-hidden p-6 rounded-2xl flex flex-wrap items-center justify-between gap-4 shadow-2xl backdrop-blur-md transition-colors",
          theme === 'light'
            ? "bg-gradient-to-r from-indigo-50/95 via-purple-50/90 to-indigo-100/95 border border-indigo-200 text-slate-900 shadow-indigo-100/60"
            : "bg-gradient-to-r from-[#0B0F19] via-[#0F172A] to-[#1E1B4B]/90 border border-slate-800 text-white"
        )}
      >
        <div className="space-y-2 z-10">
          <div className={cn(
            "flex items-center gap-2 text-xs font-semibold",
            theme === 'light' ? "text-indigo-900 font-bold" : "text-slate-300"
          )}>
            <span>Good Afternoon, Merchant</span>
            <span>👋</span>
          </div>
          <h2 className={cn(
            "text-2xl font-black tracking-tight",
            theme === 'light' ? "text-slate-900" : "text-white"
          )}>
            Your recovery engine is performing great!
          </h2>
          <div className="flex items-center gap-3 text-xs">
            <span className={theme === 'light' ? "text-slate-700 font-medium" : "text-slate-300"}>
              WAPSI recovered <strong className={theme === 'light' ? "text-emerald-700 font-black text-sm" : "text-emerald-400 font-extrabold text-sm"}>{formatINR(metrics.recovered, true)}</strong> this month
            </span>
            <span className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold",
              theme === 'light'
                ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                : "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
            )}>
              <TrendingUp className="w-3 h-3" />
              +21.3% vs baseline
            </span>
          </div>
        </div>

        {/* High-Fidelity 3D Floating Dashboard Platform Artwork */}
        <RecoveryHeroArtwork />
      </motion.div>

      {/* Top 5 KPI Cards with Trend Arrow Badges and Click Intelligence */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        <MetricCard
          title="REVENUE AT RISK"
          value={formatINR(metrics.revenueAtRisk, true)}
          delta={`${metrics.revenueAtRiskDelta > 0 ? '+' : ''}${metrics.revenueAtRiskDelta}%`}
          deltaType="warning"
          deltaSubtext="vs baseline"
          accentColor="rose"
          icon={<AlertCircle className="w-3.5 h-3.5" />}
          infoTooltip="Click to inspect causal breakdown and involuntary churn impact"
          onClick={() => handleOpenDetail('risk')}
        />
        <MetricCard
          title="RECOVERABLE (ACTIONABLE)"
          value={formatINR(metrics.recoverable, true)}
          delta={`${metrics.recoverableDelta > 0 ? '+' : ''}${metrics.recoverableDelta}%`}
          deltaType="positive"
          deltaSubtext="vs baseline"
          accentColor="amber"
          icon={<Briefcase className="w-3.5 h-3.5" />}
          infoTooltip="Click to inspect treatment payoff above No Action"
          onClick={() => handleOpenDetail('recoverable')}
        />
        <MetricCard
          title="INCREMENTAL RECOVERY"
          value={formatINR(metrics.incrementalRecovery, true)}
          delta={`${metrics.incrementalRecoveryDelta > 0 ? '+' : ''}${metrics.incrementalRecoveryDelta}%`}
          deltaType="positive"
          deltaSubtext="vs baseline"
          accentColor="emerald"
          icon={<ShieldCheck className="w-3.5 h-3.5" />}
          subtext="This is the additional recovery driven by WAPSI"
          infoTooltip="Click to view causal uplift calculation (tau = Pt - P0)"
          onClick={() => handleOpenDetail('incremental')}
        />
        <MetricCard
          title="RECOVERED"
          value={formatINR(metrics.recovered, true)}
          delta={`${metrics.recoveredDelta > 0 ? '+' : ''}${metrics.recoveredDelta}%`}
          deltaType="positive"
          deltaSubtext="vs baseline"
          accentColor="purple"
          icon={<Check className="w-3.5 h-3.5" />}
          infoTooltip="Click to view gross recovered revenue settlement"
          onClick={() => handleOpenDetail('recovered')}
        />
        <MetricCard
          title="RECOVERY RATE"
          value={`${metrics.recoveryRate.toFixed(1)}%`}
          delta={`+${metrics.recoveryRateDeltaPp || 6.8}pp`}
          deltaType="positive"
          deltaSubtext="vs baseline"
          accentColor="cyan"
          icon={<Percent className="w-3.5 h-3.5" />}
          infoTooltip="Click to view conversion benchmark across issuers"
          onClick={() => handleOpenDetail('rate')}
        />
      </div>

      {/* Middle Row: RECOVERY PULSE (7 cols) & AI OPPORTUNITIES (5 cols) - Perfectly Formatted to Fill Space */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        {/* Recovery Pulse Area Chart (7 cols) */}
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="lg:col-span-7 flex flex-col"
        >
          <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B111E]/95 space-y-4 shadow-xl flex-1 flex flex-col justify-between">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-indigo-400" />
                    RECOVERY PULSE
                  </CardTitle>
                  <p className="text-[11px] text-slate-400">Recovered amount over time vs organic baseline</p>
                </div>

                <div className="flex items-center gap-3 text-xs">
                  <div className="flex items-center gap-1.5 hidden sm:flex">
                    <span className="w-2 h-2 rounded-full bg-purple-500" />
                    <span className="text-slate-300 font-medium text-[11px]">Recovered</span>
                  </div>
                  <div className="flex items-center gap-1.5 hidden sm:flex">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span className="text-slate-400 text-[11px]">Baseline</span>
                  </div>

                  {/* Sleek Segmented Pill Timeline Switcher */}
                  <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-slate-800 shadow-inner">
                    {(['week', 'month', 'year'] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setPulseTimeline(t)}
                        className={cn(
                          'px-2.5 py-1 text-[10.5px] font-bold rounded-lg transition-all cursor-pointer capitalize',
                          pulseTimeline === t
                            ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-sm shadow-indigo-600/40'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                        )}
                      >
                        {t === 'week' ? 'Week' : t === 'month' ? 'Month' : 'Year'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Area Chart: Non-zero Deviated Baseline, Clean Y-Axis, Dynamic Data */}
              <div className="relative h-64 w-full mt-3">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={activePulse.data} margin={{ top: 15, right: 15, left: -15, bottom: 0 }}>
                    <defs>
                      <linearGradient id="pulseGlow" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.45} />
                        <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey="day" 
                      stroke="#64748B" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={{ stroke: '#1E293B' }} 
                    />
                    <YAxis 
                      stroke="#64748B" 
                      fontSize={11} 
                      tickLine={false} 
                      axisLine={{ stroke: '#1E293B' }} 
                      domain={activePulse.yDomain}
                      ticks={activePulse.yTicks}
                      tickFormatter={(val) => val === 0 ? '₹0' : `₹${val.toFixed(1)}L`} 
                    />
                    <RechartsTooltip content={<CustomPulseTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="recovered"
                      stroke="#8B5CF6"
                      strokeWidth={3}
                      fillOpacity={1}
                      fill="url(#pulseGlow)"
                      dot={{ r: 4, fill: '#FFFFFF', stroke: '#8B5CF6', strokeWidth: 2 }}
                      activeDot={{ r: 7, fill: '#C084FC' }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="baseline" 
                      stroke="#06B6D4" 
                      strokeWidth={2} 
                      strokeDasharray="3 3" 
                      dot={{ r: 2.5, fill: '#06B6D4' }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* 3 Metric Cards Under Recovery Pulse */}
            <div className="pt-3 border-t border-slate-800 space-y-3">
              <div className="grid grid-cols-3 gap-2.5 text-center">
                <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Recovered (WAPSI)</span>
                  <span className="text-sm font-extrabold text-white block mt-0.5">{activePulse.recovered}</span>
                  <span className="text-[9px] text-purple-400 font-medium">{activePulse.recoveredSub}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Baseline (No Action)</span>
                  <span className="text-sm font-extrabold text-slate-300 block mt-0.5">{activePulse.baseline}</span>
                  <span className="text-[9px] text-slate-500">{activePulse.baselineSub}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-500/30">
                  <span className="text-[10px] text-emerald-400 block font-bold">Incremental Lift</span>
                  <span className="text-sm font-extrabold text-emerald-300 block mt-0.5">{activePulse.incremental}</span>
                  <span className="text-[9px] text-emerald-400/80 font-medium">{activePulse.incrementalSub}</span>
                </div>
              </div>

              {/* Concise Precise Analytical Insights */}
              <div className="grid grid-cols-3 gap-2 text-[10px] pt-0.5">
                <div className="flex items-start gap-1.5 p-1.5 rounded-lg bg-indigo-950/30 border border-indigo-500/20 text-indigo-200">
                  <Zap className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                  <span><strong>Hazard Peak:</strong> {activePulse.hazard}</span>
                </div>
                <div className="flex items-start gap-1.5 p-1.5 rounded-lg bg-emerald-950/30 border border-emerald-500/20 text-emerald-200">
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <span><strong>Efficiency:</strong> {activePulse.efficiency}</span>
                </div>
                <div className="flex items-start gap-1.5 p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
                  <ShieldCheck className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5" />
                  <span><strong>Autonomous:</strong> {activePulse.autonomous}</span>
                </div>
              </div>
            </div>
          </Card>
        </motion.div>

        {/* AI OPPORTUNITIES (5 cols) - Fully Formatted & Height-Optimized with Interactive Timeline */}
        <motion.div 
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="lg:col-span-5 flex flex-col"
        >
          <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B111E]/95 space-y-4 shadow-xl flex-1 flex flex-col justify-between">
            <div className="space-y-4">
              {/* Header with Title ⓘ and Interactive Segmented Timeline */}
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <div className="flex items-center gap-1.5">
                  <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">
                    AI OPPORTUNITIES
                  </CardTitle>
                  <Info className="w-3.5 h-3.5 text-slate-500 cursor-pointer" />
                </div>

                {/* Sleek Segmented Pill Timeline Switcher */}
                <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-slate-800 shadow-inner">
                  {(['week', 'month', 'year'] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setOppTimeline(t)}
                      className={cn(
                        'px-2.5 py-1 text-[10.5px] font-bold rounded-lg transition-all cursor-pointer capitalize',
                        oppTimeline === t
                          ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-sm shadow-indigo-600/40'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                      )}
                    >
                      {t === 'week' ? 'Week' : t === 'month' ? 'Month' : 'Year'}
                    </button>
                  ))}
                </div>
              </div>
              <p className="text-[11px] text-slate-400">High confidence recovery opportunities identified by WAPSI!</p>

              {/* Main Metric Hero with Large Ring Gauge and Gold Amount */}
              <div className="p-3.5 rounded-2xl bg-slate-950/70 border border-slate-800/80 flex items-center justify-between gap-4 shadow-inner">
                <div className="flex items-center gap-3.5">
                  <RadialScoreGauge
                    score={activeOpp.score}
                    maxScore={activeOpp.maxScore}
                    label=""
                    size={76}
                    strokeWidth={7}
                    color="emerald"
                  />
                  <div className="space-y-0.5">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide block">
                      High-confidence opportunities
                    </span>
                    <span className="text-2xl font-black text-amber-400 tabular-nums block">
                      {activeOpp.expectedRecovery}
                    </span>
                    <span className="text-[10px] text-slate-400 block">
                      Expected incremental recovery
                    </span>
                  </div>
                </div>
              </div>

              {/* 3 Metric Pills with Clean Spacing */}
              <div className="grid grid-cols-3 gap-2 text-center p-2 rounded-xl bg-slate-900/60 border border-slate-800 text-xs">
                <div>
                  <span className="text-emerald-400 font-black block text-sm">{activeOpp.medianUplift}</span>
                  <span className="text-slate-400 text-[10px]">Median Uplift</span>
                </div>
                <div className="border-x border-slate-800">
                  <span className="text-white font-black block text-sm">{activeOpp.medianConf}</span>
                  <span className="text-slate-400 text-[10px]">Median Conf.</span>
                </div>
                <div>
                  <span className="text-indigo-300 font-black block text-sm">{activeOpp.vsRuleBased}</span>
                  <span className="text-slate-400 text-[10px]">vs Rule-Based</span>
                </div>
              </div>

              {/* Review Opportunities CTA Button */}
              <Button
                variant="primary"
                onClick={() => navigate('/recovery-center')}
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs py-2.5 rounded-xl shadow-lg shadow-indigo-600/30 gap-1.5"
              >
                <span>REVIEW OPPORTUNITIES ({activeOpp.score} READY)</span>
                <ArrowRight className="w-4 h-4" />
              </Button>

              {/* Top Opportunity Actions - Comfortable Height filling space */}
              <div className="space-y-2 pt-1">
                <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block">
                  TOP OPPORTUNITY ACTIONS
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {activeOpp.actions.map((opp, i) => {
                    const Icon = opp.icon;
                    return (
                      <div key={i} className="flex items-center justify-between text-xs p-2 rounded-xl bg-slate-950/80 border border-slate-800/80 hover:border-indigo-500/40 hover:bg-slate-900 transition-all">
                        <div className="flex items-center gap-2">
                          <div className={`p-1.5 rounded-lg ${opp.bg} ${opp.color}`}>
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <div>
                            <span className="text-slate-200 text-[11px] font-semibold block">{opp.name}</span>
                            <span className="text-[9px] text-slate-500">{opp.cases}</span>
                          </div>
                        </div>
                        <span className="font-bold text-white text-[11px] tabular-nums">
                          {opp.amount}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <button 
              onClick={() => navigate('/recovery-center')}
              className="text-[11px] text-indigo-400 hover:text-indigo-300 hover:underline pt-2 text-center font-medium block w-full transition-colors"
            >
              View all {activeOpp.score} actionable opportunities →
            </button>
          </Card>
        </motion.div>
      </div>

      {/* Bottom Grid: 4 Equal Columns matching Images */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. RECOVERY BY DOMAIN (High-Contrast Tooltip) */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.25 }}>
          <Card className={cn(
            "p-4 rounded-2xl flex flex-col justify-between shadow-xl h-full transition-colors border",
            theme === 'light' ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B111E]/95 text-white"
          )}>
            <div>
              <div className="flex items-center justify-between pb-1">
                <CardTitle className={cn("text-xs font-bold uppercase tracking-wider", theme === 'light' ? "text-slate-900" : "text-white")}>
                  RECOVERY BY DOMAIN
                </CardTitle>
                <span className={cn("text-[10px]", theme === 'light' ? "text-slate-500 font-medium" : "text-slate-500")}>This Week</span>
              </div>

              <div className="h-36 my-2">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={domains}
                      dataKey="percentage"
                      nameKey="domain"
                      cx="50%"
                      cy="50%"
                      innerRadius={36}
                      outerRadius={52}
                      paddingAngle={4}
                      stroke={theme === 'light' ? '#FFFFFF' : '#0B111E'}
                      strokeWidth={2}
                      isAnimationActive={true}
                    >
                      {domains.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <RechartsTooltip content={<CustomDomainTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-purple-500" />
                    <span className={theme === 'light' ? "text-slate-700" : "text-slate-300"}>Subscriptions</span>
                  </div>
                  <span className={cn("font-semibold", theme === 'light' ? "text-slate-900 font-bold" : "text-white")}>₹4.21L (53.9%)</span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span className={theme === 'light' ? "text-slate-700" : "text-slate-300"}>Checkout</span>
                  </div>
                  <span className={cn("font-semibold", theme === 'light' ? "text-slate-900 font-bold" : "text-white")}>₹2.16L (27.6%)</span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    <span className={theme === 'light' ? "text-slate-700" : "text-slate-300"}>Invoicing</span>
                  </div>
                  <span className={cn("font-semibold", theme === 'light' ? "text-slate-900 font-bold" : "text-white")}>₹1.45L (18.5%)</span>
                </div>
              </div>
            </div>

            <button 
              onClick={() => navigate('/analytics')}
              className={cn("text-[11px] hover:underline pt-3 text-left font-medium block transition-colors cursor-pointer", theme === 'light' ? "text-indigo-600 font-semibold" : "text-indigo-400")}
            >
              View full breakdown →
            </button>
          </Card>
        </motion.div>

        {/* 2. RECOVERY FUNNEL with Stratified Interactive Inverted Funnel */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.3 }}>
          <Card className="p-4 rounded-2xl border border-slate-800 bg-[#0B111E]/95 flex flex-col justify-between shadow-xl h-full">
            <div>
              <div className="flex items-center justify-between pb-1">
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">
                  RECOVERY FUNNEL
                </CardTitle>
                <span className="text-[10px] text-slate-500">This Week</span>
              </div>

              <div className="mt-2 flex items-center gap-3">
                {/* Stratified Inverted SVG Funnel with Interactive Band Tooltips */}
                <InvertedFunnelGraphic />

                <div className="flex-1 space-y-1.5 text-xs">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Detected</span>
                    <span className="font-bold text-white">12,842</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Scored</span>
                    <span className="font-bold text-white">8,931</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Ready</span>
                    <span className="font-bold text-white">4,231</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Actioned</span>
                    <span className="font-bold text-white">2,104</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Recovered</span>
                    <span className="font-bold text-emerald-400">1,842</span>
                  </div>

                  <div className="p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-center mt-2">
                    <span className="text-base font-black text-emerald-400 block">42.4%</span>
                    <span className="text-[9px] text-slate-400 block">Overall recovery conversion</span>
                  </div>
                </div>
              </div>
            </div>
            <button 
              onClick={() => navigate('/analytics')}
              className="text-[11px] text-indigo-400 hover:underline pt-2 text-left font-medium block"
            >
              View funnel analysis →
            </button>
          </Card>
        </motion.div>

        {/* 3. TOP FAILURE REASONS */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.35 }}>
          <Card className="p-4 rounded-2xl border border-slate-800 bg-[#0B111E]/95 flex flex-col justify-between shadow-xl h-full">
            <div>
              <div className="flex items-center justify-between pb-1">
                <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">
                  TOP FAILURE REASONS
                </CardTitle>
                <span className="text-[10px] text-slate-500">This Week</span>
              </div>

              <div className="mt-3 space-y-2 text-xs">
                {failureReasons.map((r: any, i: number) => (
                  <div key={i} className="space-y-1">
                    <div className="flex justify-between text-[11px]">
                      <span className="text-slate-300 truncate max-w-[130px]">{r.reason}</span>
                      <span className="text-slate-200 font-semibold tabular-nums">{r.percentage}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${r.percentage * 2}%` }}
                        transition={{ duration: 0.8, delay: i * 0.1 }}
                        className="h-full bg-indigo-500/90 rounded-full" 
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <button 
              onClick={() => navigate('/recovery-cases')}
              className="text-[11px] text-indigo-400 hover:underline pt-3 text-left font-medium block"
            >
              View all reasons →
            </button>
          </Card>
        </motion.div>

        {/* 4. MODEL HEALTH (Exact layout & gauge matching Image 1) */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.4 }}>
          <Card className="p-4 rounded-2xl border border-slate-800 bg-[#0B111E]/95 flex flex-col justify-between shadow-xl h-full">
            <div>
              <div className="flex items-center justify-between pb-1">
                <div className="flex items-center gap-1.5">
                  <CardTitle className="text-xs font-bold uppercase tracking-wider text-white">
                    MODEL HEALTH
                  </CardTitle>
                  <Info className="w-3.5 h-3.5 text-slate-500 cursor-pointer" />
                </div>
                <span className="text-[10px] text-emerald-400 font-semibold">Operational</span>
              </div>

              {/* Increased Gauge Size + Balanced Status Alignment matching Image 1 */}
              <div className="my-2 flex items-center justify-between gap-3">
                <RadialScoreGauge
                  score={95}
                  maxScore={100}
                  label="Health Score"
                  size={84}
                  strokeWidth={7}
                  color="emerald"
                />

                {/* Status items with glowing green dots */}
                <div className="space-y-1 text-[11px] flex-1">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
                      Uplift Model
                    </span>
                    <span className="text-emerald-400 font-semibold">Healthy</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
                      Hazard Model
                    </span>
                    <span className="text-emerald-400 font-semibold">Healthy</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
                      Policy Engine
                    </span>
                    <span className="text-emerald-400 font-semibold">Healthy</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
                      Data Pipeline
                    </span>
                    <span className="text-emerald-400 font-semibold">Healthy</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
                      Feature Quality
                    </span>
                    <span className="text-emerald-400 font-semibold">Good</span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80 flex justify-between text-[10px] text-slate-400">
                <span>Conformal Coverage: <strong className="text-slate-200">95.1%</strong></span>
                <span>OOD Cases: <strong className="text-slate-200">7</strong></span>
              </div>
            </div>
            <button 
              onClick={() => navigate('/ai-decisions')}
              className="text-[11px] text-indigo-400 hover:underline pt-3 text-left font-medium block"
            >
              View model details →
            </button>
          </Card>
        </motion.div>
      </div>

      {/* Bottom Single-Line Sleek Governance & Trust Bar */}
      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.45 }}
        className="p-3.5 rounded-2xl bg-[#0B111E]/95 border border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs shadow-xl backdrop-blur-md"
      >
        <div className="flex items-center gap-3.5 flex-wrap">
          <div className="p-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <span className="font-bold text-white tracking-wide">GOVERNANCE & TRUST</span>
          <span className="text-slate-600 hidden sm:inline">•</span>
          <span className="text-slate-300">Policy Violations: <strong className="text-emerald-400">0</strong></span>
          <span className="text-slate-600 hidden sm:inline">•</span>
          <span className="text-slate-300">All Actions Bounded</span>
          <span className="text-slate-600 hidden sm:inline">•</span>
          <span className="text-slate-300">Fairness Within Threshold</span>
          <span className="text-slate-600 hidden md:inline">•</span>
          <span className="text-slate-400">TEE Protected (Simulated)</span>
          <span className="text-slate-600 hidden md:inline">•</span>
          <span className="text-indigo-400 font-medium">Audit Trail Active</span>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={() => navigate('/governance')}
          className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-1.5 px-4 rounded-xl shadow-md shrink-0"
        >
          VIEW GOVERNANCE
        </Button>
      </motion.div>

      {/* Interactive Metric Detail Intelligence Modal */}
      <MetricDetailModal
        data={selectedMetricDetail}
        onClose={() => setSelectedMetricDetail(null)}
      />
    </motion.div>
  );
};
