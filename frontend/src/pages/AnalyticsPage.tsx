import React, { useState, useEffect } from 'react';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { RecoverySimulator } from '../components/simulator/RecoverySimulator';
import { RecoveryFunnelInsightsCard } from '../components/shared/RecoveryFunnelInsightsCard';
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
  Clock,
  ChevronDown,
  Info,
  Disc,
  Target,
  Users,
  LineChart as LineChartIcon,
  IndianRupee,
  Coins,
  FileSpreadsheet,
  Check
} from 'lucide-react';
import { useDemoStore } from '../store/demoStore';
import { useAnalytics } from '../hooks/useAnalytics';
import { formatINR } from '../lib/formatting';
import { cn } from '../lib/utils';
import { motion } from 'framer-motion';

type TimelineKey = 'This Week' | 'This Month' | 'This Quarter' | 'Year to Date';

interface TimelineDataset {
  label: string;
  subLabel: string;
  recoveredValue: string;
  baselineRecovered: string;
  recoveredLift: string;
  sparkline: { v: number }[];

  incrementalValue: string;
  incrementalLift: string;

  totalCases: string;
  totalCasesLift: string;
  totalCasesSub: string;

  avgTime: string;
  avgTimeDelta: string;
  avgTimeSub: string;

  comparisonRows: {
    metric: string;
    sub: string;
    wapsi: string;
    baseline: string;
    diff: string;
    imp: string;
    icon: any;
    iconColor: string;
    iconBg: string;
    tooltip: string;
  }[];

  trendData: { day: string; wapsi: number; baseline: number }[];
  yAxisTicks: number[];
  yAxisFormatter: (v: number) => string;

  domainTotal: string;
  domainSegments: { name: string; amount: string; percentage: string; value: number; color: string }[];
  outcomeSegments: { name: string; percentage: string; value: number; color: string }[];
}

const analyticsDataByTimeline: Record<TimelineKey, TimelineDataset> = {
  'This Week': {
    label: 'This Week',
    subLabel: 'vs baseline ₹5.68L',
    recoveredValue: '₹7.82L',
    baselineRecovered: '₹5.68L',
    recoveredLift: '▲ 37.7%',
    sparkline: [{ v: 4.2 }, { v: 4.8 }, { v: 5.4 }, { v: 6.1 }, { v: 6.8 }, { v: 7.2 }, { v: 7.82 }],
    incrementalValue: '₹2.14L',
    incrementalLift: '▲ 37.6%',
    totalCases: '12,842',
    totalCasesLift: '▲ 18.7%',
    totalCasesSub: 'vs last 30 days',
    avgTime: '2.7 days',
    avgTimeDelta: '▼ -0.6 days',
    avgTimeSub: 'vs last 30 days',
    comparisonRows: [
      { metric: 'Recovered', sub: 'Total amount recovered', wapsi: '₹7.82L', baseline: '₹5.68L', diff: '+₹2.14L', imp: '▲ 37.7%', icon: Disc, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/50', tooltip: 'Gross recovered value through optimal execution' },
      { metric: 'Attempts', sub: 'Recovery attempts used', wapsi: '1,842', baseline: '3,104', diff: '-1,262', imp: '▲ 40.7%', icon: Target, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/50', tooltip: '40.7% fewer gateway retry attempts used' },
      { metric: 'Contacts', sub: 'Customer contacts made', wapsi: '742', baseline: '1,921', diff: '-1,179', imp: '▲ 61.4%', icon: Users, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/50', tooltip: '61.4% fewer messages sent, preserving user trust' },
      { metric: '₹ / Attempt', sub: 'Recovery per attempt', wapsi: '₹425', baseline: '₹183', diff: '+₹242', imp: '▲ 132.2%', icon: LineChartIcon, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '132.2% higher efficiency per retry trigger' },
      { metric: '₹ / Contact', sub: 'Recovery per contact', wapsi: '₹1,054', baseline: '₹296', diff: '+₹758', imp: '▲ 256.1%', icon: IndianRupee, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '2.5x more revenue captured per communication' },
    ],
    trendData: [
      { day: 'Mon 22', wapsi: 0.15, baseline: 0.12 },
      { day: 'Tue 23', wapsi: 0.50, baseline: 0.35 },
      { day: 'Wed 24', wapsi: 0.90, baseline: 0.50 },
      { day: 'Thu 25', wapsi: 1.00, baseline: 0.60 },
      { day: 'Fri 26', wapsi: 1.50, baseline: 0.95 },
      { day: 'Sat 27', wapsi: 1.85, baseline: 1.30 },
      { day: 'Sun 28', wapsi: 1.65, baseline: 1.40 },
    ],
    yAxisTicks: [0, 0.5, 1.0, 1.5, 2.0],
    yAxisFormatter: (v) => `₹${v}L`,
    domainTotal: '₹7.82L',
    domainSegments: [
      { name: 'Subscriptions', amount: '₹4.21L', percentage: '53.9%', value: 53.9, color: '#8B5CF6' },
      { name: 'Checkout', amount: '₹2.16L', percentage: '27.6%', value: 27.6, color: '#06B6D4' },
      { name: 'B2B Receivables', amount: '₹1.45L', percentage: '18.5%', value: 18.5, color: '#10B981' },
    ],
    outcomeSegments: [
      { name: 'Recovered', percentage: '68.2%', value: 68.2, color: '#22C55E' },
      { name: 'Promise-to-Pay', percentage: '18.7%', value: 18.7, color: '#3B82F6' },
      { name: 'Failed', percentage: '9.6%', value: 9.6, color: '#EF4444' },
      { name: 'Escalated', percentage: '3.5%', value: 3.5, color: '#F59E0B' },
    ],
  },
  'This Month': {
    label: 'This Month',
    subLabel: 'vs baseline ₹22.80L',
    recoveredValue: '₹31.40L',
    baselineRecovered: '₹22.80L',
    recoveredLift: '▲ 37.7%',
    sparkline: [{ v: 18.5 }, { v: 21.2 }, { v: 24.0 }, { v: 26.5 }, { v: 28.9 }, { v: 30.1 }, { v: 31.4 }],
    incrementalValue: '₹8.60L',
    incrementalLift: '▲ 37.7%',
    totalCases: '51,368',
    totalCasesLift: '▲ 19.4%',
    totalCasesSub: 'vs last month',
    avgTime: '2.6 days',
    avgTimeDelta: '▼ -0.7 days',
    avgTimeSub: 'vs last month',
    comparisonRows: [
      { metric: 'Recovered', sub: 'Total amount recovered', wapsi: '₹31.40L', baseline: '₹22.80L', diff: '+₹8.60L', imp: '▲ 37.7%', icon: Disc, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/50', tooltip: 'Gross recovered value through optimal execution' },
      { metric: 'Attempts', sub: 'Recovery attempts used', wapsi: '7,368', baseline: '12,416', diff: '-5,048', imp: '▲ 40.7%', icon: Target, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/50', tooltip: '40.7% fewer gateway retry attempts used' },
      { metric: 'Contacts', sub: 'Customer contacts made', wapsi: '2,968', baseline: '7,684', diff: '-4,716', imp: '▲ 61.4%', icon: Users, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/50', tooltip: '61.4% fewer messages sent, preserving user trust' },
      { metric: '₹ / Attempt', sub: 'Recovery per attempt', wapsi: '₹426', baseline: '₹184', diff: '+₹242', imp: '▲ 132.2%', icon: LineChartIcon, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '132.2% higher efficiency per retry trigger' },
      { metric: '₹ / Contact', sub: 'Recovery per contact', wapsi: '₹1,058', baseline: '₹297', diff: '+₹761', imp: '▲ 256.1%', icon: IndianRupee, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '2.5x more revenue captured per communication' },
    ],
    trendData: [
      { day: 'Week 1', wapsi: 6.8, baseline: 5.0 },
      { day: 'Week 2', wapsi: 14.5, baseline: 10.8 },
      { day: 'Week 3', wapsi: 23.1, baseline: 16.9 },
      { day: 'Week 4', wapsi: 31.4, baseline: 22.8 },
    ],
    yAxisTicks: [0, 10, 20, 30, 40],
    yAxisFormatter: (v) => `₹${v}L`,
    domainTotal: '₹31.40L',
    domainSegments: [
      { name: 'Subscriptions', amount: '₹16.92L', percentage: '53.9%', value: 53.9, color: '#8B5CF6' },
      { name: 'Checkout', amount: '₹8.67L', percentage: '27.6%', value: 27.6, color: '#06B6D4' },
      { name: 'B2B Receivables', amount: '₹5.81L', percentage: '18.5%', value: 18.5, color: '#10B981' },
    ],
    outcomeSegments: [
      { name: 'Recovered', percentage: '69.1%', value: 69.1, color: '#22C55E' },
      { name: 'Promise-to-Pay', percentage: '18.2%', value: 18.2, color: '#3B82F6' },
      { name: 'Failed', percentage: '9.2%', value: 9.2, color: '#EF4444' },
      { name: 'Escalated', percentage: '3.5%', value: 3.5, color: '#F59E0B' },
    ],
  },
  'This Quarter': {
    label: 'This Quarter',
    subLabel: 'vs baseline ₹68.40L',
    recoveredValue: '₹94.20L',
    baselineRecovered: '₹68.40L',
    recoveredLift: '▲ 37.7%',
    sparkline: [{ v: 55.0 }, { v: 62.5 }, { v: 71.0 }, { v: 78.4 }, { v: 85.2 }, { v: 90.0 }, { v: 94.2 }],
    incrementalValue: '₹25.80L',
    incrementalLift: '▲ 37.7%',
    totalCases: '154,104',
    totalCasesLift: '▲ 21.2%',
    totalCasesSub: 'vs last quarter',
    avgTime: '2.5 days',
    avgTimeDelta: '▼ -0.8 days',
    avgTimeSub: 'vs last quarter',
    comparisonRows: [
      { metric: 'Recovered', sub: 'Total amount recovered', wapsi: '₹94.20L', baseline: '₹68.40L', diff: '+₹25.80L', imp: '▲ 37.7%', icon: Disc, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/50', tooltip: 'Gross recovered value through optimal execution' },
      { metric: 'Attempts', sub: 'Recovery attempts used', wapsi: '22,104', baseline: '37,248', diff: '-15,144', imp: '▲ 40.7%', icon: Target, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/50', tooltip: '40.7% fewer gateway retry attempts used' },
      { metric: 'Contacts', sub: 'Customer contacts made', wapsi: '8,904', baseline: '23,052', diff: '-14,148', imp: '▲ 61.4%', icon: Users, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/50', tooltip: '61.4% fewer messages sent, preserving user trust' },
      { metric: '₹ / Attempt', sub: 'Recovery per attempt', wapsi: '₹426', baseline: '₹184', diff: '+₹242', imp: '▲ 132.2%', icon: LineChartIcon, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '132.2% higher efficiency per retry trigger' },
      { metric: '₹ / Contact', sub: 'Recovery per contact', wapsi: '₹1,058', baseline: '₹297', diff: '+₹761', imp: '▲ 256.1%', icon: IndianRupee, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '2.5x more revenue captured per communication' },
    ],
    trendData: [
      { day: 'Jun 2025', wapsi: 28.5, baseline: 20.8 },
      { day: 'Jul 2025', wapsi: 60.2, baseline: 43.9 },
      { day: 'Aug 2025', wapsi: 94.2, baseline: 68.4 },
    ],
    yAxisTicks: [0, 25, 50, 75, 100],
    yAxisFormatter: (v) => `₹${v}L`,
    domainTotal: '₹94.20L',
    domainSegments: [
      { name: 'Subscriptions', amount: '₹50.77L', percentage: '53.9%', value: 53.9, color: '#8B5CF6' },
      { name: 'Checkout', amount: '₹26.00L', percentage: '27.6%', value: 27.6, color: '#06B6D4' },
      { name: 'B2B Receivables', amount: '₹17.43L', percentage: '18.5%', value: 18.5, color: '#10B981' },
    ],
    outcomeSegments: [
      { name: 'Recovered', percentage: '70.4%', value: 70.4, color: '#22C55E' },
      { name: 'Promise-to-Pay', percentage: '17.8%', value: 17.8, color: '#3B82F6' },
      { name: 'Failed', percentage: '8.5%', value: 8.5, color: '#EF4444' },
      { name: 'Escalated', percentage: '3.3%', value: 3.3, color: '#F59E0B' },
    ],
  },
  'Year to Date': {
    label: 'Year to Date',
    subLabel: 'vs baseline ₹2.73Cr',
    recoveredValue: '₹3.76Cr',
    baselineRecovered: '₹2.73Cr',
    recoveredLift: '▲ 37.7%',
    sparkline: [{ v: 0.4 }, { v: 0.9 }, { v: 1.4 }, { v: 1.9 }, { v: 2.5 }, { v: 3.1 }, { v: 3.76 }],
    incrementalValue: '₹1.03Cr',
    incrementalLift: '▲ 37.7%',
    totalCases: '616,416',
    totalCasesLift: '▲ 23.5%',
    totalCasesSub: 'vs 2024 annualized',
    avgTime: '2.4 days',
    avgTimeDelta: '▼ -0.9 days',
    avgTimeSub: 'vs 2024 baseline',
    comparisonRows: [
      { metric: 'Recovered', sub: 'Total amount recovered', wapsi: '₹3.76Cr', baseline: '₹2.73Cr', diff: '+₹1.03Cr', imp: '▲ 37.7%', icon: Disc, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/50', tooltip: 'Gross recovered value through optimal execution' },
      { metric: 'Attempts', sub: 'Recovery attempts used', wapsi: '88,416', baseline: '148,992', diff: '-60,576', imp: '▲ 40.7%', icon: Target, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/50', tooltip: '40.7% fewer gateway retry attempts used' },
      { metric: 'Contacts', sub: 'Customer contacts made', wapsi: '35,616', baseline: '92,208', diff: '-56,592', imp: '▲ 61.4%', icon: Users, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/50', tooltip: '61.4% fewer messages sent, preserving user trust' },
      { metric: '₹ / Attempt', sub: 'Recovery per attempt', wapsi: '₹425', baseline: '₹183', diff: '+₹242', imp: '▲ 132.2%', icon: LineChartIcon, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '132.2% higher efficiency per retry trigger' },
      { metric: '₹ / Contact', sub: 'Recovery per contact', wapsi: '₹1,056', baseline: '₹296', diff: '+₹760', imp: '▲ 256.1%', icon: IndianRupee, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/50', tooltip: '2.5x more revenue captured per communication' },
    ],
    trendData: [
      { day: 'Jan', wapsi: 0.42, baseline: 0.30 },
      { day: 'Feb', wapsi: 0.88, baseline: 0.64 },
      { day: 'Mar', wapsi: 1.39, baseline: 1.01 },
      { day: 'Apr', wapsi: 1.95, baseline: 1.41 },
      { day: 'May', wapsi: 2.54, baseline: 1.84 },
      { day: 'Jun', wapsi: 3.10, baseline: 2.25 },
      { day: 'Jul', wapsi: 3.55, baseline: 2.58 },
      { day: 'Aug', wapsi: 3.76, baseline: 2.73 },
    ],
    yAxisTicks: [0, 1.0, 2.0, 3.0, 4.0],
    yAxisFormatter: (v) => `₹${v}Cr`,
    domainTotal: '₹3.76Cr',
    domainSegments: [
      { name: 'Subscriptions', amount: '₹2.03Cr', percentage: '53.9%', value: 53.9, color: '#8B5CF6' },
      { name: 'Checkout', amount: '₹1.04Cr', percentage: '27.6%', value: 27.6, color: '#06B6D4' },
      { name: 'B2B Receivables', amount: '₹0.69Cr', percentage: '18.5%', value: 18.5, color: '#10B981' },
    ],
    outcomeSegments: [
      { name: 'Recovered', percentage: '71.2%', value: 71.2, color: '#22C55E' },
      { name: 'Promise-to-Pay', percentage: '17.4%', value: 17.4, color: '#3B82F6' },
      { name: 'Failed', percentage: '8.1%', value: 8.1, color: '#EF4444' },
      { name: 'Escalated', percentage: '3.3%', value: 3.3, color: '#F59E0B' },
    ],
  },
};

export const AnalyticsPage: React.FC = () => {
  const globalDateRange = useDemoStore((state) => state.selectedDateRange);
  const setSelectedDateRange = useDemoStore((state) => state.setSelectedDateRange);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const { data: analyticsData } = useAnalytics();
  const liveOverview = analyticsData?.metrics;

  const [activeTimeline, setActiveTimeline] = useState<TimelineKey>('This Week');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Sync with global header range when changed
  useEffect(() => {
    if (globalDateRange.includes('Month') || globalDateRange.includes('Aug 1 – Aug 28')) {
      setActiveTimeline('This Month');
    } else if (globalDateRange.includes('Quarter') || globalDateRange.includes('90 Days') || globalDateRange.includes('Jun 1 – Aug 28')) {
      setActiveTimeline('This Quarter');
    } else if (globalDateRange.includes('Year') || globalDateRange.includes('Jan 1 – Aug 28')) {
      setActiveTimeline('Year to Date');
    } else {
      setActiveTimeline('This Week');
    }
  }, [globalDateRange]);

  const handleTimelineChange = (t: TimelineKey) => {
    setActiveTimeline(t);
    setIsDropdownOpen(false);

    // Sync back to global store
    if (t === 'This Week') setSelectedDateRange('Aug 22 – Aug 28, 2026');
    if (t === 'This Month') setSelectedDateRange('Aug 1 – Aug 28, 2026');
    if (t === 'This Quarter') setSelectedDateRange('Jun 1 – Aug 28, 2026');
    if (t === 'Year to Date') setSelectedDateRange('Jan 1 – Aug 28, 2026');
  };

  const currentData = analyticsDataByTimeline[activeTimeline] || analyticsDataByTimeline['This Week'];
  const timelineOptions: TimelineKey[] = ['This Week', 'This Month', 'This Quarter', 'Year to Date'];

  // Bind summary KPI cards to live data from GET /api/v1/analytics/summary
  const displayRecovered = (activeTimeline === 'This Week' && liveOverview?.recovered != null)
    ? formatINR(liveOverview.recovered, true)
    : currentData.recoveredValue;

  const displayRecoveredLift = (activeTimeline === 'This Week' && liveOverview?.recoveredDelta != null)
    ? `▲ ${Math.abs(liveOverview.recoveredDelta)}%`
    : currentData.recoveredLift;

  const displayIncremental = (activeTimeline === 'This Week' && liveOverview?.incrementalRecovery != null)
    ? formatINR(liveOverview.incrementalRecovery, true)
    : currentData.incrementalValue;

  const displayIncrementalLift = (activeTimeline === 'This Week' && liveOverview?.incrementalRecoveryDelta != null)
    ? `▲ ${Math.abs(liveOverview.incrementalRecoveryDelta)}%`
    : currentData.incrementalLift;

  const displayTotalCases = (activeTimeline === 'This Week' && analyticsData?.funnel?.[0]?.count != null)
    ? analyticsData.funnel[0].count.toLocaleString('en-IN')
    : currentData.totalCases;

  // Reusable Timeline Selector Dropdown
  const renderTimelineDropdown = () => (
    <div className="relative">
      <button
        onClick={() => setIsDropdownOpen(!isDropdownOpen)}
        className="flex items-center gap-1 text-xs font-semibold text-slate-300 bg-slate-900 border border-slate-800 hover:border-slate-700 px-2.5 py-1 rounded-lg cursor-pointer transition-colors shadow-sm"
      >
        <span>{activeTimeline}</span>
        <ChevronDown className={cn("w-3 h-3 text-slate-400 transition-transform", isDropdownOpen ? "rotate-180" : "")} />
      </button>

      {isDropdownOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsDropdownOpen(false)} />
          <div className="absolute right-0 mt-1.5 w-36 bg-[#090E1B] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1 max-h-48 overflow-y-auto">
            {timelineOptions.map((opt) => {
              const isSelected = activeTimeline === opt;
              return (
                <button
                  key={opt}
                  onClick={() => handleTimelineChange(opt)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 text-xs font-medium flex items-center justify-between transition-colors cursor-pointer",
                    isSelected
                      ? "bg-indigo-600/20 text-indigo-300 font-bold border-l-2 border-indigo-500"
                      : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
                  )}
                >
                  <span>{opt}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-indigo-400" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="space-y-4 max-w-[1600px] mx-auto pb-8"
    >
      <Topbar
        title="Analytics"
        subtitle="Measure impact. Prove value. Drive smarter recovery."
      />

      {/* Top 4 KPI Cards - Exact Match to Image 1 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Card 1: TOTAL RECOVERED BY WAPSI */}
        <motion.div
          key={`card-1-${activeTimeline}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className={cn(
            "p-4 rounded-2xl border space-y-2 relative overflow-hidden transition-colors",
            isLight
              ? "bg-white border-slate-200 shadow-sm text-slate-900"
              : "border-purple-500/20 bg-gradient-to-b from-[#140F28]/95 to-[#0B0918]/95 shadow-xl text-white"
          )}
        >
          <div className="flex items-center justify-between">
            <span className={cn("text-[10px] uppercase font-extrabold tracking-wider", isLight ? "text-slate-500" : "text-slate-400")}>
              TOTAL RECOVERED BY WAPSI
            </span>
            <span className={cn(
              "text-[9.5px] font-semibold px-2 py-0.5 rounded-md border",
              isLight
                ? "text-purple-800 bg-purple-50 border-purple-200 font-bold"
                : "text-purple-200 bg-purple-950/80 border-purple-500/40"
            )}>
              {activeTimeline}
            </span>
          </div>

          <div className="flex items-end justify-between gap-2 pt-0.5">
            <div>
              <div className={cn(
                "text-2xl sm:text-3xl font-black tabular-nums tracking-tight",
                isLight ? "text-purple-700 font-black" : "text-purple-400"
              )}>
                {displayRecovered}
              </div>
              <div className={cn("text-[10.5px] mt-0.5", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>
                {currentData.subLabel}
              </div>
              <div className={cn("flex items-center gap-1 text-[11px] font-bold mt-1", isLight ? "text-emerald-700" : "text-emerald-400")}>
                <span>{displayRecoveredLift}</span>
              </div>
            </div>

            {/* Mini Sparkline Chart on Right */}
            <div className="w-24 h-12 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={currentData.sparkline}>
                  <defs>
                    <linearGradient id={`purpleGlow-${theme}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#8B5CF6" stopOpacity={isLight ? 0.3 : 0.4} />
                      <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <Area
                    type="monotone"
                    dataKey="v"
                    stroke="#8B5CF6"
                    strokeWidth={2.2}
                    fill={`url(#purpleGlow-${theme})`}
                    dot={{ r: 2.5, fill: '#FFFFFF', stroke: '#8B5CF6', strokeWidth: 1.5 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </motion.div>

        {/* Card 2: INCREMENTAL RECOVERY (EST.) */}
        <motion.div
          key={`card-2-${activeTimeline}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: 0.04 }}
          className={cn(
            "p-4 rounded-2xl border space-y-2 relative overflow-hidden flex flex-col justify-between transition-colors",
            isLight
              ? "bg-white border-slate-200 shadow-sm text-slate-900"
              : "border-emerald-500/20 bg-gradient-to-b from-[#0C1E18]/95 to-[#081310]/95 shadow-xl text-white"
          )}
        >
          <div className="flex items-center justify-between">
            <span className={cn("text-[10px] uppercase font-extrabold tracking-wider", isLight ? "text-slate-500" : "text-slate-400")}>
              INCREMENTAL RECOVERY (EST.)
            </span>
          </div>

          <div className="flex items-center justify-between gap-2 pt-0.5">
            <div>
              <div className={cn(
                "text-2xl sm:text-3xl font-black tabular-nums tracking-tight",
                isLight ? "text-emerald-700 font-black" : "text-emerald-400"
              )}>
                {displayIncremental}
              </div>
              <div className={cn("text-[10.5px] mt-0.5", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>
                vs baseline
              </div>
              <div className={cn("flex items-center gap-1 text-[11px] font-bold mt-1", isLight ? "text-emerald-700" : "text-emerald-400")}>
                <span>{displayIncrementalLift}</span>
              </div>
            </div>

            {/* Green Circular Badge with Stacked Coins */}
            <div className={cn(
              "w-11 h-11 rounded-full border flex items-center justify-center shrink-0 shadow-md",
              isLight
                ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                : "bg-emerald-950/80 border-emerald-500/40 text-emerald-400 shadow-emerald-950/40"
            )}>
              <Coins className="w-5 h-5" />
            </div>
          </div>
        </motion.div>

        {/* Card 3: TOTAL CASES */}
        <motion.div
          key={`card-3-${activeTimeline}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: 0.08 }}
          className={cn(
            "p-4 rounded-2xl border space-y-2 relative overflow-hidden flex flex-col justify-between transition-colors",
            isLight
              ? "bg-white border-slate-200 shadow-sm text-slate-900"
              : "border-cyan-500/20 bg-gradient-to-b from-[#0C1A2B]/95 to-[#07101C]/95 shadow-xl text-white"
          )}
        >
          <div className="flex items-center justify-between">
            <span className={cn("text-[10px] uppercase font-extrabold tracking-wider", isLight ? "text-slate-500" : "text-slate-400")}>
              TOTAL CASES
            </span>
          </div>

          <div className="flex items-center justify-between gap-2 pt-0.5">
            <div>
              <div className={cn(
                "text-2xl sm:text-3xl font-black tabular-nums tracking-tight",
                isLight ? "text-cyan-700 font-black" : "text-cyan-400"
              )}>
                {displayTotalCases}
              </div>
              <div className={cn("text-[10.5px] mt-0.5", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>
                {currentData.totalCasesSub}
              </div>
              <div className={cn("flex items-center gap-1 text-[11px] font-bold mt-1", isLight ? "text-emerald-700" : "text-emerald-400")}>
                <span>{currentData.totalCasesLift}</span>
              </div>
            </div>

            {/* Blue Circular Badge with Ledger Document Icon */}
            <div className={cn(
              "w-11 h-11 rounded-full border flex items-center justify-center shrink-0 shadow-md",
              isLight
                ? "bg-cyan-50 border-cyan-200 text-cyan-700"
                : "bg-cyan-950/80 border-cyan-500/40 text-cyan-400 shadow-cyan-950/40"
            )}>
              <FileSpreadsheet className="w-5 h-5" />
            </div>
          </div>
        </motion.div>

        {/* Card 4: AVG. RECOVERY TIME */}
        <motion.div
          key={`card-4-${activeTimeline}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: 0.12 }}
          className={cn(
            "p-4 rounded-2xl border space-y-2 relative overflow-hidden flex flex-col justify-between transition-colors",
            isLight
              ? "bg-white border-slate-200 shadow-sm text-slate-900"
              : "border-amber-500/20 bg-gradient-to-b from-[#241A0B]/95 to-[#130E06]/95 shadow-xl text-white"
          )}
        >
          <div className="flex items-center justify-between">
            <span className={cn("text-[10px] uppercase font-extrabold tracking-wider", isLight ? "text-slate-500" : "text-slate-400")}>
              AVG. RECOVERY TIME
            </span>
          </div>

          <div className="flex items-center justify-between gap-2 pt-0.5">
            <div>
              <div className={cn(
                "text-2xl sm:text-3xl font-black tabular-nums tracking-tight",
                isLight ? "text-amber-700 font-black" : "text-amber-400"
              )}>
                {currentData.avgTime}
              </div>
              <div className={cn("text-[10.5px] mt-0.5", isLight ? "text-slate-600 font-medium" : "text-slate-400")}>
                {currentData.avgTimeSub}
              </div>
              <div className={cn("flex items-center gap-1 text-[11px] font-bold mt-1", isLight ? "text-rose-700" : "text-rose-400")}>
                <span>{currentData.avgTimeDelta}</span>
              </div>
            </div>

            {/* Orange Circular Badge with Clock Icon */}
            <div className={cn(
              "w-11 h-11 rounded-full border flex items-center justify-center shrink-0 shadow-md",
              isLight
                ? "bg-amber-50 border-amber-200 text-amber-700"
                : "bg-amber-950/80 border-amber-500/40 text-amber-400 shadow-amber-950/40"
            )}>
              <Clock className="w-5 h-5" />
            </div>
          </div>
        </motion.div>
      </div>

      {/* Main 2-Column Grid: Left 8 cols (Table, Chart) & Right 4 cols (Simulator, Recovery by Domain) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left Column (8 cols): WAPSI vs Baseline Table & Recovery Over Time Chart */}
        <div className="lg:col-span-8 space-y-4">
          {/* Card 1: WAPSI vs Baseline Comparison Matrix */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
            <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-2xl backdrop-blur-md">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <CardTitle className="text-sm font-bold text-white flex items-center gap-1.5">
                  <span>WAPSI vs Baseline Comparison</span>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                      </TooltipTrigger>
                      <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                        <p>Direct comparison against legacy static recovery rule engine</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </CardTitle>

                {/* Dropdown Selector */}
                {renderTimelineDropdown()}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                      <th className="py-2.5 px-3">METRIC</th>
                      <th className="py-2.5 px-3">WAPSI</th>
                      <th className="py-2.5 px-3">BASELINE</th>
                      <th className="py-2.5 px-3">DIFFERENCE</th>
                      <th className="py-2.5 px-3 text-right">IMPROVEMENT</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {currentData.comparisonRows.map((row) => {
                      const IconComponent = row.icon;
                      return (
                        <tr key={row.metric} className="hover:bg-slate-900/50 transition-colors group">
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2.5">
                              <div className={`w-6 h-6 rounded-full ${row.iconBg} border flex items-center justify-center ${row.iconColor} shrink-0`}>
                                <IconComponent className="w-3.5 h-3.5" />
                              </div>
                              <div>
                                <span className="font-semibold text-white block text-xs group-hover:text-indigo-300 transition-colors">
                                  {row.metric}
                                </span>
                                <span className="text-[10px] text-slate-400 block">
                                  {row.sub}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-bold text-white tabular-nums text-xs">
                            {row.wapsi}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400 tabular-nums text-xs font-medium">
                            {row.baseline}
                          </td>
                          <td className="py-2.5 px-3 font-semibold text-emerald-400 tabular-nums text-xs">
                            {row.diff}
                          </td>
                          <td className="py-2.5 px-3 text-right font-black text-emerald-400 tabular-nums text-xs">
                            {row.imp}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </motion.div>

          {/* Card 2: Recovery Over Time Area Chart */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 }}>
            <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-2xl backdrop-blur-md">
              <div className="flex items-center justify-between pb-1 border-b border-slate-800">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-1.5">
                    <span>Recovery Over Time</span>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                        </TooltipTrigger>
                        <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                          <p>Cumulative recovery progress compared to baseline for {activeTimeline}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </CardTitle>

                  {/* Legend */}
                  <div className="flex items-center gap-3 text-xs mt-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-purple-500 shadow-sm shadow-purple-500/50" />
                      <span className="text-slate-200 text-[11px] font-semibold">WAPSI</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
                      <span className="text-slate-400 text-[11px]">Baseline</span>
                    </div>
                  </div>
                </div>

                {/* Dropdown Selector */}
                {renderTimelineDropdown()}
              </div>

              <div className="h-48 w-full pt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={currentData.trendData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                    <defs>
                      <linearGradient id="wapsiAreaGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#A855F7" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#A855F7" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="day"
                      stroke="#64748B"
                      fontSize={10.5}
                      tickLine={false}
                      axisLine={{ stroke: '#1E293B' }}
                    />
                    <YAxis
                      stroke="#64748B"
                      fontSize={10.5}
                      tickLine={false}
                      axisLine={{ stroke: '#1E293B' }}
                      tickFormatter={currentData.yAxisFormatter}
                      ticks={currentData.yAxisTicks}
                    />
                    <RechartsTooltip
                      contentStyle={{ backgroundColor: '#090D18', borderColor: '#334155', borderRadius: '8px', fontSize: '11px', color: '#fff' }}
                      formatter={(val: number, name: string) => [currentData.yAxisFormatter(val), name === 'wapsi' ? 'WAPSI' : 'Baseline']}
                    />
                    <Area
                      type="monotone"
                      dataKey="wapsi"
                      stroke="#A855F7"
                      strokeWidth={2.5}
                      fill="url(#wapsiAreaGradient)"
                      dot={{ r: 3.5, fill: '#FFFFFF', stroke: '#A855F7', strokeWidth: 2 }}
                      isAnimationActive={true}
                    />
                    <Line
                      type="monotone"
                      dataKey="baseline"
                      stroke="#6366F1"
                      strokeWidth={1.8}
                      dot={{ r: 2.5, fill: '#6366F1', stroke: '#0F172A', strokeWidth: 1.5 }}
                      isAnimationActive={true}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </motion.div>
        </div>

        {/* Right Column (4 cols): Recovery Simulator & Recovery by Domain */}
        <div className="lg:col-span-4 space-y-4">
          {/* 1. Recovery Simulator */}
          <RecoverySimulator />

          {/* 2. Recovery by Domain Donut Card (Placed directly below Simulator) */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.08 }}>
            <Card className={cn(
              "p-4 rounded-2xl space-y-3 backdrop-blur-md transition-colors border",
              isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white shadow-2xl"
            )}>
              <div className={cn("flex items-center justify-between pb-1 border-b", isLight ? "border-slate-100" : "border-slate-800")}>
                <CardTitle className={cn("text-xs font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                  <span>Recovery by Domain</span>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 cursor-pointer" />
                      </TooltipTrigger>
                      <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                        <p>Recovered revenue contribution across transaction domains</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </CardTitle>
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                {/* Donut graphic with center label */}
                <div className="relative w-28 h-28 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={currentData.domainSegments}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={28}
                        outerRadius={46}
                        stroke={isLight ? '#FFFFFF' : '#0B101D'}
                        strokeWidth={2.5}
                        isAnimationActive={true}
                      >
                        {currentData.domainSegments.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  {/* Center Label */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className={cn("text-[11px] font-black leading-tight", isLight ? "text-slate-900" : "text-white")}>{currentData.domainTotal}</span>
                    <span className={cn("text-[8.5px] leading-tight", isLight ? "text-slate-500 font-medium" : "text-slate-400")}>Total</span>
                  </div>
                </div>

                {/* Legend */}
                <div className="space-y-1.5 flex-1 pl-1">
                  {currentData.domainSegments.map((s) => (
                    <div key={s.name} className="flex items-start gap-1 text-[10.5px]">
                      <span className="w-1.5 h-1.5 rounded-full mt-1 shrink-0" style={{ backgroundColor: s.color }} />
                      <div className="min-w-0">
                        <span className={cn("font-medium block text-[10px] truncate leading-tight", isLight ? "text-slate-800" : "text-slate-300")}>{s.name}</span>
                        <span className={cn("text-[9px] font-mono block tabular-nums leading-tight", isLight ? "text-slate-500 font-semibold" : "text-slate-400")}>
                          {s.amount} ({s.percentage})
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>
        </div>
      </div>

      {/* Bottom Section: Recovery Funnel (8 cols) & Outcome Distribution (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        {/* Left (8 cols): Recovery Funnel & Key Insights */}
        <div className="lg:col-span-8 flex flex-col">
          <RecoveryFunnelInsightsCard />
        </div>

        {/* Right (4 cols): Outcome Distribution Donut Card */}
        <div className="lg:col-span-4 flex flex-col">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.12 }} className="h-full">
            <Card className={cn(
              "p-4 rounded-2xl space-y-3 backdrop-blur-md h-full flex flex-col justify-between transition-colors border",
              isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "border-slate-800 bg-[#0B101D]/95 text-white shadow-2xl"
            )}>
              <div className={cn("flex items-center justify-between pb-1 border-b", isLight ? "border-slate-100" : "border-slate-800")}>
                <CardTitle className={cn("text-xs font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
                  <span>Outcome Distribution</span>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 cursor-pointer" />
                      </TooltipTrigger>
                      <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                        <p>Resolution status across all evaluated failed transaction attempts</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </CardTitle>
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                {/* Donut graphic */}
                <div className="relative w-28 h-28 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={currentData.outcomeSegments}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={28}
                        outerRadius={46}
                        stroke={isLight ? '#FFFFFF' : '#0B101D'}
                        strokeWidth={2.5}
                        isAnimationActive={true}
                      >
                        {currentData.outcomeSegments.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                {/* Legend */}
                <div className="space-y-1.5 flex-1 pl-1">
                  {currentData.outcomeSegments.map((s) => (
                    <div key={s.name} className="flex items-start gap-1.5 text-xs">
                      <span className="w-1.5 h-1.5 rounded-full mt-1 shrink-0" style={{ backgroundColor: s.color }} />
                      <div className="min-w-0">
                        <span className={cn("font-medium block text-[10.5px] truncate leading-tight", isLight ? "text-slate-800" : "text-slate-300")}>{s.name}</span>
                        <span className={cn("text-[9.5px] font-mono block tabular-nums leading-tight", isLight ? "text-slate-500 font-semibold" : "text-slate-400")}>
                          {s.percentage}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>
        </div>
      </div>

      {/* Footer Note */}
      <div className="p-2.5 text-center text-[11px] text-slate-500 border-t border-slate-800/80">
        All comparisons are against baseline (current manual/legacy process) • Metrics updated daily at 12:00 AM IST
      </div>
    </motion.div>
  );
};
