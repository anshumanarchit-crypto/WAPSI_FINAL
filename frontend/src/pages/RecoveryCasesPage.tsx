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
  Download, 
  RotateCcw, 
  Star, 
  ChevronLeft, 
  ChevronRight,
  Clock,
  Layers,
  Sparkles,
  RefreshCw,
  CreditCard,
  Building2,
  TrendingUp,
  ArrowRight,
  SlidersHorizontal,
  CheckCircle2
} from 'lucide-react';
import { useDemoStore } from '../store/demoStore';
import { useRecoveryCases } from '../hooks/useRecovery';
import { formatINR } from '../lib/formatting';
import { cn } from '../lib/utils';
import { RecoveryCase } from '../types';
import { motion } from 'framer-motion';

// Comprehensive dataset covering all lifecycle stages
const richLedgerDataset: RecoveryCase[] = [
  {
    caseId: 'RX-48291',
    customerId: 'cust_6a113e',
    customerName: 'Aarav Sharma',
    customerHandle: 'aarav.sharma@enterprise.in',
    merchantId: 'MRC_928374',
    domain: 'SUBSCRIPTIONS',
    amount: 8999,
    failureReason: 'Insufficient Funds',
    failureCode: 'PAYMENT_FAIL_INSUFFICIENT_BALANCE',
    attempts: 2,
    maxAttempts: 4,
    contactsMade: 2,
    maxContacts: 5,
    issuer: 'HDFC Bank',
    status: 'READY',
    naturalRecoveryProbability: 0.48,
    treatmentProbability: 0.72,
    incrementalUplift: 0.24,
    recommendedAction: 'RETRY',
    recommendedActionLabel: 'Smart Retry',
    recommendedTime: 'Tomorrow 10:30 AM',
    optimalWindow: 'In 18 hours',
    decisionConfidence: 0.96,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T10:32:14Z',
    updatedAt: '2025-08-28T10:32:18Z',
  },
  {
    caseId: 'RX-48292',
    customerId: 'cust_2e7c6d',
    customerName: 'Priya Patel',
    customerHandle: 'priya.p@fintechcorp.io',
    merchantId: 'MRC_928374',
    domain: 'CHECKOUT',
    amount: 4200,
    failureReason: 'Gateway Timeout',
    failureCode: 'GATEWAY_TIMEOUT',
    attempts: 1,
    maxAttempts: 4,
    contactsMade: 1,
    maxContacts: 5,
    issuer: 'ICICI Bank',
    status: 'ACTIONED',
    naturalRecoveryProbability: 0.55,
    treatmentProbability: 0.70,
    incrementalUplift: 0.15,
    recommendedAction: 'WHATSAPP',
    recommendedActionLabel: 'WhatsApp Nudge',
    recommendedTime: 'Today 05:00 PM',
    optimalWindow: 'In 2 hours',
    decisionConfidence: 0.89,
    decisionSource: 'NETWORK',
    isOOD: false,
    createdAt: '2025-08-28T11:15:22Z',
    updatedAt: '2025-08-28T11:15:30Z',
  },
  {
    caseId: 'RX-48293',
    customerId: 'cust_9f3b1a',
    customerName: 'Vikram Mehta',
    customerHandle: 'v.mehta@saascloud.com',
    merchantId: 'MRC_928374',
    domain: 'RECEIVABLES_B2B',
    amount: 14500,
    failureReason: 'Mandate Expired',
    failureCode: 'MANDATE_EXPIRED',
    attempts: 3,
    maxAttempts: 4,
    contactsMade: 3,
    maxContacts: 5,
    issuer: 'State Bank of India',
    status: 'RECOVERED',
    naturalRecoveryProbability: 0.20,
    treatmentProbability: 0.65,
    incrementalUplift: 0.45,
    recommendedAction: 'VOICE',
    recommendedActionLabel: 'Voice Call',
    recommendedTime: 'Completed',
    optimalWindow: 'Recovered (₹14,500)',
    decisionConfidence: 0.94,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-27T09:12:40Z',
    updatedAt: '2025-08-28T12:45:00Z',
  },
  {
    caseId: 'RX-48294',
    customerId: 'cust_4d8a2c',
    customerName: 'Ananya Roy',
    customerHandle: 'ananya.roy@designstudio.co',
    merchantId: 'MRC_928374',
    domain: 'SUBSCRIPTIONS',
    amount: 2499,
    failureReason: 'Natural Recovery Likely',
    failureCode: 'USER_INTERVENTION_PENDING',
    attempts: 0,
    maxAttempts: 4,
    contactsMade: 0,
    maxContacts: 5,
    issuer: 'Axis Bank',
    status: 'MONITORING',
    naturalRecoveryProbability: 0.82,
    treatmentProbability: 0.84,
    incrementalUplift: 0.02,
    recommendedAction: 'NO_ACTION',
    recommendedActionLabel: 'No Action (Monitor)',
    recommendedTime: 'Self-healing window',
    optimalWindow: 'Zero Cost Save',
    decisionConfidence: 0.97,
    decisionSource: 'MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T13:00:10Z',
    updatedAt: '2025-08-28T13:00:15Z',
  },
  {
    caseId: 'RX-48295',
    customerId: 'cust_7c2e9f',
    customerName: 'Rohan Gupta',
    customerHandle: 'rohan.g@hypergrowth.tech',
    merchantId: 'MRC_928374',
    domain: 'CHECKOUT',
    amount: 6800,
    failureReason: 'Card Limit Exceeded',
    failureCode: 'CARD_LIMIT_EXCEEDED',
    attempts: 1,
    maxAttempts: 4,
    contactsMade: 1,
    maxContacts: 5,
    issuer: 'Kotak Mahindra',
    status: 'READY',
    naturalRecoveryProbability: 0.38,
    treatmentProbability: 0.74,
    incrementalUplift: 0.36,
    recommendedAction: 'INCENTIVE',
    recommendedActionLabel: 'Incentive Link',
    recommendedTime: 'In 6 hours',
    optimalWindow: 'Window: 6-12h',
    decisionConfidence: 0.91,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T14:20:00Z',
    updatedAt: '2025-08-28T14:20:08Z',
  },
  {
    caseId: 'RX-48296',
    customerId: 'cust_1a9b3c',
    customerName: 'Kavita Krishnan',
    customerHandle: 'kavita.k@analytics.ai',
    merchantId: 'MRC_928374',
    domain: 'SUBSCRIPTIONS',
    amount: 11999,
    failureReason: '3D Secure Failed',
    failureCode: 'AUTH_3DS_FAILED',
    attempts: 2,
    maxAttempts: 4,
    contactsMade: 2,
    maxContacts: 5,
    issuer: 'HDFC Bank',
    status: 'RECOVERED',
    naturalRecoveryProbability: 0.30,
    treatmentProbability: 0.68,
    incrementalUplift: 0.38,
    recommendedAction: 'WHATSAPP',
    recommendedActionLabel: 'WhatsApp Nudge',
    recommendedTime: 'Completed',
    optimalWindow: 'Recovered (₹11,999)',
    decisionConfidence: 0.93,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-27T16:40:12Z',
    updatedAt: '2025-08-28T09:15:30Z',
  },
  {
    caseId: 'RX-48297',
    customerId: 'cust_8e4f2d',
    customerName: 'Siddharth Joshi',
    customerHandle: 'siddharth@edutech.org',
    merchantId: 'MRC_928374',
    domain: 'RECEIVABLES_B2B',
    amount: 18500,
    failureReason: 'Account Inactive',
    failureCode: 'ACCOUNT_DORMANT',
    attempts: 4,
    maxAttempts: 4,
    contactsMade: 5,
    maxContacts: 5,
    issuer: 'Bank of Baroda',
    status: 'FAILED',
    naturalRecoveryProbability: 0.05,
    treatmentProbability: 0.12,
    incrementalUplift: 0.07,
    recommendedAction: 'VOICE',
    recommendedActionLabel: 'Voice Call',
    recommendedTime: 'Exhausted',
    optimalWindow: 'Attempts Exhausted',
    decisionConfidence: 0.98,
    decisionSource: 'NETWORK',
    isOOD: true,
    createdAt: '2025-08-26T08:00:00Z',
    updatedAt: '2025-08-28T10:00:00Z',
  },
  {
    caseId: 'RX-48298',
    customerId: 'cust_3c7b5a',
    customerName: 'Divya Nair',
    customerHandle: 'divya.n@healthscale.io',
    merchantId: 'MRC_928374',
    domain: 'CHECKOUT',
    amount: 3500,
    failureReason: 'Dispute Suspected',
    failureCode: 'DISPUTE_SUSPECTED',
    attempts: 1,
    maxAttempts: 4,
    contactsMade: 1,
    maxContacts: 5,
    issuer: 'Yes Bank',
    status: 'ESCALATED',
    naturalRecoveryProbability: 0.15,
    treatmentProbability: 0.25,
    incrementalUplift: 0.10,
    recommendedAction: 'VOICE',
    recommendedActionLabel: 'Manual CS Escalation',
    recommendedTime: 'Assigned to Ops',
    optimalWindow: 'Ops Review',
    decisionConfidence: 0.85,
    decisionSource: 'MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T15:10:00Z',
    updatedAt: '2025-08-28T15:10:20Z',
  },
  {
    caseId: 'RX-48299',
    customerId: 'cust_5f1e8c',
    customerName: 'Manish Chawla',
    customerHandle: 'manish.c@retailchain.in',
    merchantId: 'MRC_928374',
    domain: 'SUBSCRIPTIONS',
    amount: 5400,
    failureReason: 'Webhook Received',
    failureCode: 'PAYMENT_FAILED_RAW',
    attempts: 0,
    maxAttempts: 4,
    contactsMade: 0,
    maxContacts: 5,
    issuer: 'IndusInd Bank',
    status: 'DETECTED',
    naturalRecoveryProbability: 0.40,
    treatmentProbability: 0.65,
    incrementalUplift: 0.25,
    recommendedAction: 'RETRY',
    recommendedActionLabel: 'Smart Retry',
    recommendedTime: 'Pending Evaluation',
    optimalWindow: 'Scoring Queue',
    decisionConfidence: 0.82,
    decisionSource: 'NETWORK',
    isOOD: false,
    createdAt: '2025-08-28T16:00:00Z',
    updatedAt: '2025-08-28T16:00:05Z',
  },
  {
    caseId: 'RX-48300',
    customerId: 'cust_0d2a4e',
    customerName: 'Sunita Menon',
    customerHandle: 'sunita.m@logistics.net',
    merchantId: 'MRC_928374',
    domain: 'RECEIVABLES_B2B',
    amount: 9200,
    failureReason: 'Uplift Computed',
    failureCode: 'SCORED_AWAITING_APPROVAL',
    attempts: 0,
    maxAttempts: 4,
    contactsMade: 0,
    maxContacts: 5,
    issuer: 'ICICI Bank',
    status: 'SCORED',
    naturalRecoveryProbability: 0.35,
    treatmentProbability: 0.76,
    incrementalUplift: 0.41,
    recommendedAction: 'WHATSAPP',
    recommendedActionLabel: 'WhatsApp Nudge',
    recommendedTime: 'Tomorrow 09:00 AM',
    optimalWindow: 'Batch Ready',
    decisionConfidence: 0.95,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T16:15:00Z',
    updatedAt: '2025-08-28T16:15:10Z',
  },
  {
    caseId: 'RX-48301',
    customerId: 'cust_6e9f1a',
    customerName: 'Kunal Deshmukh',
    customerHandle: 'kunal.d@cloudinfra.tech',
    merchantId: 'MRC_928374',
    domain: 'SUBSCRIPTIONS',
    amount: 7500,
    failureReason: 'Policy Verified',
    failureCode: 'POLICY_CHECKS_PASSED',
    attempts: 1,
    maxAttempts: 4,
    contactsMade: 1,
    maxContacts: 5,
    issuer: 'HDFC Bank',
    status: 'APPROVED',
    naturalRecoveryProbability: 0.42,
    treatmentProbability: 0.75,
    incrementalUplift: 0.33,
    recommendedAction: 'RETRY',
    recommendedActionLabel: 'Smart Retry',
    recommendedTime: 'Tomorrow 08:30 AM',
    optimalWindow: 'In 16 hours',
    decisionConfidence: 0.94,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: false,
    createdAt: '2025-08-28T16:30:00Z',
    updatedAt: '2025-08-28T16:30:15Z',
  }
];

export const RecoveryCasesPage: React.FC = () => {
  const [activeStatusTab, setActiveStatusTab] = useState('All');
  const [selectedDomain, setSelectedDomain] = useState('All');
  const [selectedAmountFilter, setSelectedAmountFilter] = useState('All');
  const [selectedActionFilter, setSelectedActionFilter] = useState('All');
  const [selectedSourceFilter, setSelectedSourceFilter] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  const openCaseDrawer = useDemoStore((state) => state.openCaseDrawer);
  const selectedCaseId = useDemoStore((state) => state.selectedCaseId);
  const storeCases = useDemoStore((state) => state.cases);
  const theme = useDemoStore((state) => state.theme);

  const { data: liveCases, isLoading } = useRecoveryCases(selectedDomain, activeStatusTab, searchQuery);
  const activeDataset = (liveCases && liveCases.length > 0) ? liveCases : (storeCases && storeCases.length > 0) ? storeCases : richLedgerDataset;

  // Dynamic Status Tab Counts computed from exact entries
  const statusCounts = useMemo(() => {
    return {
      All: activeDataset.length,
      Detected: activeDataset.filter(c => c.status === 'DETECTED').length,
      Scored: activeDataset.filter(c => c.status === 'SCORED').length,
      Ready: activeDataset.filter(c => c.status === 'READY').length,
      Approved: activeDataset.filter(c => c.status === 'APPROVED').length,
      Actioned: activeDataset.filter(c => c.status === 'ACTIONED').length,
      Recovered: activeDataset.filter(c => c.status === 'RECOVERED').length,
      Failed: activeDataset.filter(c => c.status === 'FAILED').length,
      Escalated: activeDataset.filter(c => c.status === 'ESCALATED').length,
      Monitoring: activeDataset.filter(c => c.status === 'MONITORING' || c.recommendedAction === 'NO_ACTION').length,
    };
  }, [activeDataset]);

  const statusTabs = useMemo(() => [
    { label: 'All', count: statusCounts['All'] || 0, tooltip: 'Entire ledger of all transaction attempts' },
    { label: 'Detected', count: statusCounts['Detected'] || 0, tooltip: 'Newly failed payments received via webhooks' },
    { label: 'Scored', count: statusCounts['Scored'] || 0, tooltip: 'Causal probabilities and uplift calculated' },
    { label: 'Ready', count: statusCounts['Ready'] || 0, tooltip: 'Action approved and queued for optimal timing' },
    { label: 'Approved', count: statusCounts['Approved'] || 0, tooltip: 'Policy validation complete, scheduled for dispatch' },
    { label: 'Actioned', count: statusCounts['Actioned'] || 0, tooltip: 'Communication or smart retry executed' },
    { label: 'Recovered', count: statusCounts['Recovered'] || 0, tooltip: 'Payment successfully captured' },
    { label: 'Failed', count: statusCounts['Failed'] || 0, tooltip: 'Attempts exhausted or customer churned' },
    { label: 'Escalated', count: statusCounts['Escalated'] || 0, tooltip: 'Sent to human operations or customer success' },
    { label: 'Monitoring', count: statusCounts['Monitoring'] || 0, tooltip: 'No Action chosen, observing natural recovery' },
  ], [statusCounts]);

  // Dynamic Filtering Logic
  const filteredCases = useMemo(() => {
    return activeDataset.filter((c) => {
      // 1. Status Tab Filter
      if (activeStatusTab !== 'All') {
        if (activeStatusTab === 'Monitoring') {
          if (c.status !== 'MONITORING' && c.recommendedAction !== 'NO_ACTION') return false;
        } else {
          const matchStatus = c.status.toLowerCase() === activeStatusTab.toLowerCase();
          if (!matchStatus) return false;
        }
      }

      // 2. Domain Filter
      if (selectedDomain !== 'All') {
        if (selectedDomain === 'Subscriptions' && c.domain !== 'SUBSCRIPTIONS') return false;
        if (selectedDomain === 'Checkout' && c.domain !== 'CHECKOUT') return false;
        if (selectedDomain === 'B2B' && c.domain !== 'RECEIVABLES_B2B') return false;
      }

      // 3. Amount Filter
      if (selectedAmountFilter === '> ₹5,000' && c.amount <= 5000) return false;
      if (selectedAmountFilter === '< ₹5,000' && c.amount > 5000) return false;

      // 4. Action Filter
      if (selectedActionFilter !== 'All') {
        if (selectedActionFilter === 'Retry' && c.recommendedAction !== 'RETRY') return false;
        if (selectedActionFilter === 'WhatsApp' && c.recommendedAction !== 'WHATSAPP') return false;
        if (selectedActionFilter === 'Voice' && c.recommendedAction !== 'VOICE') return false;
        if (selectedActionFilter === 'Incentive' && c.recommendedAction !== 'INCENTIVE') return false;
        if (selectedActionFilter === 'No Action' && c.recommendedAction !== 'NO_ACTION') return false;
      }

      // 5. Decision Source Filter
      if (selectedSourceFilter !== 'All') {
        if (selectedSourceFilter === 'Network Prior' && c.decisionSource !== 'NETWORK') return false;
        if (selectedSourceFilter === 'Merchant Prior' && c.decisionSource !== 'MERCHANT') return false;
        if (selectedSourceFilter === 'Blended' && c.decisionSource !== 'NETWORK_MERCHANT') return false;
      }

      // 6. Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const match = 
          c.caseId.toLowerCase().includes(q) ||
          c.customerName.toLowerCase().includes(q) ||
          c.customerHandle.toLowerCase().includes(q) ||
          c.failureReason.toLowerCase().includes(q) ||
          (c.issuer && c.issuer.toLowerCase().includes(q));
        if (!match) return false;
      }

      return true;
    });
  }, [activeStatusTab, selectedDomain, selectedAmountFilter, selectedActionFilter, selectedSourceFilter, searchQuery]);

  // Pagination calculation
  const totalPages = Math.ceil(filteredCases.length / itemsPerPage) || 1;
  const paginatedCases = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredCases.slice(start, start + itemsPerPage);
  }, [filteredCases, currentPage]);

  const activeTabMeta = statusTabs.find(t => t.label === activeStatusTab) || statusTabs[0];

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="space-y-3.5 w-full pb-8 overflow-hidden"
    >
      <Topbar
        title="Recovery Cases"
        subtitle="Full operational audit ledger of all transaction recovery attempts and causal outcomes"
      />

      {/* Top 5 KPI Cards - Responsive Fit */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
        <MetricCard
          title="Total Cases"
          value="12,842"
          delta="+16.7%"
          deltaType="info"
          deltaSubtext="vs last 30d"
          accentColor="cyan"
          sparklineData={[10000, 10500, 11200, 11800, 12100, 12500, 12842]}
        />
        <MetricCard
          title="Recovered Cases"
          value="4,931"
          delta="+21.3%"
          deltaType="positive"
          deltaSubtext="vs last 30d"
          accentColor="emerald"
          subtext="38.4% rate"
          sparklineData={[3800, 4000, 4200, 4400, 4600, 4800, 4931]}
        />
        <MetricCard
          title="Total Recovered"
          value="₹7.82L"
          delta="+24.6%"
          deltaType="positive"
          deltaSubtext="vs last 30d"
          accentColor="purple"
          sparklineData={[5.2, 5.8, 6.1, 6.7, 7.1, 7.5, 7.82]}
        />
        <MetricCard
          title="Avg. Recovery Time"
          value="2.7 days"
          delta="-0.6d"
          deltaType="positive"
          deltaSubtext="vs last 30d"
          accentColor="amber"
          sparklineData={[3.5, 3.4, 3.2, 3.0, 2.9, 2.8, 2.7]}
        />
        <MetricCard
          title="Incremental (Est.)"
          value="₹2.14L"
          delta="+37.6%"
          deltaType="positive"
          deltaSubtext="vs last 7d"
          accentColor="cyan"
          sparklineData={[1.2, 1.4, 1.6, 1.8, 1.9, 2.0, 2.14]}
        />
      </div>

      {/* Ledger Table Card */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <Card className="rounded-2xl border border-slate-800 bg-[#0B101D]/95 p-3.5 sm:p-4 space-y-3 shadow-2xl backdrop-blur-md overflow-hidden">
          {/* Status Tabs with Dynamic Counts computed directly from table entries */}
          <TooltipProvider delayDuration={150}>
            <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-950/90 border border-slate-200 dark:border-slate-800/80 overflow-x-auto scrollbar-none">
              {statusTabs.map((t) => {
                const isActive = activeStatusTab === t.label;
                return (
                  <Tooltip key={t.label}>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => {
                          setActiveStatusTab(t.label);
                          setCurrentPage(1);
                        }}
                        className={cn(
                          'px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer',
                          isActive
                            ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/30 ring-1 ring-indigo-400/40'
                            : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/70 dark:hover:bg-slate-900/90'
                        )}
                      >
                        <span>{t.label}</span>
                        <span
                          className={cn(
                            'px-1.5 py-0.2 rounded-full text-[9.5px] font-bold tabular-nums',
                            isActive
                              ? 'bg-indigo-950/80 text-indigo-100 border border-indigo-400/30'
                              : 'bg-slate-200 dark:bg-slate-800/90 text-slate-700 dark:text-slate-400'
                          )}
                        >
                          {t.count.toLocaleString()}
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="bg-slate-900 border border-slate-700 text-xs">
                      <p>{t.tooltip}</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </TooltipProvider>

          {/* Filter Bar with Dropdowns and Search */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 pt-0.5">
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Domain Dropdown */}
              <select
                value={selectedDomain}
                onChange={(e) => {
                  setSelectedDomain(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-800 dark:text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-sm"
              >
                <option value="All">Domain: All</option>
                <option value="Subscriptions">Subscriptions</option>
                <option value="Checkout">Checkout</option>
                <option value="B2B">B2B Receivables</option>
              </select>

              {/* Amount Dropdown */}
              <select
                value={selectedAmountFilter}
                onChange={(e) => {
                  setSelectedAmountFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-800 dark:text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-sm"
              >
                <option value="All">Amount: All</option>
                <option value="> ₹5,000">&gt; ₹5,000</option>
                <option value="< ₹5,000">&lt; ₹5,000</option>
              </select>

              {/* Action Filter */}
              <select
                value={selectedActionFilter}
                onChange={(e) => {
                  setSelectedActionFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-800 dark:text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-sm"
              >
                <option value="All">Action: All</option>
                <option value="Retry">Smart Retry</option>
                <option value="WhatsApp">WhatsApp</option>
                <option value="Voice">Voice Call</option>
                <option value="Incentive">Incentive</option>
                <option value="No Action">No Action</option>
              </select>

              {/* Source Filter */}
              <select
                value={selectedSourceFilter}
                onChange={(e) => {
                  setSelectedSourceFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-800 dark:text-slate-200 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-sm"
              >
                <option value="All">Source: All</option>
                <option value="Blended">Blended (Net+Merch)</option>
                <option value="Network Prior">Network Prior</option>
                <option value="Merchant Prior">Merchant Prior</option>
              </select>

              {/* Reset Filter */}
              {(selectedDomain !== 'All' || selectedAmountFilter !== 'All' || selectedActionFilter !== 'All' || selectedSourceFilter !== 'All' || searchQuery !== '' || activeStatusTab !== 'All') && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedDomain('All');
                    setSelectedAmountFilter('All');
                    setSelectedActionFilter('All');
                    setSelectedSourceFilter('All');
                    setActiveStatusTab('All');
                    setSearchQuery('');
                    setCurrentPage(1);
                  }}
                  className="text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white h-6 px-1.5 rounded cursor-pointer"
                >
                  <RotateCcw className="w-2.5 h-2.5 mr-1" />
                  Reset
                </Button>
              )}
            </div>

            <div className="flex items-center gap-2">
              {/* Search Box */}
              <div className="relative min-w-[180px] sm:min-w-[200px]">
                <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  placeholder="Search ledger..."
                  className="w-full bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-lg pl-7 pr-2.5 py-1 text-[11px] text-slate-800 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 transition-colors shadow-sm"
                />
              </div>

              {/* Export CSV Button */}
              <Button variant="outline" size="sm" className="text-[11px] h-6 px-2 rounded-lg border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:text-white shadow-sm">
                <Download className="w-3 h-3 mr-1" />
                Export
              </Button>
            </div>
          </div>

          {/* High-Fidelity Compact Ledger Table - Zero Horizontal Scroll */}
          <div className="w-full overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-950/40 shadow-sm">
            <table className="w-full text-left text-[11px] border-collapse table-fixed">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 font-bold uppercase tracking-wider text-[9px] bg-slate-50 dark:bg-slate-900/90">
                  <th className="py-2 px-2 w-[7.5%]">Case ID</th>
                  <th className="py-2 px-2 w-[13%]">Customer</th>
                  <th className="py-2 px-1.5 w-[8.5%]">Domain</th>
                  <th className="py-2 px-2 w-[12%]">Failure Reason</th>
                  <th className="py-2 px-1.5 w-[7%]">Amount</th>
                  <th className="py-2 px-2 w-[15%]">Action</th>
                  <th className="py-2 px-1.5 w-[7%]">Inc. Uplift</th>
                  <th className="py-2 px-1.5 w-[6.5%]">Confidence</th>
                  <th className="py-2 px-1.5 w-[7.5%]">Source</th>
                  <th className="py-2 px-1.5 w-[9%] text-center">Status</th>
                  <th className="py-2 px-2 w-[7%] text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {paginatedCases.length > 0 ? (
                  paginatedCases.map((c: RecoveryCase, idx: number) => {
                    const isSelected = selectedCaseId === c.caseId;
                    const initials = c.customerName
                      .split(' ')
                      .map((n) => n[0])
                      .join('')
                      .toUpperCase()
                      .slice(0, 2);

                    return (
                      <motion.tr
                        key={c.caseId}
                        initial={{ opacity: 0, y: 3 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.15, delay: idx * 0.015 }}
                        onClick={() => openCaseDrawer(c.caseId)}
                        className={cn(
                          'hover:bg-slate-50 dark:hover:bg-slate-850/60 cursor-pointer transition-colors group',
                          isSelected ? 'bg-indigo-50/80 dark:bg-indigo-950/40 ring-1 ring-inset ring-indigo-500/50' : ''
                        )}
                      >
                        {/* Case ID */}
                        <td className="py-1.5 px-2">
                          <div className="flex items-center gap-1">
                            {c.amount > 5000 && (
                              <Star className="w-3 h-3 text-amber-500 fill-amber-400/30 shrink-0" />
                            )}
                            <span className="font-mono text-[10px] font-bold text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-200 dark:border-indigo-500/30 px-1 py-0.2 rounded group-hover:border-indigo-400 transition-colors truncate">
                              {c.caseId}
                            </span>
                          </div>
                        </td>

                        {/* Customer */}
                        <td className="py-1.5 px-2">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-indigo-600 to-purple-500 flex items-center justify-center text-[8.5px] font-bold text-white shrink-0 shadow-inner">
                              {initials}
                            </div>
                            <div className="min-w-0">
                              <span className="font-semibold text-slate-900 dark:text-white block text-[10.5px] truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-200 transition-colors leading-tight">
                                {c.customerName}
                              </span>
                              <span className="text-[9px] text-slate-500 dark:text-slate-400 font-mono block truncate leading-tight">
                                {c.customerHandle}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* Domain */}
                        <td className="py-1.5 px-1.5">
                          <span className={cn(
                            'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-semibold border truncate max-w-full',
                            c.domain === 'SUBSCRIPTIONS' 
                              ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/30'
                              : c.domain === 'CHECKOUT'
                              ? 'bg-cyan-50 dark:bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border-cyan-200 dark:border-cyan-500/30'
                              : 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30'
                          )}>
                            {c.domain === 'SUBSCRIPTIONS' ? <RefreshCw className="w-2 h-2 shrink-0" /> : c.domain === 'CHECKOUT' ? <CreditCard className="w-2 h-2 shrink-0" /> : <Building2 className="w-2 h-2 shrink-0" />}
                            <span className="truncate">{c.domain === 'SUBSCRIPTIONS' ? 'Subs' : c.domain === 'CHECKOUT' ? 'Checkout' : 'B2B'}</span>
                          </span>
                        </td>

                        {/* Failure Reason */}
                        <td className="py-1.5 px-2">
                          <div className="flex items-center gap-1 min-w-0">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                            <span className="text-slate-800 dark:text-slate-200 text-[10px] font-medium truncate">
                              {c.failureReason}
                            </span>
                          </div>
                          {c.issuer && (
                            <span className="text-[8.5px] text-slate-500 font-mono block truncate leading-tight mt-0.5">
                              {c.issuer}
                            </span>
                          )}
                        </td>

                        {/* Amount */}
                        <td className="py-1.5 px-1.5 font-bold text-slate-900 dark:text-white tabular-nums text-[11px] truncate">
                          {formatINR(c.amount)}
                        </td>

                        {/* Recommended Action */}
                        <td className="py-1.5 px-2">
                          <div className="flex items-center gap-1 min-w-0 flex-wrap">
                            <ActionPill action={c.recommendedAction} label={c.recommendedActionLabel} />
                            {c.optimalWindow && (
                              <span className="text-[8.5px] text-slate-500 dark:text-slate-400 flex items-center gap-0.5 bg-slate-100 dark:bg-slate-900/90 px-1 py-0.2 rounded border border-slate-200 dark:border-slate-800 truncate">
                                <Clock className="w-2 h-2 text-slate-400 dark:text-slate-500 shrink-0" />
                                <span className="truncate">{c.optimalWindow}</span>
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Incremental Uplift (τ) */}
                        <td className="py-1.5 px-1.5 font-bold tabular-nums">
                          {c.recommendedAction === 'NO_ACTION' ? (
                            <span className="text-slate-400 dark:text-slate-500 text-[9.5px]">Baseline</span>
                          ) : c.incrementalUplift ? (
                            <span className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 px-1 py-0.2 rounded text-[9.5px] font-bold">
                              <TrendingUp className="w-2 h-2 shrink-0" />
                              <span>+{Math.round(c.incrementalUplift * 100)}%</span>
                            </span>
                          ) : (
                            <span className="text-slate-400 dark:text-slate-500 text-[9.5px]">—</span>
                          )}
                        </td>

                        {/* Confidence */}
                        <td className="py-1.5 px-1.5">
                          <div className="space-y-0.5">
                            <span className="font-bold text-slate-900 dark:text-white tabular-nums text-[9.5px] block">
                              {Math.round(c.decisionConfidence * 100)}%
                            </span>
                            <div className="h-1 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-emerald-500 rounded-full"
                                style={{ width: `${Math.round(c.decisionConfidence * 100)}%` }}
                              />
                            </div>
                          </div>
                        </td>

                        {/* Decision Source */}
                        <td className="py-1.5 px-1.5">
                          <span className="text-[9px] text-slate-700 dark:text-slate-300 inline-flex items-center gap-0.5 font-medium bg-slate-100 dark:bg-slate-900 px-1 py-0.2 rounded border border-slate-200 dark:border-slate-800 truncate">
                            <Layers className="w-2.5 h-2.5 text-indigo-600 dark:text-indigo-400 shrink-0" />
                            <span className="truncate">
                              {c.decisionSource === 'NETWORK_MERCHANT'
                                ? 'Net+Merch'
                                : c.decisionSource === 'NETWORK'
                                ? 'Network'
                                : 'Merchant'}
                            </span>
                          </span>
                        </td>

                        {/* Status */}
                        <td className="py-1.5 px-1.5 text-center">
                          <StatusBadge status={c.status} size="sm" />
                        </td>

                        {/* Inspect CTA */}
                        <td className="py-1.5 px-2 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openCaseDrawer(c.caseId);
                            }}
                            className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-[9.5px] font-bold bg-indigo-50 dark:bg-indigo-600/20 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-600 hover:text-white border border-indigo-200 dark:border-indigo-500/30 transition-all cursor-pointer whitespace-nowrap"
                          >
                            <span>Inspect</span>
                            <ArrowRight className="w-2.5 h-2.5" />
                          </button>
                        </td>
                      </motion.tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={11} className="py-6 text-center text-slate-400">
                      <div className="flex flex-col items-center justify-center space-y-1">
                        <SlidersHorizontal className="w-5 h-5 text-slate-600 mb-1" />
                        <p className="text-[11px] font-semibold text-slate-300">No cases match the selected filters</p>
                        <p className="text-[10px] text-slate-500">Try resetting the status tab or search query</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Dynamic Footer with Actual Filtered Counts & Pagination */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-800/80 text-[11px] text-slate-400">
            <div>
              <span>
                Showing <strong className="text-white font-semibold">{paginatedCases.length > 0 ? (currentPage - 1) * itemsPerPage + 1 : 0}</strong> to{' '}
                <strong className="text-white font-semibold">{Math.min(currentPage * itemsPerPage, filteredCases.length)}</strong> of{' '}
                <strong className="text-white font-semibold">{filteredCases.length}</strong> cases
                {activeStatusTab !== 'All' && (
                  <span className="text-slate-500 ml-1">
                    ({activeTabMeta.count.toLocaleString()} in {activeStatusTab})
                  </span>
                )}
              </span>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center gap-1">
              <button 
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1 rounded bg-slate-950 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>

              {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  className={cn(
                    'w-6 h-6 rounded text-[10.5px] font-bold transition-all cursor-pointer flex items-center justify-center',
                    currentPage === pageNum
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/40 ring-1 ring-indigo-400/40'
                      : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-900'
                  )}
                >
                  {pageNum}
                </button>
              ))}

              <button 
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages || totalPages === 0}
                className="p-1 rounded bg-slate-950 border border-slate-800 text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
};
