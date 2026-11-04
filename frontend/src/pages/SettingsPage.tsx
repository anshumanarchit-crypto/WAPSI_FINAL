import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient, IntegrationsStatusResponse } from '../services/api/apiClient';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { Switch } from '../components/ui/Switch';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/Tooltip';
import { 
  Building2, 
  ShieldCheck, 
  Send, 
  Sliders, 
  Users, 
  Edit3, 
  Check, 
  ChevronDown, 
  ChevronRight, 
  IndianRupee, 
  ShoppingBag, 
  TrendingUp, 
  Coins, 
  Bell, 
  CheckCircle2, 
  FileText, 
  AlertTriangle, 
  Settings2, 
  Lock, 
  Download, 
  Clock, 
  Cpu, 
  Activity,
  Layers,
  PhoneCall,
  Zap,
  Sun,
  Moon,
  Key,
  Copy,
  RotateCw,
  Plus,
  Trash2,
  ExternalLink,
  MessageSquare,
  Smartphone,
  Mic,
  Globe,
  Database,
  Radio
} from 'lucide-react';
import { useDemoStore } from '../store/demoStore';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '../lib/utils';

type SettingsTab = 'merchant' | 'policies' | 'channels' | 'integrations' | 'team';
type BusinessTimeline = 'This Week' | 'This Month' | 'This Quarter' | 'Year to Date';

interface BusinessMetric {
  title: string;
  value: string;
  valueColor?: string;
  trend?: string;
  subtext?: string;
  icon: any;
  iconBg: string;
  iconColor: string;
  sparklineColor: string;
  sparklinePath: string;
}

const businessMetricsByTimeline: Record<BusinessTimeline, BusinessMetric[]> = {
  'This Week': [
    {
      title: 'Active Customers',
      value: '12,842',
      trend: '↗ 18.7% vs last 30 days',
      icon: Users,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,18 Q30,12 60,16 T120,8 T180,14 T240,4',
    },
    {
      title: 'Monthly GMV',
      value: '₹2.48Cr',
      trend: '↗ 16.3% vs last 30 days',
      icon: IndianRupee,
      iconBg: 'bg-blue-950/80 border-blue-500/30',
      iconColor: 'text-blue-400',
      sparklineColor: '#3B82F6',
      sparklinePath: 'M0,20 Q30,15 60,18 T120,10 T180,12 T240,3',
    },
    {
      title: 'Recovery Enabled',
      value: '100%',
      valueColor: 'text-purple-400',
      subtext: 'All payment methods',
      icon: ShieldCheck,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,16 Q40,16 80,12 T160,10 T240,6',
    },
    {
      title: 'Avg. Order Value',
      value: '₹1,932',
      trend: '↗ 4.8% vs last 30 days',
      icon: ShoppingBag,
      iconBg: 'bg-cyan-950/80 border-cyan-500/30',
      iconColor: 'text-cyan-400',
      sparklineColor: '#06B6D4',
      sparklinePath: 'M0,22 Q30,18 60,20 T120,14 T180,12 T240,5',
    },
    {
      title: 'Recovery Success Rate',
      value: '68.2%',
      trend: '↗ 6.2pp vs last 30 days',
      icon: TrendingUp,
      iconBg: 'bg-emerald-950/80 border-emerald-500/30',
      iconColor: 'text-emerald-400',
      sparklineColor: '#10B981',
      sparklinePath: 'M0,20 Q30,16 60,18 T120,12 T180,14 T240,4',
    },
    {
      title: 'Est. Incremental Recovery',
      value: '₹2.14L',
      trend: '↗ 37.6% vs last 30 days',
      icon: Coins,
      iconBg: 'bg-amber-950/80 border-amber-500/30',
      iconColor: 'text-amber-400',
      sparklineColor: '#F59E0B',
      sparklinePath: 'M0,22 Q30,18 60,16 T120,12 T180,8 T240,2',
    },
  ],
  'This Month': [
    {
      title: 'Active Customers',
      value: '51,368',
      trend: '↗ 21.4% vs last month',
      icon: Users,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,20 Q30,14 60,18 T120,9 T180,12 T240,3',
    },
    {
      title: 'Monthly GMV',
      value: '₹9.84Cr',
      trend: '↗ 19.8% vs last month',
      icon: IndianRupee,
      iconBg: 'bg-blue-950/80 border-blue-500/30',
      iconColor: 'text-blue-400',
      sparklineColor: '#3B82F6',
      sparklinePath: 'M0,22 Q30,16 60,19 T120,11 T180,10 T240,2',
    },
    {
      title: 'Recovery Enabled',
      value: '100%',
      valueColor: 'text-purple-400',
      subtext: 'All payment methods',
      icon: ShieldCheck,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,16 Q40,16 80,12 T160,10 T240,6',
    },
    {
      title: 'Avg. Order Value',
      value: '₹2,045',
      trend: '↗ 6.1% vs last month',
      icon: ShoppingBag,
      iconBg: 'bg-cyan-950/80 border-cyan-500/30',
      iconColor: 'text-cyan-400',
      sparklineColor: '#06B6D4',
      sparklinePath: 'M0,21 Q30,17 60,19 T120,13 T180,11 T240,4',
    },
    {
      title: 'Recovery Success Rate',
      value: '70.4%',
      trend: '↗ 7.8pp vs last month',
      icon: TrendingUp,
      iconBg: 'bg-emerald-950/80 border-emerald-500/30',
      iconColor: 'text-emerald-400',
      sparklineColor: '#10B981',
      sparklinePath: 'M0,19 Q30,15 60,17 T120,11 T180,13 T240,3',
    },
    {
      title: 'Est. Incremental Recovery',
      value: '₹8.62L',
      trend: '↗ 41.2% vs last month',
      icon: Coins,
      iconBg: 'bg-amber-950/80 border-amber-500/30',
      iconColor: 'text-amber-400',
      sparklineColor: '#F59E0B',
      sparklinePath: 'M0,23 Q30,17 60,15 T120,10 T180,7 T240,1',
    },
  ],
  'This Quarter': [
    {
      title: 'Active Customers',
      value: '154,104',
      trend: '↗ 24.1% vs last quarter',
      icon: Users,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,22 Q30,15 60,17 T120,8 T180,11 T240,2',
    },
    {
      title: 'Monthly GMV',
      value: '₹29.40Cr',
      trend: '↗ 22.4% vs last quarter',
      icon: IndianRupee,
      iconBg: 'bg-blue-950/80 border-blue-500/30',
      iconColor: 'text-blue-400',
      sparklineColor: '#3B82F6',
      sparklinePath: 'M0,23 Q30,17 60,18 T120,10 T180,9 T240,2',
    },
    {
      title: 'Recovery Enabled',
      value: '100%',
      valueColor: 'text-purple-400',
      subtext: 'All payment methods',
      icon: ShieldCheck,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,16 Q40,16 80,12 T160,10 T240,6',
    },
    {
      title: 'Avg. Order Value',
      value: '₹2,110',
      trend: '↗ 7.4% vs last quarter',
      icon: ShoppingBag,
      iconBg: 'bg-cyan-950/80 border-cyan-500/30',
      iconColor: 'text-cyan-400',
      sparklineColor: '#06B6D4',
      sparklinePath: 'M0,20 Q30,16 60,18 T120,12 T180,10 T240,3',
    },
    {
      title: 'Recovery Success Rate',
      value: '72.1%',
      trend: '↗ 8.9pp vs last quarter',
      icon: TrendingUp,
      iconBg: 'bg-emerald-950/80 border-emerald-500/30',
      iconColor: 'text-emerald-400',
      sparklineColor: '#10B981',
      sparklinePath: 'M0,18 Q30,14 60,16 T120,10 T180,12 T240,2',
    },
    {
      title: 'Est. Incremental Recovery',
      value: '₹25.80L',
      trend: '↗ 45.3% vs last quarter',
      icon: Coins,
      iconBg: 'bg-amber-950/80 border-amber-500/30',
      iconColor: 'text-amber-400',
      sparklineColor: '#F59E0B',
      sparklinePath: 'M0,24 Q30,18 60,14 T120,9 T180,6 T240,1',
    },
  ],
  'Year to Date': [
    {
      title: 'Active Customers',
      value: '616,416',
      trend: '↗ 26.5% vs 2024',
      icon: Users,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,24 Q30,16 60,18 T120,7 T180,10 T240,1',
    },
    {
      title: 'Monthly GMV',
      value: '₹118.2Cr',
      trend: '↗ 25.1% vs 2024',
      icon: IndianRupee,
      iconBg: 'bg-blue-950/80 border-blue-500/30',
      iconColor: 'text-blue-400',
      sparklineColor: '#3B82F6',
      sparklinePath: 'M0,24 Q30,18 60,19 T120,9 T180,8 T240,1',
    },
    {
      title: 'Recovery Enabled',
      value: '100%',
      valueColor: 'text-purple-400',
      subtext: 'All payment methods',
      icon: ShieldCheck,
      iconBg: 'bg-purple-950/80 border-purple-500/30',
      iconColor: 'text-purple-400',
      sparklineColor: '#A855F7',
      sparklinePath: 'M0,16 Q40,16 80,12 T160,10 T240,6',
    },
    {
      title: 'Avg. Order Value',
      value: '₹2,185',
      trend: '↗ 8.8% vs 2024',
      icon: ShoppingBag,
      iconBg: 'bg-cyan-950/80 border-cyan-500/30',
      iconColor: 'text-cyan-400',
      sparklineColor: '#06B6D4',
      sparklinePath: 'M0,20 Q30,15 60,17 T120,11 T180,9 T240,2',
    },
    {
      title: 'Recovery Success Rate',
      value: '73.8%',
      trend: '↗ 10.2pp vs 2024',
      icon: TrendingUp,
      iconBg: 'bg-emerald-950/80 border-emerald-500/30',
      iconColor: 'text-emerald-400',
      sparklineColor: '#10B981',
      sparklinePath: 'M0,17 Q30,13 60,15 T120,9 T180,11 T240,1',
    },
    {
      title: 'Est. Incremental Recovery',
      value: '₹103.4L',
      trend: '↗ 48.9% vs 2024',
      icon: Coins,
      iconBg: 'bg-amber-950/80 border-amber-500/30',
      iconColor: 'text-amber-400',
      sparklineColor: '#F59E0B',
      sparklinePath: 'M0,25 Q30,19 60,13 T120,8 T180,5 T240,1',
    },
  ],
};

export const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('merchant');
  const merchantSettings = useDemoStore((state) => state.merchantSettings);
  const setMerchantModalOpen = useDemoStore((state) => state.setMerchantModalOpen);
  const setUserManagementModalOpen = useDemoStore((state) => state.setUserManagementModalOpen);
  const theme = useDemoStore((state) => state.theme);
  const setTheme = useDemoStore((state) => state.setTheme);

  const { data: liveIntegrations } = useQuery<IntegrationsStatusResponse>({
    queryKey: ['integrations-status'],
    queryFn: () => apiClient.getIntegrationsStatus(),
    refetchInterval: 15000,
    staleTime: 10000,
  });

  // Business Overview Timeline Selector
  const [selectedTimeline, setSelectedTimeline] = useState<BusinessTimeline>('This Week');
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);

  // Notification Preferences State
  const [notifications, setNotifications] = useState({
    criticalAlerts: true,
    recoveryUpdates: true,
    dailySummary: true,
    policyViolations: true,
    systemUpdates: false,
  });

  // Delivery Channels State
  const [deliveryChannels, setDeliveryChannels] = useState({
    email: true,
    sms: true,
    inApp: true,
  });

  // Data Retention State
  const [retentionSettings, setRetentionSettings] = useState({
    recoveryCases: '24 Months',
    auditLogs: '36 Months',
    systemLogs: '12 Months',
    analyticsData: '24 Months',
  });

  const [activeRetentionDropdown, setActiveRetentionDropdown] = useState<string | null>(null);

  // Policy Settings State
  const [policyParams, setPolicyParams] = useState({
    confidenceThreshold: 90,
    upliftThreshold: 5,
    retryAttempts: 4,
    contactBudget: 5,
    dndEnabled: true,
    autoCooldown: true,
  });

  // API Key copy feedback
  const [copiedKey, setCopiedKey] = useState(false);

  // Global Date Sync
  const globalDateRange = useDemoStore((state) => state.selectedDateRange);
  const setSelectedDateRange = useDemoStore((state) => state.setSelectedDateRange);

  useEffect(() => {
    if (globalDateRange.includes('Month') || globalDateRange.includes('Aug 1 – Aug 28')) {
      setSelectedTimeline('This Month');
    } else if (globalDateRange.includes('Quarter') || globalDateRange.includes('90 Days') || globalDateRange.includes('Jun 1 – Aug 28')) {
      setSelectedTimeline('This Quarter');
    } else if (globalDateRange.includes('Year') || globalDateRange.includes('Jan 1 – Aug 28')) {
      setSelectedTimeline('Year to Date');
    } else {
      setSelectedTimeline('This Week');
    }
  }, [globalDateRange]);

  const handleTimelineSelect = (t: BusinessTimeline) => {
    setSelectedTimeline(t);
    setIsTimelineOpen(false);

    // Sync to global store
    if (t === 'This Week') setSelectedDateRange('Aug 22 – Aug 28, 2026');
    if (t === 'This Month') setSelectedDateRange('Aug 1 – Aug 28, 2026');
    if (t === 'This Quarter') setSelectedDateRange('Jun 1 – Aug 28, 2026');
    if (t === 'Year to Date') setSelectedDateRange('Jan 1 – Aug 28, 2026');
  };

  const copyApiKey = () => {
    navigator.clipboard.writeText('wap_live_928374_89f3a8b2c1d4e5f6');
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const tabs: { id: SettingsTab; label: string; icon: any }[] = [
    { id: 'merchant', label: 'Merchant', icon: Building2 },
    { id: 'policies', label: 'Recovery Policies', icon: ShieldCheck },
    { id: 'channels', label: 'Channels', icon: Send },
    { id: 'integrations', label: 'Integrations', icon: Sliders },
    { id: 'team', label: 'Team & Access', icon: Users },
  ];

  const currentMetrics = businessMetricsByTimeline[selectedTimeline] || businessMetricsByTimeline['This Week'];

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="space-y-4 max-w-[1600px] mx-auto pb-8"
    >
      <Topbar
        title="Settings"
        subtitle="Manage your recovery engine configuration"
      />

      {/* Settings Navigation Tabs matching Screenshot */}
      <div className="flex items-center gap-6 border-b border-slate-800 pb-2 text-xs font-semibold overflow-x-auto">
        {tabs.map((tab) => {
          const IconComp = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "pb-1 transition-colors cursor-pointer relative flex items-center gap-1.5",
                isActive 
                  ? "text-purple-300 font-bold" 
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <IconComp className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
              {isActive && (
                <motion.div 
                  layoutId="settingsTabUnderline" 
                  className="absolute -bottom-2 left-0 right-0 h-[2px] bg-purple-500 shadow-sm shadow-purple-500/50" 
                />
              )}
            </button>
          );
        })}
      </div>

      {/* TAB 1: MERCHANT VIEW */}
      {activeTab === 'merchant' && (
        <motion.div
          key="tab-merchant"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="space-y-4"
        >
          {/* Row 1: Merchant Profile (5 cols) & Business Overview (7 cols) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
            {/* Merchant Profile Card (5 cols) */}
            <div className="lg:col-span-5 flex flex-col">
              <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800/90 bg-[#0B101D]/95 space-y-4 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                    <div>
                      <CardTitle className="text-sm sm:text-base font-bold text-white">
                        Merchant Profile
                      </CardTitle>
                      <p className="text-[11px] text-slate-400 mt-0.5">View and update your business information</p>
                    </div>
                    
                    <button 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center gap-1.5 text-xs font-semibold text-purple-300 hover:text-white bg-purple-950/40 hover:bg-purple-900/60 border border-purple-500/40 px-3 py-1.5 rounded-xl cursor-pointer transition-all shadow-sm"
                    >
                      <Edit3 className="w-3.5 h-3.5 text-purple-400" />
                      <span>Edit Profile</span>
                    </button>
                  </div>

                  {/* Profile Body with Enclosed Avatar Box & 2-Column Info Grid */}
                  <div className="flex items-center gap-5 pt-3.5">
                    {/* Left Enclosed Avatar Box */}
                    <div className="w-32 h-36 rounded-2xl bg-[#070D1A]/90 border border-slate-800/90 flex flex-col items-center justify-center p-3 shrink-0 shadow-inner">
                      <div className="w-20 h-20 rounded-full bg-gradient-to-b from-[#111C35] to-[#091021] border border-blue-500/20 flex items-center justify-center shadow-lg">
                        <span className="text-base font-black text-white tracking-widest">
                          ACME
                        </span>
                      </div>
                      
                      {/* Verified Badge */}
                      <div className="mt-3 flex items-center gap-1.5 bg-emerald-950/80 border border-emerald-500/40 px-2.5 py-0.5 rounded-full text-[9.5px] font-bold text-emerald-400 shadow-sm">
                        <Check className="w-2.5 h-2.5 text-emerald-400 stroke-[3]" />
                        <span>VERIFIED</span>
                      </div>
                    </div>

                    {/* Right 2-Column Details Grid */}
                    <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-3.5 text-xs">
                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Merchant Name</span>
                        <span className="font-bold text-white text-[12px] sm:text-[13px] mt-0.5 block">Acme Corp</span>
                      </div>
                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Merchant ID</span>
                        <span className="font-mono font-semibold text-slate-200 text-[12px] sm:text-[13px] mt-0.5 block">MRC_928374</span>
                      </div>

                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Business Type</span>
                        <span className="text-slate-200 text-[12px] sm:text-[13px] font-medium mt-0.5 block">Subscription & Billing</span>
                      </div>
                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Industry</span>
                        <span className="text-slate-200 text-[12px] sm:text-[13px] font-medium mt-0.5 block">SaaS</span>
                      </div>

                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Website</span>
                        <a 
                          href="https://acmecorp.com" 
                          target="_blank" 
                          rel="noreferrer"
                          className="text-purple-400 hover:text-purple-300 text-[12px] sm:text-[13px] font-medium hover:underline mt-0.5 block truncate"
                        >
                          https://acmecorp.com
                        </a>
                      </div>
                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Registered Email</span>
                        <span className="text-slate-200 text-[12px] sm:text-[13px] font-mono mt-0.5 block truncate">finance@acmecorp.com</span>
                      </div>

                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Country</span>
                        <span className="text-slate-200 text-[12px] sm:text-[13px] font-medium mt-0.5 block">India</span>
                      </div>
                      <div>
                        <span className="text-slate-400 text-[10px] block font-medium">Time Zone</span>
                        <span className="text-slate-200 text-[12px] sm:text-[13px] font-medium truncate mt-0.5 block">(GMT+05:30) Asia/Kolkata</span>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            </div>

            {/* Business Overview Card (7 cols) - 6 Micro KPI Cards */}
            <div className="lg:col-span-7 flex flex-col">
              <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <div>
                      <CardTitle className="text-xs sm:text-sm font-bold text-white">
                        Business Overview
                      </CardTitle>
                      <p className="text-[10px] text-slate-400">Key business metrics</p>
                    </div>

                    {/* Timeline Dropdown Selector */}
                    <div className="relative">
                      <button
                        onClick={() => setIsTimelineOpen(!isTimelineOpen)}
                        className="flex items-center gap-1 text-[10.5px] font-semibold text-slate-300 bg-slate-900 border border-slate-800 hover:border-slate-700 px-2 py-0.5 rounded-lg cursor-pointer transition-colors shadow-sm"
                      >
                        <span>{selectedTimeline}</span>
                        <ChevronDown className={cn("w-3 h-3 text-slate-400 transition-transform", isTimelineOpen ? "rotate-180" : "")} />
                      </button>

                      {isTimelineOpen && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setIsTimelineOpen(false)} />
                          <div className="absolute right-0 mt-1 w-36 bg-[#090E1B] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                            {(['This Week', 'This Month', 'This Quarter', 'Year to Date'] as BusinessTimeline[]).map((opt) => {
                              const isSelected = selectedTimeline === opt;
                              return (
                                <button
                                  key={opt}
                                  onClick={() => handleTimelineSelect(opt)}
                                  className={cn(
                                    "w-full text-left px-3 py-1.5 text-xs font-medium flex items-center justify-between transition-colors cursor-pointer",
                                    isSelected 
                                      ? "bg-purple-600/20 text-purple-300 font-bold border-l-2 border-purple-500" 
                                      : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
                                  )}
                                >
                                  <span>{opt}</span>
                                  {isSelected && <Check className="w-3.5 h-3.5 text-purple-400" />}
                                </button>
                              );
                            })}
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 6 Micro KPI Cards with Glowing Sparkline Waves */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 pt-1">
                    {currentMetrics.map((kpi) => {
                      const IconComp = kpi.icon;
                      return (
                        <div 
                          key={kpi.title}
                          className="p-3 rounded-2xl bg-[#090F1E]/90 border border-slate-800/90 shadow-md relative overflow-hidden flex flex-col justify-between group hover:border-slate-700/80 transition-all"
                        >
                          <div className="space-y-1.5 relative z-10">
                            <div className="flex items-center gap-2">
                              <div className={cn("w-6 h-6 rounded-lg border flex items-center justify-center shrink-0", kpi.iconBg, kpi.iconColor)}>
                                <IconComp className="w-3 h-3" />
                              </div>
                              <span className="text-[10px] text-slate-400 font-medium truncate">
                                {kpi.title}
                              </span>
                            </div>

                            <div>
                              <div className={cn("text-xl font-black tabular-nums tracking-tight", kpi.valueColor || "text-white")}>
                                {kpi.value}
                              </div>
                              {kpi.trend && (
                                <div className="text-[9.5px] font-semibold text-emerald-400 mt-0.5">
                                  {kpi.trend}
                                </div>
                              )}
                              {kpi.subtext && (
                                <div className="text-[9.5px] font-medium text-slate-400 mt-0.5">
                                  {kpi.subtext}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Smooth Glowing Bottom Sparkline */}
                          <div className="pt-2 relative h-6 w-full overflow-hidden">
                            <svg viewBox="0 0 240 28" className="w-full h-full preserve-3d" fill="none">
                              <path
                                d={kpi.sparklinePath}
                                stroke={kpi.sparklineColor}
                                strokeWidth="2"
                                strokeLinecap="round"
                                className="drop-shadow-[0_0_6px_rgba(168,85,247,0.4)]"
                              />
                            </svg>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </Card>
            </div>
          </div>

          {/* Row 2: 3 Columns (Notification Preferences, Engine & Model Settings, Data Retention & Privacy) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
            {/* Col 1: Notification Preferences (4 cols) */}
            <div className="lg:col-span-4 flex flex-col">
              <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white">
                      Notification Preferences
                    </CardTitle>
                    <p className="text-[10px] text-slate-400">Choose how you want to be notified</p>
                  </div>

                  {/* 5 Toggle List Items */}
                  <div className="space-y-2.5 pt-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-amber-950/70 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
                          <Bell className="w-3 h-3" />
                        </div>
                        <div>
                          <span className="text-[11px] font-semibold text-white block">Critical Alerts</span>
                          <span className="text-[9.5px] text-slate-400 block">Failures, escalations, policy violations</span>
                        </div>
                      </div>
                      <Switch 
                        checked={notifications.criticalAlerts} 
                        onCheckedChange={(c) => setNotifications(prev => ({ ...prev, criticalAlerts: c }))} 
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-emerald-950/70 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shrink-0">
                          <CheckCircle2 className="w-3 h-3" />
                        </div>
                        <div>
                          <span className="text-[11px] font-semibold text-white block">Recovery Updates</span>
                          <span className="text-[9.5px] text-slate-400 block">Recovery success, action outcomes</span>
                        </div>
                      </div>
                      <Switch 
                        checked={notifications.recoveryUpdates} 
                        onCheckedChange={(c) => setNotifications(prev => ({ ...prev, recoveryUpdates: c }))} 
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-blue-950/70 border border-blue-500/40 flex items-center justify-center text-blue-400 shrink-0">
                          <FileText className="w-3 h-3" />
                        </div>
                        <div>
                          <span className="text-[11px] font-semibold text-white block">Daily Summary</span>
                          <span className="text-[9.5px] text-slate-400 block">Daily recovery summary and insights</span>
                        </div>
                      </div>
                      <Switch 
                        checked={notifications.dailySummary} 
                        onCheckedChange={(c) => setNotifications(prev => ({ ...prev, dailySummary: c }))} 
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-rose-950/70 border border-rose-500/40 flex items-center justify-center text-rose-400 shrink-0">
                          <AlertTriangle className="w-3 h-3" />
                        </div>
                        <div>
                          <span className="text-[11px] font-semibold text-white block">Policy Violations</span>
                          <span className="text-[9.5px] text-slate-400 block">Budget limits, attempt limits</span>
                        </div>
                      </div>
                      <Switch 
                        checked={notifications.policyViolations} 
                        onCheckedChange={(c) => setNotifications(prev => ({ ...prev, policyViolations: c }))} 
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-slate-900 border border-slate-700 flex items-center justify-center text-slate-400 shrink-0">
                          <Settings2 className="w-3 h-3" />
                        </div>
                        <div>
                          <span className="text-[11px] font-semibold text-white block">System Updates</span>
                          <span className="text-[9.5px] text-slate-400 block">Product updates and maintenance</span>
                        </div>
                      </div>
                      <Switch 
                        checked={notifications.systemUpdates} 
                        onCheckedChange={(c) => setNotifications(prev => ({ ...prev, systemUpdates: c }))} 
                      />
                    </div>
                  </div>
                </div>

                {/* Delivery Channels */}
                <div className="pt-2.5 border-t border-slate-800 space-y-1.5">
                  <span className="text-[10px] text-slate-400 font-bold tracking-wider block">
                    Delivery Channels
                  </span>
                  <div className="flex items-center gap-4 text-xs">
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 hover:text-white">
                      <input
                        type="checkbox"
                        checked={deliveryChannels.email}
                        onChange={(e) => setDeliveryChannels(prev => ({ ...prev, email: e.target.checked }))}
                        className="rounded border-slate-700 bg-slate-900 text-purple-600 focus:ring-0 w-3.5 h-3.5"
                      />
                      <span className="text-[11px]">Email</span>
                    </label>

                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 hover:text-white">
                      <input
                        type="checkbox"
                        checked={deliveryChannels.sms}
                        onChange={(e) => setDeliveryChannels(prev => ({ ...prev, sms: e.target.checked }))}
                        className="rounded border-slate-700 bg-slate-900 text-purple-600 focus:ring-0 w-3.5 h-3.5"
                      />
                      <span className="text-[11px]">SMS</span>
                    </label>

                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300 hover:text-white">
                      <input
                        type="checkbox"
                        checked={deliveryChannels.inApp}
                        onChange={(e) => setDeliveryChannels(prev => ({ ...prev, inApp: e.target.checked }))}
                        className="rounded border-slate-700 bg-slate-900 text-purple-600 focus:ring-0 w-3.5 h-3.5"
                      />
                      <span className="text-[11px]">In-app</span>
                    </label>
                  </div>
                </div>
              </Card>
            </div>

            {/* Col 2: Engine & Model Settings (4 cols) */}
            <div className="lg:col-span-4 flex flex-col">
              <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white">
                      Engine & Model Settings
                    </CardTitle>
                    <p className="text-[10px] text-slate-400">Configure recovery engine behavior</p>
                  </div>

                  {/* 6 Engine Setting Rows */}
                  <div className="space-y-2 pt-2 text-xs">
                    <div 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center justify-between p-1.5 hover:bg-slate-900/60 rounded-xl transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-300" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Decision Confidence Threshold</span>
                          <span className="text-[9px] text-slate-400 block">Minimum confidence to auto-execute</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono text-purple-300 font-bold">
                        <span>{policyParams.confidenceThreshold}%</span>
                        <ChevronRight className="w-3 h-3 text-slate-500" />
                      </div>
                    </div>

                    <div 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center justify-between p-1.5 hover:bg-slate-900/60 rounded-xl transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <Zap className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-300" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Minimum Uplift Threshold</span>
                          <span className="text-[9px] text-slate-400 block">Minimum incremental uplift vs no action</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono text-purple-300 font-bold">
                        <span>+{policyParams.upliftThreshold}%</span>
                        <ChevronRight className="w-3 h-3 text-slate-500" />
                      </div>
                    </div>

                    <div 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center justify-between p-1.5 hover:bg-slate-900/60 rounded-xl transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-300" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Retry Attempt Limit</span>
                          <span className="text-[9px] text-slate-400 block">Max retry attempts per case</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono text-slate-300 font-bold">
                        <span>{policyParams.retryAttempts} attempts</span>
                        <ChevronRight className="w-3 h-3 text-slate-500" />
                      </div>
                    </div>

                    <div 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center justify-between p-1.5 hover:bg-slate-900/60 rounded-xl transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <PhoneCall className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-300" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Contact Budget (per customer)</span>
                          <span className="text-[9px] text-slate-400 block">Max contacts across all channels</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono text-slate-300 font-bold">
                        <span>{policyParams.contactBudget} contacts</span>
                        <ChevronRight className="w-3 h-3 text-slate-500" />
                      </div>
                    </div>

                    <div 
                      onClick={() => setMerchantModalOpen(true)}
                      className="flex items-center justify-between p-1.5 hover:bg-slate-900/60 rounded-xl transition-colors cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-300" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Recovery Window</span>
                          <span className="text-[9px] text-slate-400 block">Time window to attempt recovery</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 text-[10.5px] font-mono text-slate-300 font-bold">
                        <span>24 – 72 hrs</span>
                        <ChevronRight className="w-3 h-3 text-slate-500" />
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-1.5">
                      <div className="flex items-center gap-2">
                        <Cpu className="w-3.5 h-3.5 text-slate-400" />
                        <div>
                          <span className="text-[10.5px] font-semibold text-white block">Model Version</span>
                          <span className="text-[9px] text-slate-400 block">Currently active model</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px] font-mono">
                        <span className="text-slate-300">v2.3.1 (Latest)</span>
                        <span className="px-1.5 py-0.2 rounded bg-emerald-950/80 border border-emerald-500/40 text-emerald-400 font-bold text-[8.5px]">
                          ACTIVE
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom Link */}
                <div className="pt-2 border-t border-slate-800">
                  <button 
                    onClick={() => setMerchantModalOpen(true)}
                    className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <span>View model performance</span>
                    <span>&gt;</span>
                  </button>
                </div>
              </Card>
            </div>

            {/* Col 3: Data Retention & Privacy (4 cols) */}
            <div className="lg:col-span-4 flex flex-col">
              <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white">
                      Data Retention & Privacy
                    </CardTitle>
                    <p className="text-[10px] text-slate-400">Manage how long data is retained and protected</p>
                  </div>

                  {/* 4 Retention Rows with Selectors */}
                  <div className="space-y-1.5 pt-2 text-xs">
                    {[
                      { id: 'recoveryCases', label: 'Recovery Cases', current: retentionSettings.recoveryCases, options: ['12 Months', '24 Months', '36 Months', 'Indefinite'] },
                      { id: 'auditLogs', label: 'Audit Logs', current: retentionSettings.auditLogs, options: ['12 Months', '24 Months', '36 Months', '7 Years (Statutory)'] },
                      { id: 'systemLogs', label: 'System Logs', current: retentionSettings.systemLogs, options: ['6 Months', '12 Months', '24 Months'] },
                      { id: 'analyticsData', label: 'Analytics Data', current: retentionSettings.analyticsData, options: ['12 Months', '24 Months', '36 Months', '5 Years'] },
                    ].map((item) => (
                      <div key={item.id} className="flex items-center justify-between py-1 relative">
                        <span className="text-[11px] text-slate-300">{item.label}</span>
                        <div className="relative">
                          <button
                            onClick={() => setActiveRetentionDropdown(activeRetentionDropdown === item.id ? null : item.id)}
                            className="flex items-center gap-1 text-[10.5px] font-mono text-slate-200 bg-slate-900 border border-slate-800 hover:border-slate-700 px-2 py-0.5 rounded-lg cursor-pointer"
                          >
                            <span>{item.current}</span>
                            <ChevronDown className="w-3 h-3 text-slate-400" />
                          </button>

                          {activeRetentionDropdown === item.id && (
                            <>
                              <div className="fixed inset-0 z-40" onClick={() => setActiveRetentionDropdown(null)} />
                              <div className="absolute right-0 mt-1 w-32 bg-[#090E1B] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                                {item.options.map((opt) => (
                                  <button
                                    key={opt}
                                    onClick={() => {
                                      setRetentionSettings(prev => ({ ...prev, [item.id]: opt }));
                                      setActiveRetentionDropdown(null);
                                    }}
                                    className="w-full text-left px-2.5 py-1 text-[10.5px] text-slate-300 hover:bg-slate-800 hover:text-white block"
                                  >
                                    {opt}
                                  </button>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Purple Encrypted Storage Notice Box */}
                  <div className="mt-3 p-2.5 rounded-xl bg-[#140F28]/90 border border-purple-500/40 flex items-center gap-2.5 shadow-sm">
                    <div className="w-6 h-6 rounded-lg bg-purple-950/80 border border-purple-500/40 flex items-center justify-center text-purple-400 shrink-0">
                      <Lock className="w-3 h-3" />
                    </div>
                    <p className="text-[10px] text-slate-300 leading-tight">
                      Data is encrypted and stored securely in Razorpay's infrastructure
                    </p>
                  </div>
                </div>

                {/* Download Link */}
                <div className="pt-2 border-t border-slate-800">
                  <button className="text-[10.5px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1.5 transition-colors cursor-pointer">
                    <Download className="w-3 h-3" />
                    <span>Download Data Retention Policy</span>
                  </button>
                </div>
              </Card>
            </div>
          </div>

          {/* Row 3: Dedicated Theme & Appearance Selector Card */}
          <Card className="p-4 sm:p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-xl backdrop-blur-md">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-2">
                  <Sun className="w-4 h-4 text-amber-400" />
                  <span>Appearance & Interface Theme</span>
                </CardTitle>
                <p className="text-[10px] text-slate-400">Switch color mode for high readability and visual comfort</p>
              </div>

              <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <button
                  onClick={() => setTheme('dark')}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer",
                    theme === 'dark' 
                      ? "bg-purple-600 text-white shadow-md shadow-purple-600/30" 
                      : "text-slate-400 hover:text-white"
                  )}
                >
                  <Moon className="w-3.5 h-3.5" />
                  <span>Dark Mode</span>
                </button>

                <button
                  onClick={() => setTheme('light')}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer",
                    theme === 'light' 
                      ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30" 
                      : "text-slate-400 hover:text-white"
                  )}
                >
                  <Sun className="w-3.5 h-3.5" />
                  <span>Light Mode</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
              <div 
                onClick={() => setTheme('dark')}
                className={cn(
                  "p-3 rounded-xl border cursor-pointer transition-all flex items-center gap-3",
                  theme === 'dark' ? "border-purple-500/80 bg-purple-950/20" : "border-slate-800 bg-slate-950 hover:border-slate-700"
                )}
              >
                <div className="w-10 h-10 rounded-lg bg-[#070B14] border border-purple-500/30 flex items-center justify-center text-purple-400 font-bold">
                  🌙
                </div>
                <div>
                  <span className="font-bold text-white block">Deep Cyber Night (Default)</span>
                  <span className="text-[10px] text-slate-400 block">Optimized for mission control operations with neon indicators</span>
                </div>
              </div>

              <div 
                onClick={() => setTheme('light')}
                className={cn(
                  "p-3 rounded-xl border cursor-pointer transition-all flex items-center gap-3",
                  theme === 'light' ? "border-indigo-500/80 bg-indigo-950/20" : "border-slate-800 bg-slate-950 hover:border-slate-700"
                )}
              >
                <div className="w-10 h-10 rounded-lg bg-slate-100 border border-slate-300 flex items-center justify-center text-indigo-600 font-bold">
                  ☀️
                </div>
                <div>
                  <span className="font-bold text-white block">Daylight Clarity (Light)</span>
                  <span className="text-[10px] text-slate-400 block">High-contrast, crisp slate palette for bright office environments</span>
                </div>
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {/* TAB 2: RECOVERY POLICIES */}
      {activeTab === 'policies' && (
        <motion.div
          key="tab-policies"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="space-y-4"
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Guardrail Rules Editor */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800">
                <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-purple-400" />
                  <span>Deterministic Regulatory Bounds</span>
                </CardTitle>
                <p className="text-[10.5px] text-slate-400">NPCI and TRAI hard thresholds enforced on all autonomous actions</p>
              </div>

              <div className="space-y-4 text-xs">
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="font-medium text-white">NPCI Retry Attempt Limit ({policyParams.retryAttempts} max)</span>
                    <span className="font-mono text-purple-400 font-bold">{policyParams.retryAttempts} Attempts</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="6"
                    value={policyParams.retryAttempts}
                    onChange={(e) => setPolicyParams(p => ({ ...p, retryAttempts: Number(e.target.value) }))}
                    className="w-full accent-purple-500 cursor-pointer"
                  />
                  <span className="text-[9.5px] text-slate-400">Strictly caps automated gateway retries to prevent issuer fatigue penalty</span>
                </div>

                <div>
                  <div className="flex justify-between mb-1">
                    <span className="font-medium text-white">TRAI Contact Budget ({policyParams.contactBudget} contacts)</span>
                    <span className="font-mono text-emerald-400 font-bold">{policyParams.contactBudget} Total</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="8"
                    value={policyParams.contactBudget}
                    onChange={(e) => setPolicyParams(p => ({ ...p, contactBudget: Number(e.target.value) }))}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                  <span className="text-[9.5px] text-slate-400">Maximum customer communications across WhatsApp, SMS, and Voice</span>
                </div>

                <div>
                  <div className="flex justify-between mb-1">
                    <span className="font-medium text-white">Confidence Cutoff Threshold ({policyParams.confidenceThreshold}%)</span>
                    <span className="font-mono text-cyan-400 font-bold">{policyParams.confidenceThreshold}%</span>
                  </div>
                  <input
                    type="range"
                    min="70"
                    max="99"
                    value={policyParams.confidenceThreshold}
                    onChange={(e) => setPolicyParams(p => ({ ...p, confidenceThreshold: Number(e.target.value) }))}
                    className="w-full accent-cyan-500 cursor-pointer"
                  />
                  <span className="text-[9.5px] text-slate-400">Actions with model confidence below this threshold require Human-in-the-Loop review</span>
                </div>
              </div>
            </Card>

            {/* Silence Windows & Cooldowns */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800">
                <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                  <Clock className="w-4 h-4 text-amber-400" />
                  <span>TRAI Do-Not-Disturb & Cooldown Rules</span>
                </CardTitle>
                <p className="text-[10.5px] text-slate-400">Timing guardrails to ensure zero customer harassment</p>
              </div>

              <div className="space-y-4 text-xs">
                <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <div>
                    <span className="font-semibold text-white block">Night Silence Window (10 PM – 8 AM IST)</span>
                    <span className="text-[10px] text-slate-400">Automatically pauses all customer WhatsApp/SMS nudges during DND hours</span>
                  </div>
                  <Switch 
                    checked={policyParams.dndEnabled} 
                    onCheckedChange={(c) => setPolicyParams(p => ({ ...p, dndEnabled: c }))} 
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <div>
                    <span className="font-semibold text-white block">24h Fatigue Cooldown Protection</span>
                    <span className="text-[10px] text-slate-400">Guarantees a minimum 24h gap before re-contacting the same customer</span>
                  </div>
                  <Switch 
                    checked={policyParams.autoCooldown} 
                    onCheckedChange={(c) => setPolicyParams(p => ({ ...p, autoCooldown: c }))} 
                  />
                </div>

                <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/30 text-[10.5px] text-emerald-300">
                  ✓ All rules are compiled directly into the hardware-isolated TEE simulation boundary.
                </div>
              </div>
            </Card>
          </div>
        </motion.div>
      )}

      {/* TAB 3: CHANNELS */}
      {activeTab === 'channels' && (
        <motion.div
          key="tab-channels"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="space-y-4"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { name: 'WhatsApp Business API', provider: 'Meta Cloud API', icon: MessageSquare, iconColor: 'text-emerald-400', status: 'Connected', health: '99.8%', latency: '450ms', badge: 'Primary' },
              { name: 'SMS Smart Gateway', provider: 'Twilio / Karix DLT', icon: Smartphone, iconColor: 'text-blue-400', status: 'Connected', health: '99.5%', latency: '820ms', badge: 'Fallback' },
              { name: 'AI Voice Assistant', provider: 'Exotel + Deepgram', icon: Mic, iconColor: 'text-purple-400', status: 'Active', health: '98.9%', latency: '350ms', badge: 'High Value' },
              { name: 'In-App Webhooks', provider: 'Merchant SDK v4.2', icon: Radio, iconColor: 'text-cyan-400', status: 'Live', health: '100%', latency: '28ms', badge: 'Instant' },
            ].map((ch) => {
              const IconComp = ch.icon;
              return (
                <Card key={ch.name} className="p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-3 shadow-xl flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                      <div className="flex items-center gap-2">
                        <div className={cn("w-7 h-7 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center", ch.iconColor)}>
                          <IconComp className="w-3.5 h-3.5" />
                        </div>
                        <span className="font-bold text-white text-xs">{ch.name}</span>
                      </div>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {ch.status}
                      </span>
                    </div>

                    <div className="space-y-1.5 pt-2 text-xs">
                      <div className="flex justify-between text-[10.5px]">
                        <span className="text-slate-400">Provider</span>
                        <span className="font-medium text-white">{ch.provider}</span>
                      </div>
                      <div className="flex justify-between text-[10.5px]">
                        <span className="text-slate-400">Uptime Health</span>
                        <span className="font-mono text-emerald-400 font-bold">{ch.health}</span>
                      </div>
                      <div className="flex justify-between text-[10.5px]">
                        <span className="text-slate-400">Mean Latency</span>
                        <span className="font-mono text-slate-300">{ch.latency}</span>
                      </div>
                    </div>
                  </div>

                  <button className="w-full mt-2 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-[11px] font-semibold text-purple-300 hover:bg-slate-800 cursor-pointer transition-colors">
                    Configure Channel &gt;
                  </button>
                </Card>
              );
            })}
          </div>
        </motion.div>
      )}

      {/* TAB 4: INTEGRATIONS */}
      {activeTab === 'integrations' && (
        <motion.div
          key="tab-integrations"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="space-y-4"
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Razorpay Integration */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <Globe className="w-4 h-4 text-blue-400" />
                    <span>Razorpay Payment Gateway Integration</span>
                  </CardTitle>
                  <p className="text-[10.5px] text-slate-400">Deterministic webhook & Payment Link synchronization</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {liveIntegrations?.razorpay?.ready ? 'READY / VERIFIED' : 'TEST MODE'}
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Gateway Mode</span>
                    <span className="font-mono text-emerald-400 font-bold uppercase text-xs">{liveIntegrations?.razorpay?.mode || 'test'}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Key ID (Masked)</span>
                    <span className="font-mono text-slate-200 text-xs">{liveIntegrations?.razorpay?.masked_key_id || 'rzp_test_****bdqI'}</span>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Public Webhook Receiver Endpoint</span>
                  <span className="font-mono text-slate-300 text-[11px] select-all block mt-0.5">
                    /api/v1/webhooks/razorpay (HMAC-SHA256 Protected)
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">API Secret Configured</span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">Webhook Secret Valid</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* WhatsApp Meta Cloud API */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <Send className="w-4 h-4 text-emerald-400" />
                    <span>WhatsApp Cloud API (Meta Graph v26.0)</span>
                  </CardTitle>
                  <p className="text-[10.5px] text-slate-400">Direct transactional nudges & interactive button links</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {liveIntegrations?.whatsapp_cloud_api?.configured ? 'OPERATIONAL' : 'CONFIGURED'}
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Business Account (WABA)</span>
                    <span className="font-mono text-purple-300 font-bold text-xs">{liveIntegrations?.whatsapp_cloud_api?.business_account_id || '969727602419694'}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Phone Number ID</span>
                    <span className="font-mono text-slate-200 text-xs">{liveIntegrations?.whatsapp_cloud_api?.phone_number_id || '1407090562487899'}</span>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">Inbound Webhook Verification URL</span>
                  <span className="font-mono text-slate-300 text-[11px] select-all block mt-0.5">
                    /api/v1/webhooks/whatsapp (hub.challenge & signature validated)
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">System User Token Active</span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">Meta App Secret Verified</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Persistence & Multi-Tenant Database */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-purple-400" />
                    <span>Supabase / PostgreSQL Persistence</span>
                  </CardTitle>
                  <p className="text-[10.5px] text-slate-400">Multi-tenant transactional database with row-level security</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {liveIntegrations?.database?.status === 'healthy' ? 'CONNECTED' : 'STANDBY'}
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Engine</span>
                    <span className="font-mono text-white font-bold text-xs uppercase">{liveIntegrations?.database?.dialect || 'postgresql'}</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Latency</span>
                    <span className="font-mono text-cyan-400 font-bold text-xs">{liveIntegrations?.database?.latency_ms || 119}ms</span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-medium">Tenant Context</span>
                    <span className="font-mono text-emerald-400 font-bold text-xs">ENFORCED</span>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-slate-300 space-y-1">
                  <div>• RLS Tenant Isolation via <code className="text-indigo-300">app.current_merchant_id</code> session context</div>
                  <div>• SKIP LOCKED worker queueing for zero duplicate outbox leases</div>
                  <div>• Immutable tamper-evident audit ledger with SHA-256 block chains</div>
                </div>
              </div>
            </Card>

            {/* Confidential Computing TEE Enclave */}
            <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
              <div className="pb-2 border-b border-slate-800 flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <Lock className="w-4 h-4 text-cyan-400" />
                    <span>Confidential Computing Enclave Boundary</span>
                  </CardTitle>
                  <p className="text-[10.5px] text-slate-400">Cryptographic attestation & zero-copy PII masking</p>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  ATTESTED
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-medium">PCR-0 Measurement Hash</span>
                  <span className="font-mono text-slate-300 text-[11px] block truncate">
                    2d54fff6b7e916991f758d2a1dc6c63a36dab8652dfbe67295ab34e08b12044d
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">PII Zero-Knowledge Masking</span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-slate-300">Fail-Closed Boundary</span>
                  </div>
                </div>

                <p className="text-[11px] text-slate-400">
                  Signature Algorithm: <strong className="text-white font-mono">ECDSA-P256-SHA256</strong> (Hardware-Isolated Execution Simulator).
                </p>
              </div>
            </Card>
          </div>
        </motion.div>
      )}

      {/* TAB 5: TEAM & ACCESS */}
      {activeTab === 'team' && (
        <motion.div
          key="tab-team"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="space-y-4"
        >
          <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div>
                <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                  <Users className="w-4 h-4 text-purple-400" />
                  <span>Team Operators & RBAC Roles</span>
                </CardTitle>
                <p className="text-[10.5px] text-slate-400">Role-based access control with granular causal simulation privileges</p>
              </div>

              <button 
                onClick={() => setUserManagementModalOpen(true)}
                className="flex items-center gap-1.5 text-xs font-semibold text-white bg-purple-600 hover:bg-purple-500 px-3 py-1.5 rounded-xl cursor-pointer shadow-md shadow-purple-600/30"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Invite Operator</span>
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold">
                    <th className="py-2 px-3">MEMBER</th>
                    <th className="py-2 px-3">ROLE</th>
                    <th className="py-2 px-3">STATUS</th>
                    <th className="py-2 px-3">LAST ACTIVE</th>
                    <th className="py-2 px-3 text-right">ACTION</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {[
                    { name: 'Arpit', email: 'arpit@acmecorp.com', role: 'Principal Architect (Admin)', status: 'Active', last: 'Just now' },
                    { name: 'Priya Sharma', email: 'priya.s@acmecorp.com', role: 'Risk Officer', status: 'Active', last: '2 hours ago' },
                    { name: 'Rohan Mehta', email: 'rohan.m@acmecorp.com', role: 'Recovery Ops Analyst', status: 'Active', last: 'Yesterday' },
                    { name: 'Kavita Verma', email: 'kavita.v@acmecorp.com', role: 'Compliance Auditor', status: 'Active', last: '3 days ago' },
                  ].map((m) => (
                    <tr key={m.email} className="hover:bg-slate-900/50">
                      <td className="py-2.5 px-3">
                        <div className="font-semibold text-white">{m.name}</div>
                        <div className="text-[10px] text-slate-400 font-mono">{m.email}</div>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                          {m.role}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          {m.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 tabular-nums text-[11px]">
                        {m.last}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button className="text-[11px] text-slate-400 hover:text-white cursor-pointer">
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Page Footer */}
      <div className="pt-4 flex flex-col sm:flex-row items-center justify-between text-[10.5px] text-slate-500 border-t border-slate-800/80 gap-2">
        <div>© 2026 WAPSI by Razorpay • All rights reserved</div>
        <div className="flex items-center gap-4">
          <a href="#" className="hover:text-slate-400 transition-colors">Privacy Policy</a>
          <a href="#" className="hover:text-slate-400 transition-colors">Terms of Service</a>
          <a href="#" className="hover:text-slate-400 transition-colors">Security</a>
        </div>
      </div>
    </motion.div>
  );
};
