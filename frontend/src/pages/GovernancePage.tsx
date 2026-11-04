import React, { useState, useEffect } from 'react';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../components/ui/Tooltip';
import {
  ShieldCheck,
  ShieldAlert,
  UserCheck,
  Bot,
  Info,
  CheckCircle2,
  Lock,
  ChevronDown,
  TrendingUp,
  Layers,
  Clock,
  PhoneCall,
  Zap,
  Activity,
  CreditCard,
  Check,
  SlidersHorizontal
} from 'lucide-react';
import { formatINR } from '../lib/formatting';
import { cn } from '../lib/utils';
import { motion } from 'framer-motion';
import { useDemoStore } from '../store/demoStore';
import { useGovernance } from '../hooks/useGovernance';

interface TopKpiProps {
  icon: any;
  iconBg: string;
  iconBorder: string;
  iconColor: string;
  title: string;
  value: string;
  valueColor?: string;
  trend: string;
  trendType: 'positive' | 'warning' | 'info' | 'purple';
  cardBg: string;
  cardBorder: string;
  bars: number[];
  barColor: string;
}

const MicroBarChart: React.FC<{ bars: number[]; color: string }> = ({ bars, color }) => {
  return (
    <div className="flex items-end gap-[3px] h-6 w-full pt-1">
      {bars.map((h, i) => (
        <div
          key={i}
          className={cn("flex-1 rounded-[1px] transition-all opacity-80 hover:opacity-100", color)}
          style={{ height: `${Math.max(15, Math.min(100, h))}%` }}
        />
      ))}
    </div>
  );
};

type GovernanceTimeline = 'This Week' | 'This Month' | 'This Quarter' | 'Year to Date';
type AuditCaseKey = 'RX-48291' | 'RX-91823' | 'RX-34901' | 'RX-78214';

interface GovernanceTimelineDataset {
  label: string;
  policyChecks: string;
  policyChecksDelta: string;
  policyChecksBars: number[];

  actionsBlocked: string;
  actionsBlockedDelta: string;
  actionsBlockedBars: number[];

  violations: string;
  violationsDelta: string;
  violationsBars: number[];

  manualReviews: string;
  manualReviewsDelta: string;
  manualReviewsBars: number[];

  autonomousActions: string;
  autonomousActionsDelta: string;
  autonomousActionsBars: number[];

  activeBoundsCount: number;
  policyControls: {
    id: string;
    icon: any;
    iconColor: string;
    iconBg: string;
    name: string;
    description: string;
    badge: string;
    badgeBg: string;
    minLabel: string;
    maxLabel: string;
    percent: number;
    segments: { width: string; color: string }[];
    status: string;
    compliance: string;
    complianceColor: string;
  }[];

  fairnessSegments: {
    name: string;
    cases: string;
    uplift: string;
    gap: string;
    status: string;
  }[];

  modelFairness: {
    disparateImpact: string;
    equalOpportunity: string;
    calibrationGap: string;
    overall: string;
  };
}

const governanceDataByTimeline: Record<GovernanceTimeline, GovernanceTimelineDataset> = {
  'This Week': {
    label: 'This Week',
    policyChecks: '12,842',
    policyChecksDelta: '↗ 18.7% vs last 7 days',
    policyChecksBars: [30, 45, 60, 40, 75, 50, 65, 80, 55, 90, 70, 85, 95, 60, 75, 85, 90, 100],
    actionsBlocked: '214',
    actionsBlockedDelta: '↘ 23.4% vs last 7 days',
    actionsBlockedBars: [80, 65, 75, 90, 70, 85, 60, 75, 55, 65, 50, 45, 40, 35, 30, 25, 20, 15],
    violations: '0',
    violationsDelta: 'Great! No violations',
    violationsBars: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    manualReviews: '184',
    manualReviewsDelta: '↗ 8.2% vs last 7 days',
    manualReviewsBars: [30, 40, 45, 55, 50, 65, 60, 70, 75, 65, 80, 85, 70, 75, 80, 85, 90, 95],
    autonomousActions: '92.6%',
    autonomousActionsDelta: '↗ 5.3pp vs last 7 days',
    autonomousActionsBars: [60, 65, 70, 75, 70, 80, 85, 80, 88, 90, 85, 92, 90, 94, 91, 95, 93, 96],
    activeBoundsCount: 8,
    policyControls: [
      { id: 'npci', icon: Layers, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/40', name: 'NPCI Attempt Limit', description: 'Max retry attempts allowed', badge: '3 / 4', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '4', percent: 75, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '98%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'trai', icon: PhoneCall, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/40', name: 'Contact Budget (TRAI)', description: 'Max contacts per customer', badge: '3 / 5', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '5', percent: 60, segments: [{ width: '60%', color: 'bg-emerald-500' }, { width: '25%', color: 'bg-amber-500' }, { width: '15%', color: 'bg-rose-500' }], status: '87%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'merchant', icon: TrendingUp, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/40', name: 'Merchant Daily Limit', description: 'Max contacts per day', badge: '42%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '100%', percent: 42, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '68%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'confidence', icon: ShieldCheck, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Confidence Threshold', description: 'Minimum confidence required', badge: '95%', badgeBg: 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300', minLabel: '80%', maxLabel: '100%', percent: 75, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '96%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'window', icon: Clock, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Recovery Window', description: 'Allowed time window for action', badge: 'Within Window', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0h', maxLabel: '72h', percent: 40, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '93%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'uplift', icon: Zap, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Uplift Threshold', description: 'Minimum uplift vs no action', badge: '+5%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '25%', percent: 30, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '90%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'card-fatigue', icon: CreditCard, iconColor: 'text-indigo-400', iconBg: 'bg-indigo-950/70 border-indigo-500/40', name: 'Card Fatigue Cool-off', description: 'Minimum gap between recurring card retries', badge: '24h / 48h', badgeBg: 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300', minLabel: '0h', maxLabel: '48h', percent: 50, segments: [{ width: '80%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }], status: '95%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'settlement-cap', icon: Activity, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Max Automated Settlement Cap', description: 'Autonomous execution transaction ceiling', badge: '₹50K / ₹1L', badgeBg: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300', minLabel: '₹0', maxLabel: '₹1L', percent: 50, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '100%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
    ],
    fairnessSegments: [
      { name: 'New vs Existing', cases: '4,231', uplift: '+22.1%', gap: '2.3pp', status: 'Fair' },
      { name: 'High vs Low Value', cases: '3,982', uplift: '+21.4%', gap: '1.8pp', status: 'Fair' },
      { name: 'Region (Tier 1 vs 2/3)', cases: '5,104', uplift: '+20.7%', gap: '2.6pp', status: 'Fair' },
      { name: 'Issuer (Top vs Others)', cases: '6,211', uplift: '+19.6%', gap: '2.1pp', status: 'Fair' },
    ],
    modelFairness: {
      disparateImpact: '0.92',
      equalOpportunity: '0.91',
      calibrationGap: '1.8%',
      overall: 'Fair',
    },
  },
  'This Month': {
    label: 'This Month',
    policyChecks: '51,368',
    policyChecksDelta: '↗ 21.4% vs last month',
    policyChecksBars: [40, 55, 65, 50, 80, 60, 75, 88, 65, 92, 78, 88, 96, 70, 82, 90, 94, 100],
    actionsBlocked: '856',
    actionsBlockedDelta: '↘ 19.8% vs last month',
    actionsBlockedBars: [70, 60, 68, 82, 65, 78, 55, 70, 50, 60, 45, 40, 38, 32, 28, 22, 18, 12],
    violations: '0',
    violationsDelta: 'Great! No violations',
    violationsBars: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    manualReviews: '736',
    manualReviewsDelta: '↗ 6.5% vs last month',
    manualReviewsBars: [35, 45, 50, 60, 55, 70, 65, 75, 80, 70, 85, 88, 75, 80, 85, 90, 92, 96],
    autonomousActions: '93.1%',
    autonomousActionsDelta: '↗ 4.8pp vs last month',
    autonomousActionsBars: [65, 70, 75, 80, 75, 85, 88, 85, 90, 92, 88, 94, 92, 96, 94, 96, 95, 98],
    activeBoundsCount: 8,
    policyControls: [
      { id: 'npci', icon: Layers, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/40', name: 'NPCI Attempt Limit', description: 'Max retry attempts allowed', badge: '3 / 4', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '4', percent: 75, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '98.4%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'trai', icon: PhoneCall, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/40', name: 'Contact Budget (TRAI)', description: 'Max contacts per customer', badge: '3 / 5', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '5', percent: 60, segments: [{ width: '60%', color: 'bg-emerald-500' }, { width: '25%', color: 'bg-amber-500' }, { width: '15%', color: 'bg-rose-500' }], status: '89.2%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'merchant', icon: TrendingUp, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/40', name: 'Merchant Daily Limit', description: 'Max contacts per day', badge: '45%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '100%', percent: 45, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '71.5%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'confidence', icon: ShieldCheck, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Confidence Threshold', description: 'Minimum confidence required', badge: '95%', badgeBg: 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300', minLabel: '80%', maxLabel: '100%', percent: 75, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '96.8%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'window', icon: Clock, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Recovery Window', description: 'Allowed time window for action', badge: 'Within Window', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0h', maxLabel: '72h', percent: 40, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '94.1%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'uplift', icon: Zap, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Uplift Threshold', description: 'Minimum uplift vs no action', badge: '+5%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '25%', percent: 30, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '91.2%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'card-fatigue', icon: CreditCard, iconColor: 'text-indigo-400', iconBg: 'bg-indigo-950/70 border-indigo-500/40', name: 'Card Fatigue Cool-off', description: 'Minimum gap between recurring card retries', badge: '24h / 48h', badgeBg: 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300', minLabel: '0h', maxLabel: '48h', percent: 50, segments: [{ width: '80%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }], status: '96.2%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'settlement-cap', icon: Activity, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Max Automated Settlement Cap', description: 'Autonomous execution transaction ceiling', badge: '₹50K / ₹1L', badgeBg: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300', minLabel: '₹0', maxLabel: '₹1L', percent: 50, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '100%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
    ],
    fairnessSegments: [
      { name: 'New vs Existing', cases: '16,924', uplift: '+22.4%', gap: '2.1pp', status: 'Fair' },
      { name: 'High vs Low Value', cases: '15,928', uplift: '+21.8%', gap: '1.6pp', status: 'Fair' },
      { name: 'Region (Tier 1 vs 2/3)', cases: '20,416', uplift: '+20.9%', gap: '2.4pp', status: 'Fair' },
      { name: 'Issuer (Top vs Others)', cases: '24,844', uplift: '+20.1%', gap: '1.9pp', status: 'Fair' },
    ],
    modelFairness: {
      disparateImpact: '0.93',
      equalOpportunity: '0.92',
      calibrationGap: '1.6%',
      overall: 'Fair',
    },
  },
  'This Quarter': {
    label: 'This Quarter',
    policyChecks: '154,104',
    policyChecksDelta: '↗ 24.1% vs last quarter',
    policyChecksBars: [45, 60, 70, 55, 85, 68, 80, 92, 70, 95, 82, 90, 98, 75, 88, 92, 96, 100],
    actionsBlocked: '2,568',
    actionsBlockedDelta: '↘ 18.2% vs last quarter',
    actionsBlockedBars: [65, 55, 60, 75, 58, 70, 48, 62, 45, 52, 40, 35, 32, 28, 24, 18, 15, 10],
    violations: '0',
    violationsDelta: 'Great! No violations',
    violationsBars: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    manualReviews: '2,208',
    manualReviewsDelta: '↗ 5.1% vs last quarter',
    manualReviewsBars: [40, 50, 55, 65, 60, 75, 70, 80, 85, 75, 90, 92, 80, 85, 90, 94, 95, 98],
    autonomousActions: '93.8%',
    autonomousActionsDelta: '↗ 4.2pp vs last quarter',
    autonomousActionsBars: [70, 75, 80, 85, 80, 90, 92, 88, 94, 95, 90, 96, 94, 98, 96, 98, 97, 100],
    activeBoundsCount: 8,
    policyControls: [
      { id: 'npci', icon: Layers, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/40', name: 'NPCI Attempt Limit', description: 'Max retry attempts allowed', badge: '3 / 4', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '4', percent: 75, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '98.8%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'trai', icon: PhoneCall, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/40', name: 'Contact Budget (TRAI)', description: 'Max contacts per customer', badge: '3 / 5', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '5', percent: 60, segments: [{ width: '60%', color: 'bg-emerald-500' }, { width: '25%', color: 'bg-amber-500' }, { width: '15%', color: 'bg-rose-500' }], status: '90.5%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'merchant', icon: TrendingUp, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/40', name: 'Merchant Daily Limit', description: 'Max contacts per day', badge: '48%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '100%', percent: 48, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '74.2%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'confidence', icon: ShieldCheck, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Confidence Threshold', description: 'Minimum confidence required', badge: '95%', badgeBg: 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300', minLabel: '80%', maxLabel: '100%', percent: 75, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '97.2%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'window', icon: Clock, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Recovery Window', description: 'Allowed time window for action', badge: 'Within Window', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0h', maxLabel: '72h', percent: 40, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '94.8%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'uplift', icon: Zap, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Uplift Threshold', description: 'Minimum uplift vs no action', badge: '+5%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '25%', percent: 30, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '92.1%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'card-fatigue', icon: CreditCard, iconColor: 'text-indigo-400', iconBg: 'bg-indigo-950/70 border-indigo-500/40', name: 'Card Fatigue Cool-off', description: 'Minimum gap between recurring card retries', badge: '24h / 48h', badgeBg: 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300', minLabel: '0h', maxLabel: '48h', percent: 50, segments: [{ width: '80%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }], status: '97.0%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'settlement-cap', icon: Activity, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Max Automated Settlement Cap', description: 'Autonomous execution transaction ceiling', badge: '₹50K / ₹1L', badgeBg: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300', minLabel: '₹0', maxLabel: '₹1L', percent: 50, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '100%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
    ],
    fairnessSegments: [
      { name: 'New vs Existing', cases: '50,772', uplift: '+22.8%', gap: '1.9pp', status: 'Fair' },
      { name: 'High vs Low Value', cases: '47,784', uplift: '+22.1%', gap: '1.5pp', status: 'Fair' },
      { name: 'Region (Tier 1 vs 2/3)', cases: '61,248', uplift: '+21.3%', gap: '2.2pp', status: 'Fair' },
      { name: 'Issuer (Top vs Others)', cases: '74,532', uplift: '+20.5%', gap: '1.7pp', status: 'Fair' },
    ],
    modelFairness: {
      disparateImpact: '0.94',
      equalOpportunity: '0.93',
      calibrationGap: '1.4%',
      overall: 'Fair',
    },
  },
  'Year to Date': {
    label: 'Year to Date',
    policyChecks: '616,416',
    policyChecksDelta: '↗ 26.5% vs 2024',
    policyChecksBars: [50, 65, 75, 60, 90, 72, 85, 96, 75, 98, 88, 95, 100, 80, 92, 95, 98, 100],
    actionsBlocked: '10,272',
    actionsBlockedDelta: '↘ 16.5% vs 2024',
    actionsBlockedBars: [60, 50, 55, 70, 52, 65, 42, 55, 38, 45, 35, 30, 26, 22, 18, 14, 10, 8],
    violations: '0',
    violationsDelta: 'Great! No violations',
    violationsBars: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    manualReviews: '8,832',
    manualReviewsDelta: '↗ 4.2% vs 2024',
    manualReviewsBars: [45, 55, 60, 70, 65, 80, 75, 85, 90, 80, 94, 95, 85, 90, 94, 96, 98, 100],
    autonomousActions: '94.2%',
    autonomousActionsDelta: '↗ 3.8pp vs 2024',
    autonomousActionsBars: [75, 80, 85, 90, 85, 94, 96, 92, 96, 98, 94, 98, 96, 100, 98, 100, 99, 100],
    activeBoundsCount: 8,
    policyControls: [
      { id: 'npci', icon: Layers, iconColor: 'text-purple-400', iconBg: 'bg-purple-950/70 border-purple-500/40', name: 'NPCI Attempt Limit', description: 'Max retry attempts allowed', badge: '3 / 4', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '4', percent: 75, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '99.1%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'trai', icon: PhoneCall, iconColor: 'text-blue-400', iconBg: 'bg-blue-950/70 border-blue-500/40', name: 'Contact Budget (TRAI)', description: 'Max contacts per customer', badge: '3 / 5', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0', maxLabel: '5', percent: 60, segments: [{ width: '60%', color: 'bg-emerald-500' }, { width: '25%', color: 'bg-amber-500' }, { width: '15%', color: 'bg-rose-500' }], status: '91.8%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'merchant', icon: TrendingUp, iconColor: 'text-cyan-400', iconBg: 'bg-cyan-950/70 border-cyan-500/40', name: 'Merchant Daily Limit', description: 'Max contacts per day', badge: '50%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '100%', percent: 50, segments: [{ width: '70%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }, { width: '10%', color: 'bg-rose-500' }], status: '76.8%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'confidence', icon: ShieldCheck, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Confidence Threshold', description: 'Minimum confidence required', badge: '95%', badgeBg: 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300', minLabel: '80%', maxLabel: '100%', percent: 75, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '97.8%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'window', icon: Clock, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Recovery Window', description: 'Allowed time window for action', badge: 'Within Window', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0h', maxLabel: '72h', percent: 40, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '95.4%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'uplift', icon: Zap, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Uplift Threshold', description: 'Minimum uplift vs no action', badge: '+5%', badgeBg: 'bg-amber-500/20 border-amber-500/40 text-amber-300', minLabel: '0%', maxLabel: '25%', percent: 30, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '93.0%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
      { id: 'card-fatigue', icon: CreditCard, iconColor: 'text-indigo-400', iconBg: 'bg-indigo-950/70 border-indigo-500/40', name: 'Card Fatigue Cool-off', description: 'Minimum gap between recurring card retries', badge: '24h / 48h', badgeBg: 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300', minLabel: '0h', maxLabel: '48h', percent: 50, segments: [{ width: '80%', color: 'bg-emerald-500' }, { width: '20%', color: 'bg-amber-500' }], status: '97.8%', compliance: 'Within Limit', complianceColor: 'text-emerald-400' },
      { id: 'settlement-cap', icon: Activity, iconColor: 'text-emerald-400', iconBg: 'bg-emerald-950/70 border-emerald-500/40', name: 'Max Automated Settlement Cap', description: 'Autonomous execution transaction ceiling', badge: '₹50K / ₹1L', badgeBg: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300', minLabel: '₹0', maxLabel: '₹1L', percent: 50, segments: [{ width: '100%', color: 'bg-emerald-500' }], status: '100%', compliance: 'Healthy', complianceColor: 'text-emerald-400' },
    ],
    fairnessSegments: [
      { name: 'New vs Existing', cases: '203,088', uplift: '+23.1%', gap: '1.8pp', status: 'Fair' },
      { name: 'High vs Low Value', cases: '191,136', uplift: '+22.5%', gap: '1.4pp', status: 'Fair' },
      { name: 'Region (Tier 1 vs 2/3)', cases: '244,992', uplift: '+21.6%', gap: '2.0pp', status: 'Fair' },
      { name: 'Issuer (Top vs Others)', cases: '298,128', uplift: '+20.8%', gap: '1.5pp', status: 'Fair' },
    ],
    modelFairness: {
      disparateImpact: '0.95',
      equalOpportunity: '0.94',
      calibrationGap: '1.2%',
      overall: 'Fair',
    },
  },
};

// Case Audit Trail Datasets
const auditCasesData: Record<AuditCaseKey, {
  label: string;
  subtitle: string;
  timeline: {
    num: number;
    time: string;
    numColor: string;
    title: string;
    desc: string;
    badge: string;
    badgeClass: string;
  }[];
}> = {
  'RX-48291': {
    label: 'RX-48291 (UPI Autodebit ₹8,999)',
    subtitle: 'Track key decisions and actions for Customer #4821',
    timeline: [
      { num: 1, time: '10:32:14', numColor: 'bg-purple-900/80 text-purple-300 border-purple-500/50', title: 'Payment failed', desc: 'Payment of ₹8,999 failed for Customer #4821', badge: 'DETECTED', badgeClass: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
      { num: 2, time: '10:32:15', numColor: 'bg-blue-900/80 text-blue-300 border-blue-500/50', title: 'Root cause classified', desc: 'Insufficient funds detected (Issuer: HDFC)', badge: 'CLASSIFIED', badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
      { num: 3, time: '10:32:16', numColor: 'bg-pink-900/80 text-pink-300 border-pink-500/50', title: 'Causal decision generated', desc: 'Uplift model evaluated 5 interventions (Expected: +27.4%)', badge: 'DECIDED', badgeClass: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
      { num: 4, time: '10:32:16', numColor: 'bg-emerald-900/80 text-emerald-300 border-emerald-500/50', title: 'Policy validated', desc: 'All 8 policy checks passed within NPCI / TRAI caps', badge: 'VALIDATED', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
      { num: 5, time: '10:32:17', numColor: 'bg-cyan-900/80 text-cyan-300 border-cyan-500/50', title: 'WhatsApp action executed', desc: 'Personalized payment reminder link sent via WhatsApp', badge: 'EXECUTED', badgeClass: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' },
      { num: 6, time: '11:47:03', numColor: 'bg-emerald-900/80 text-emerald-300 border-emerald-500/50', title: 'Payment recovered', desc: 'Full amount ₹8,999 recovered successfully via UPI Intent', badge: 'RECOVERED', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
    ],
  },
  'RX-91823': {
    label: 'RX-91823 (SaaS Renewal ₹14,500)',
    subtitle: 'Track key decisions and actions for Customer #1092',
    timeline: [
      { num: 1, time: '09:14:02', numColor: 'bg-purple-900/80 text-purple-300 border-purple-500/50', title: 'Card Mandate failed', desc: 'Annual SaaS subscription billing failed for Customer #1092', badge: 'DETECTED', badgeClass: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
      { num: 2, time: '09:14:03', numColor: 'bg-blue-900/80 text-blue-300 border-blue-500/50', title: 'Root cause classified', desc: 'Issuer gateway timeout on ICICI Corporate Card', badge: 'CLASSIFIED', badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
      { num: 3, time: '09:14:04', numColor: 'bg-pink-900/80 text-pink-300 border-pink-500/50', title: 'Optimal retry window selected', desc: 'Hazard model predicts 91.2% success at 14:00 IST', badge: 'DECIDED', badgeClass: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
      { num: 4, time: '14:00:12', numColor: 'bg-cyan-900/80 text-cyan-300 border-cyan-500/50', title: 'Smart Retry dispatched', desc: 'Automated background gateway retry triggered with zero user friction', badge: 'EXECUTED', badgeClass: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' },
      { num: 5, time: '14:00:15', numColor: 'bg-emerald-900/80 text-emerald-300 border-emerald-500/50', title: 'Payment recovered', desc: '₹14,500 settled successfully without customer churn', badge: 'RECOVERED', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
    ],
  },
  'RX-34901': {
    label: 'RX-34901 (B2B Invoice ₹45,000)',
    subtitle: 'Track key decisions and actions for Customer #3044',
    timeline: [
      { num: 1, time: '14:20:10', numColor: 'bg-purple-900/80 text-purple-300 border-purple-500/50', title: 'Invoice payment failed', desc: 'B2B receivable ₹45,000 failed for TechCorp India', badge: 'DETECTED', badgeClass: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
      { num: 2, time: '14:20:12', numColor: 'bg-blue-900/80 text-blue-300 border-blue-500/50', title: 'Root cause classified', desc: 'Daily netbanking limit reached on Axis Bank account', badge: 'CLASSIFIED', badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
      { num: 3, time: '14:20:15', numColor: 'bg-pink-900/80 text-pink-300 border-pink-500/50', title: 'Causal decision generated', desc: 'AI agent suggested multi-channel incentive link + direct voice outreach', badge: 'DECIDED', badgeClass: 'bg-pink-500/20 text-pink-300 border-pink-500/40' },
      { num: 4, time: '15:10:00', numColor: 'bg-cyan-900/80 text-cyan-300 border-cyan-500/50', title: 'Voice Call outreach executed', desc: 'Interactive AI voice reminder confirmed invoice rescheduling for tomorrow', badge: 'EXECUTED', badgeClass: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' },
      { num: 5, time: '15:12:30', numColor: 'bg-amber-900/80 text-amber-300 border-amber-500/50', title: 'Promise-to-Pay recorded', desc: 'Customer scheduled payment for 29th Aug 10:00 AM IST', badge: 'PROMISE-TO-PAY', badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
    ],
  },
  'RX-78214': {
    label: 'RX-78214 (Checkout ₹3,250 - Auto-Blocked)',
    subtitle: 'Track key decisions and actions for Customer #8911',
    timeline: [
      { num: 1, time: '16:05:22', numColor: 'bg-purple-900/80 text-purple-300 border-purple-500/50', title: 'Payment failed', desc: 'Checkout payment of ₹3,250 failed for Customer #8911', badge: 'DETECTED', badgeClass: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
      { num: 2, time: '16:05:23', numColor: 'bg-blue-900/80 text-blue-300 border-blue-500/50', title: 'Root cause classified', desc: 'Excessive rapid retry attempts detected across merchant nodes', badge: 'CLASSIFIED', badgeClass: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
      { num: 3, time: '16:05:24', numColor: 'bg-rose-900/80 text-rose-300 border-rose-500/50', title: 'Policy check triggered', desc: 'NPCI attempt bound (3/3 exceeded) triggered automated block', badge: 'BLOCKED', badgeClass: 'bg-rose-500/20 text-rose-300 border-rose-500/40' },
      { num: 4, time: '16:05:25', numColor: 'bg-amber-900/80 text-amber-300 border-amber-500/50', title: 'Cool-off window enforced', desc: 'Customer placed in 24h fatigue cooldown to prevent issuer penalty', badge: 'COOLDOWN', badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
    ],
  },
};

export const GovernancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'controls' | 'audit' | 'fairness' | 'confidence' | 'security'>('controls');
  const [selectedAuditCase, setSelectedAuditCase] = useState<AuditCaseKey>('RX-48291');
  const [selectedTimeline, setSelectedTimeline] = useState<GovernanceTimeline>('This Week');

  // Dropdown visibility state
  const [isCaseMenuOpen, setIsCaseMenuOpen] = useState(false);
  const [isTimelineMenuOpen, setIsTimelineMenuOpen] = useState(false);

  // Global store sync
  const globalDateRange = useDemoStore((state) => state.selectedDateRange);
  const setSelectedDateRange = useDemoStore((state) => state.setSelectedDateRange);
  const auditTrail = useDemoStore((state) => state.auditTrail);
  const engineState = useDemoStore((state) => state.engineState);
  const updatePolicyRule = useDemoStore((state) => state.updatePolicyRule);
  const policyCounts = useDemoStore((state) => state.policyCounts);
  const { data: govData } = useGovernance();

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

  const handleTimelineSelect = (t: GovernanceTimeline) => {
    setSelectedTimeline(t);
    setIsTimelineMenuOpen(false);

    // Sync back to global store
    if (t === 'This Week') setSelectedDateRange('Aug 22 – Aug 28, 2026');
    if (t === 'This Month') setSelectedDateRange('Aug 1 – Aug 28, 2026');
    if (t === 'This Quarter') setSelectedDateRange('Jun 1 – Aug 28, 2026');
    if (t === 'Year to Date') setSelectedDateRange('Jan 1 – Aug 28, 2026');
  };

  const currentDataset = governanceDataByTimeline[selectedTimeline] || governanceDataByTimeline['This Week'];
  const currentAuditCase = auditCasesData[selectedAuditCase] || auditCasesData['RX-48291'];

  const timelineOptions: GovernanceTimeline[] = ['This Week', 'This Month', 'This Quarter', 'Year to Date'];
  const caseOptions: AuditCaseKey[] = ['RX-48291', 'RX-91823', 'RX-34901', 'RX-78214'];
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  // Top 5 KPI Cards Data
  const kpiCards: TopKpiProps[] = [
    {
      icon: ShieldCheck,
      iconBg: isLight ? 'bg-blue-50' : 'bg-blue-950/80',
      iconBorder: isLight ? 'border-blue-200' : 'border-blue-500/40',
      iconColor: isLight ? 'text-blue-600' : 'text-blue-400',
      title: 'POLICY CHECKS',
      value: currentDataset.policyChecks,
      valueColor: isLight ? 'text-slate-900 font-black' : 'text-white',
      trend: currentDataset.policyChecksDelta,
      trendType: 'info',
      cardBg: isLight ? 'bg-white' : 'bg-gradient-to-b from-[#0C1A2B]/95 to-[#07101C]/95',
      cardBorder: isLight ? 'border-slate-200 shadow-sm' : 'border-blue-500/20 shadow-xl',
      bars: currentDataset.policyChecksBars,
      barColor: isLight ? 'bg-blue-500' : 'bg-blue-400',
    },
    {
      icon: ShieldAlert,
      iconBg: isLight ? 'bg-amber-50' : 'bg-amber-950/80',
      iconBorder: isLight ? 'border-amber-200' : 'border-amber-500/40',
      iconColor: isLight ? 'text-amber-600' : 'text-amber-400',
      title: 'ACTIONS BLOCKED',
      value: currentDataset.actionsBlocked,
      valueColor: isLight ? 'text-amber-700 font-black' : 'text-amber-400',
      trend: currentDataset.actionsBlockedDelta,
      trendType: 'warning',
      cardBg: isLight ? 'bg-white' : 'bg-gradient-to-b from-[#241A0B]/95 to-[#130E06]/95',
      cardBorder: isLight ? 'border-slate-200 shadow-sm' : 'border-amber-500/20 shadow-xl',
      bars: currentDataset.actionsBlockedBars,
      barColor: isLight ? 'bg-amber-500' : 'bg-amber-400',
    },
    {
      icon: ShieldCheck,
      iconBg: isLight ? 'bg-emerald-50' : 'bg-emerald-950/80',
      iconBorder: isLight ? 'border-emerald-200' : 'border-emerald-500/40',
      iconColor: isLight ? 'text-emerald-600' : 'text-emerald-400',
      title: 'POLICY VIOLATIONS',
      value: currentDataset.violations,
      valueColor: isLight ? 'text-emerald-700 font-black' : 'text-emerald-400',
      trend: currentDataset.violationsDelta,
      trendType: 'positive',
      cardBg: isLight ? 'bg-white' : 'bg-gradient-to-b from-[#0C1E18]/95 to-[#081310]/95',
      cardBorder: isLight ? 'border-slate-200 shadow-sm' : 'border-emerald-500/20 shadow-xl',
      bars: currentDataset.violationsBars,
      barColor: isLight ? 'bg-emerald-500' : 'bg-emerald-400',
    },
    {
      icon: UserCheck,
      iconBg: isLight ? 'bg-cyan-50' : 'bg-cyan-950/80',
      iconBorder: isLight ? 'border-cyan-200' : 'border-cyan-500/40',
      iconColor: isLight ? 'text-cyan-600' : 'text-cyan-400',
      title: 'MANUAL REVIEWS',
      value: currentDataset.manualReviews,
      valueColor: isLight ? 'text-cyan-700 font-black' : 'text-cyan-400',
      trend: currentDataset.manualReviewsDelta,
      trendType: 'info',
      cardBg: isLight ? 'bg-white' : 'bg-gradient-to-b from-[#0C1A2B]/95 to-[#07101C]/95',
      cardBorder: isLight ? 'border-slate-200 shadow-sm' : 'border-cyan-500/20 shadow-xl',
      bars: currentDataset.manualReviewsBars,
      barColor: isLight ? 'bg-cyan-500' : 'bg-cyan-400',
    },
    {
      icon: Bot,
      iconBg: isLight ? 'bg-purple-50' : 'bg-purple-950/80',
      iconBorder: isLight ? 'border-purple-200' : 'border-purple-500/40',
      iconColor: isLight ? 'text-purple-600' : 'text-purple-400',
      title: 'AUTONOMOUS ACTIONS',
      value: currentDataset.autonomousActions,
      valueColor: isLight ? 'text-purple-700 font-black' : 'text-purple-300',
      trend: currentDataset.autonomousActionsDelta,
      trendType: 'purple',
      cardBg: isLight ? 'bg-white' : 'bg-gradient-to-b from-[#140F28]/95 to-[#0B0918]/95',
      cardBorder: isLight ? 'border-slate-200 shadow-sm' : 'border-purple-500/20 shadow-xl',
      bars: currentDataset.autonomousActionsBars,
      barColor: isLight ? 'bg-purple-500' : 'bg-purple-400',
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.35 }}
      className="space-y-4 max-w-[1600px] mx-auto pb-8"
    >
      <Topbar
        title="Governance"
        subtitle="Ensure every recovery action is safe, fair, and compliant."
      />

      {/* Governance Tabs with Purple Underline */}
      <div className={cn("flex items-center gap-6 border-b pb-2 text-xs font-semibold overflow-x-auto", isLight ? "border-slate-200" : "border-slate-800")}>
        {[
          { id: 'controls', label: 'Policy Controls' },
          { id: 'audit', label: 'Audit Trail' },
          { id: 'fairness', label: 'Fairness' },
          { id: 'confidence', label: 'Model Confidence' },
          { id: 'security', label: 'Security' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id as any)}
            className={cn(
              "pb-1 transition-colors cursor-pointer relative",
              activeTab === t.id
                ? (isLight ? "text-purple-700 font-bold" : "text-purple-300 font-bold")
                : (isLight ? "text-slate-500 hover:text-slate-900" : "text-slate-400 hover:text-slate-200")
            )}
          >
            <span>{t.label}</span>
            {activeTab === t.id && (
              <motion.div
                layoutId="govTabUnderline"
                className="absolute -bottom-2 left-0 right-0 h-[2px] bg-purple-500 shadow-sm shadow-purple-500/50"
              />
            )}
          </button>
        ))}
      </div>

      {/* Top 5 KPI Cards - Dynamic with Timeline Selection */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        {kpiCards.map((kpi, idx) => {
          const IconComp = kpi.icon;
          return (
            <motion.div
              key={kpi.title}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: idx * 0.04 }}
              className={cn(
                "p-3.5 sm:p-4 rounded-2xl border relative overflow-hidden flex flex-col justify-between transition-colors",
                kpi.cardBg,
                kpi.cardBorder
              )}
            >
              <div>
                <div className="flex items-center justify-between">
                  <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center border", kpi.iconBg, kpi.iconBorder)}>
                    <IconComp className={cn("w-3.5 h-3.5", kpi.iconColor)} />
                  </div>
                  <span className={cn("text-[9.5px] uppercase font-extrabold tracking-wider truncate", isLight ? "text-slate-500" : "text-slate-400")}>
                    {kpi.title}
                  </span>
                </div>

                <div className="mt-3">
                  <span className={cn("text-2xl sm:text-3xl font-black tabular-nums tracking-tight block", kpi.valueColor)}>
                    {kpi.value}
                  </span>
                  <span className={cn(
                    "text-[10px] font-semibold block mt-0.5",
                    kpi.trendType === 'warning' ? (isLight ? "text-amber-700" : "text-amber-400") :
                      kpi.trendType === 'positive' ? (isLight ? "text-emerald-700" : "text-emerald-400") :
                        kpi.trendType === 'purple' ? (isLight ? "text-purple-700" : "text-purple-400") :
                          (isLight ? "text-blue-700" : "text-cyan-400")
                  )}>
                    {kpi.trend}
                  </span>
                </div>
              </div>

              {/* Sparkline Micro Bars */}
              <div className="mt-2">
                <MicroBarChart bars={kpi.bars} color={kpi.barColor} />
              </div>
            </motion.div>
          );
        })}
      </div>

      {activeTab === 'audit' ? (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <Card className="p-4 sm:p-6 rounded-2xl border border-slate-800 bg-[#0B101D]/95 shadow-2xl backdrop-blur-md space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
              <div>
                <CardTitle className="text-base font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  <span>Verifiable Cryptographic Audit Ledger</span>
                </CardTitle>
                <p className="text-xs text-slate-400 mt-0.5">
                  Tamper-evident SHA-256 block chain recording every Causal AI inference, policy check, human approval, and recovery outcome.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Chain Integrity: 100% VALID</span>
                </span>
                <button
                  onClick={() => setActiveTab('controls')}
                  className="text-xs font-semibold px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
                >
                  Back to Controls
                </button>
              </div>
            </div>

            <div className="overflow-x-auto max-h-[520px] overflow-y-auto pr-1">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold tracking-wider sticky top-0 bg-[#0B101D] z-10">
                    <th className="py-2.5 px-3">RECORD ID</th>
                    <th className="py-2.5 px-3">TIMESTAMP</th>
                    <th className="py-2.5 px-3">CASE ID</th>
                    <th className="py-2.5 px-3">ACTION / EVENT</th>
                    <th className="py-2.5 px-3">ACTOR</th>
                    <th className="py-2.5 px-3 font-mono">SHA-256 HASH</th>
                    <th className="py-2.5 px-3 font-mono">PREVIOUS HASH</th>
                    <th className="py-2.5 px-3 text-right">STATUS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {auditTrail.map((ev, i) => (
                    <tr key={ev.id || i} className="hover:bg-slate-900/50 transition-colors">
                      <td className="py-2.5 px-3 text-indigo-400 font-bold">{ev.id || `AUDIT-${i + 1}`}</td>
                      <td className="py-2.5 px-3 text-slate-400 font-sans">{ev.timestamp}</td>
                      <td className="py-2.5 px-3 text-white font-bold">{ev.caseId}</td>
                      <td className="py-2.5 px-3 text-cyan-300 font-sans font-semibold">{ev.action}</td>
                      <td className="py-2.5 px-3 text-slate-300 font-sans">{ev.actor}</td>
                      <td className="py-2.5 px-3 text-slate-400 truncate max-w-[140px]" title={ev.hash || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}>
                        {ev.hash ? `${ev.hash.slice(0, 14)}...` : 'e3b0c44298fc...'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500 truncate max-w-[140px]" title={ev.prevHash || '0000000000000000000000000000000000000000000000000000000000000000'}>
                        {ev.prevHash ? `${ev.prevHash.slice(0, 14)}...` : '000000000000...'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-sans">
                        <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                          VERIFIED
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </motion.div>
      ) : (
        <>
          {/* Live Interactive Policy Calibration & Routing Impact */}
          <Card className={cn(
            "p-4 sm:p-5 rounded-2xl border shadow-2xl space-y-4 mb-4 transition-colors",
            isLight ? "bg-white border-slate-200 text-slate-900 shadow-sm" : "bg-[#0B101D]/95 border-slate-800 text-white"
          )}>
            <div className={cn("flex flex-wrap items-center justify-between gap-3 border-b pb-3", isLight ? "border-slate-100" : "border-slate-800")}>
              <div>
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-purple-400" />
                  <span>Live Policy Bounds Engine & Real-Time Human Routing</span>
                </CardTitle>
                <p className={cn("text-[11px] mt-0.5", isLight ? "text-slate-500" : "text-slate-400")}>
                  Adjust thresholds to re-evaluate the full portfolio of 350 transactions through the Causal Policy Engine in real time.
                </p>
              </div>

              {/* Live Portfolio Impact Counters */}
              <div className="flex items-center gap-3">
                <div className={cn("px-3 py-1 rounded-xl border text-center", isLight ? "bg-emerald-50 border-emerald-200" : "bg-emerald-950/40 border-emerald-500/40")}>
                  <span className="text-[9px] uppercase font-bold text-emerald-400 block">PASS (Autonomous)</span>
                  <span className={cn("text-sm font-black tabular-nums", isLight ? "text-emerald-800" : "text-emerald-300")}>{policyCounts.pass}</span>
                </div>
                <div className={cn("px-3 py-1 rounded-xl border text-center", isLight ? "bg-amber-50 border-amber-200" : "bg-amber-950/40 border-amber-500/40")}>
                  <span className="text-[9px] uppercase font-bold text-amber-400 block">HUMAN REVIEW</span>
                  <span className={cn("text-sm font-black tabular-nums", isLight ? "text-amber-800" : "text-amber-300")}>{policyCounts.review}</span>
                </div>
                <div className={cn("px-3 py-1 rounded-xl border text-center", isLight ? "bg-rose-50 border-rose-200" : "bg-rose-950/40 border-rose-500/40")}>
                  <span className="text-[9px] uppercase font-bold text-rose-400 block">BLOCKED</span>
                  <span className={cn("text-sm font-black tabular-nums", isLight ? "text-rose-800" : "text-rose-300")}>{policyCounts.block}</span>
                </div>
              </div>
            </div>

            {/* 4 Interactive Sliders */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
              {/* Slider 1: Confidence Threshold */}
              <div className={cn("p-3 rounded-xl border space-y-2", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                <div className="flex justify-between items-center text-xs">
                  <span className={cn("font-bold", isLight ? "text-slate-800" : "text-slate-200")}>Min Confidence</span>
                  <span className="font-mono font-black text-purple-400 tabular-nums">
                    {Math.round(engineState.policyRules.confidenceThreshold * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="70"
                  max="95"
                  step="1"
                  value={Math.round(engineState.policyRules.confidenceThreshold * 100)}
                  onChange={(e) => updatePolicyRule('confidenceThreshold', Number(e.target.value) / 100)}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                />
                <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                  <span>70% (Aggressive)</span>
                  <span>95% (Strict)</span>
                </div>
              </div>

              {/* Slider 2: TRAI Contact Budget */}
              <div className={cn("p-3 rounded-xl border space-y-2", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                <div className="flex justify-between items-center text-xs">
                  <span className={cn("font-bold", isLight ? "text-slate-800" : "text-slate-200")}>TRAI Contact Cap</span>
                  <span className="font-mono font-black text-blue-400 tabular-nums">
                    {engineState.policyRules.maxContactsPerCustomer} contacts
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="5"
                  step="1"
                  value={engineState.policyRules.maxContactsPerCustomer}
                  onChange={(e) => updatePolicyRule('maxContactsPerCustomer', Number(e.target.value))}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                  <span>1 (Strict)</span>
                  <span>5 (Max)</span>
                </div>
              </div>

              {/* Slider 3: NPCI Retries */}
              <div className={cn("p-3 rounded-xl border space-y-2", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                <div className="flex justify-between items-center text-xs">
                  <span className={cn("font-bold", isLight ? "text-slate-800" : "text-slate-200")}>NPCI Retries Limit</span>
                  <span className="font-mono font-black text-emerald-400 tabular-nums">
                    {engineState.policyRules.maxRetries} retries
                  </span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="5"
                  step="1"
                  value={engineState.policyRules.maxRetries}
                  onChange={(e) => updatePolicyRule('maxRetries', Number(e.target.value))}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                  <span>1 (Low)</span>
                  <span>5 (High)</span>
                </div>
              </div>

              {/* Slider 4: High Value Escalation */}
              <div className={cn("p-3 rounded-xl border space-y-2", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                <div className="flex justify-between items-center text-xs">
                  <span className={cn("font-bold", isLight ? "text-slate-800" : "text-slate-200")}>High-Value Floor</span>
                  <span className="font-mono font-black text-amber-400 tabular-nums">
                    {formatINR(engineState.policyRules.highValueThreshold)}
                  </span>
                </div>
                <input
                  type="range"
                  min="5000"
                  max="25000"
                  step="1000"
                  value={engineState.policyRules.highValueThreshold}
                  onChange={(e) => updatePolicyRule('highValueThreshold', Number(e.target.value))}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <div className="flex justify-between text-[9px] text-slate-500 font-mono">
                  <span>₹5,000</span>
                  <span>₹25,000</span>
                </div>
              </div>
            </div>
          </Card>

          {/* Row 2: Policy Controls Overview (8 cols) & Policy Health (4 cols) - Balanced Compact Height */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
            {/* Policy Controls Overview Matrix with Scrollable Container (8 cols) */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="lg:col-span-8 flex flex-col"
            >
              <Card className="p-3.5 sm:p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-2.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-1.5">
                      <span>Policy Controls Overview</span>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                            <p>Real-time deterministic guardrails enforced before each recovery intervention</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </CardTitle>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {currentDataset.policyControls.length} Active Hard Bounds • {selectedTimeline}
                    </span>
                  </div>

                  {/* Scrollable Table Viewport with Zero-Overlap Segmented Bars */}
                  <div className="max-h-[220px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900/40 pt-1">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-[9px] text-slate-400 uppercase font-bold tracking-wider sticky top-0 bg-[#0B101D] z-20">
                          <th className="py-1.5 px-2">CONTROL</th>
                          <th className="py-1.5 px-2">DESCRIPTION</th>
                          <th className="py-1.5 px-2 text-center">STATUS</th>
                          <th className="py-1.5 px-2 text-right">COMPLIANCE</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {currentDataset.policyControls.map((row) => {
                          const IconComponent = row.icon;
                          return (
                            <tr key={row.id} className="hover:bg-slate-900/50 transition-colors group">
                              {/* Control */}
                              <td className="py-2 px-2">
                                <div className="flex items-center gap-2">
                                  <div className={cn("w-5 h-5 rounded-full border flex items-center justify-center shrink-0", row.iconBg, row.iconColor)}>
                                    <IconComponent className="w-2.5 h-2.5" />
                                  </div>
                                  <span className="font-semibold text-white text-[10.5px] group-hover:text-purple-300 transition-colors">
                                    {row.name}
                                  </span>
                                </div>
                              </td>

                              {/* Description & Non-Overlapping Segmented Progress Bar */}
                              <td className="py-2 px-2 min-w-[210px]">
                                <div className="space-y-0.5">
                                  <span className="text-[9.5px] text-slate-400 block leading-tight">
                                    {row.description}
                                  </span>
                                  {/* Segmented Bar with Cleanly Positioned Floating Badge Above Bar */}
                                  <div className="relative pt-4 pb-0.5">
                                    {/* Floating Badge positioned cleanly ABOVE the bar */}
                                    <div
                                      className={cn(
                                        "absolute top-0 px-1 py-0.2 rounded text-[8px] font-bold border transform -translate-x-1/2 whitespace-nowrap shadow-sm z-10",
                                        row.badgeBg
                                      )}
                                      style={{ left: `${Math.max(15, Math.min(85, row.percent))}%` }}
                                    >
                                      {row.badge}
                                    </div>
                                    <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden flex shadow-inner">
                                      {row.segments.map((seg, i) => (
                                        <div key={i} className={cn("h-full", seg.color)} style={{ width: seg.width }} />
                                      ))}
                                    </div>
                                    <div className="flex justify-between text-[8px] text-slate-500 font-mono mt-0.5 leading-none">
                                      <span>{row.minLabel}</span>
                                      <span>{row.maxLabel}</span>
                                    </div>
                                  </div>
                                </div>
                              </td>

                              {/* Status */}
                              <td className="py-2 px-2 text-center font-bold text-white tabular-nums text-xs">
                                {row.status}
                              </td>

                              {/* Compliance */}
                              <td className="py-2 px-2 text-right font-bold text-[10.5px] tabular-nums">
                                <span className={row.complianceColor}>{row.compliance}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Bottom Legend */}
                <div className="flex items-center gap-4 text-[9.5px] text-slate-400 pt-1.5 border-t border-slate-800/80">
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Compliant
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Near Limit
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-400" /> Limit Exceeded
                  </span>
                </div>
              </Card>
            </motion.div>

            {/* Policy Health Card (4 cols) - Compacted Proportions with Zero Dead Space */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.05 }}
              className="lg:col-span-4 flex flex-col"
            >
              <Card className="p-3.5 sm:p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-2.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-1.5">
                      <span>Policy Health</span>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                            <p>Aggregate compliance score across all bounded runtime guardrails</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </CardTitle>
                    <span className="text-[9.5px] font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-1.5 py-0.2 rounded">
                      100% Compliant
                    </span>
                  </div>

                  {/* Glowing Neon Circular Gauge & Checkmarks */}
                  <div className="py-2 flex items-center justify-around gap-2">
                    {/* Neon Green Ring Gauge */}
                    <div className="relative w-24 h-24 flex items-center justify-center shrink-0">
                      <svg viewBox="0 0 100 100" className="w-full h-full transform -rotate-90">
                        <circle
                          cx="50"
                          cy="50"
                          r="40"
                          stroke="#0F291E"
                          strokeWidth="8"
                          fill="none"
                        />
                        <circle
                          cx="50"
                          cy="50"
                          r="40"
                          stroke="#22C55E"
                          strokeWidth="8"
                          strokeDasharray="251.2"
                          strokeDashoffset="0"
                          strokeLinecap="round"
                          fill="none"
                          className="drop-shadow-[0_0_8px_rgba(34,197,94,0.6)]"
                        />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <span className="text-lg font-black text-white leading-tight">100%</span>
                        <span className="text-[9px] font-bold text-emerald-400 leading-none">Healthy</span>
                      </div>
                    </div>

                    {/* 4 Checkmarks */}
                    <ul className="space-y-1 text-xs flex-1">
                      <li className="flex items-center gap-1.5 text-emerald-400 text-[10.5px] font-medium">
                        <CheckCircle2 className="w-3 h-3 shrink-0 fill-emerald-400/20" />
                        <span>All policies active</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-emerald-400 text-[10.5px] font-medium">
                        <CheckCircle2 className="w-3 h-3 shrink-0 fill-emerald-400/20" />
                        <span>No breaches detected</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-emerald-400 text-[10.5px] font-medium">
                        <CheckCircle2 className="w-3 h-3 shrink-0 fill-emerald-400/20" />
                        <span>Recovery actions bounded</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-emerald-400 text-[10.5px] font-medium">
                        <CheckCircle2 className="w-3 h-3 shrink-0 fill-emerald-400/20" />
                        <span>System operating safely</span>
                      </li>
                    </ul>
                  </div>

                  {/* Policy Coverage Progress Bars */}
                  <div className="space-y-2 pt-2 border-t border-slate-800 text-xs">
                    <div className="text-[10.5px] font-bold text-white">Policy Coverage</div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[9.5px] text-slate-300">
                        <span>Recovery Cases Covered</span>
                        <span className="font-bold text-white">100%</span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 w-full rounded-full shadow-sm shadow-purple-500/50" />
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[9.5px] text-slate-300">
                        <span>Actions Bound by Policy</span>
                        <span className="font-bold text-white">100%</span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 w-full rounded-full shadow-sm shadow-purple-500/50" />
                      </div>
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex justify-between text-[9.5px] text-slate-300">
                        <span>Policies Passing Thresholds</span>
                        <span className="font-bold text-emerald-400">5 / 5</span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 w-full rounded-full shadow-sm shadow-purple-500/50" />
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>
          </div>

          {/* Row 3: 3 Columns (Audit Trail, Fairness & Bias Monitor, TEE Enclave) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
            {/* Col 1: Audit Trail with Interactive Dropdown (4 cols) */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="lg:col-span-4 flex flex-col"
            >
              <Card className="p-3.5 sm:p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-2.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <div>
                      <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-1.5">
                        <span>Audit Trail</span>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                            </TooltipTrigger>
                            <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                              <p>Verifiable chronological event log for individual recovery cases</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </CardTitle>
                      <p className="text-[10px] text-slate-400">{currentAuditCase.subtitle}</p>
                    </div>

                    {/* Interactive Case Selector Dropdown */}
                    <div className="relative">
                      <button
                        onClick={() => setIsCaseMenuOpen(!isCaseMenuOpen)}
                        className="flex items-center gap-1 text-[10.5px] font-mono font-bold text-indigo-300 bg-slate-900 border border-slate-800 hover:border-indigo-500/50 px-2 py-0.5 rounded-lg cursor-pointer transition-colors shadow-sm"
                      >
                        <span>{selectedAuditCase}</span>
                        <ChevronDown className={cn("w-3 h-3 text-slate-400 transition-transform", isCaseMenuOpen ? "rotate-180" : "")} />
                      </button>

                      {isCaseMenuOpen && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setIsCaseMenuOpen(false)} />
                          <div className="absolute right-0 mt-1 w-64 bg-[#090E1B] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                            {caseOptions.map((cKey) => {
                              const isSelected = selectedAuditCase === cKey;
                              const caseMeta = auditCasesData[cKey];
                              return (
                                <button
                                  key={cKey}
                                  onClick={() => {
                                    setSelectedAuditCase(cKey);
                                    setIsCaseMenuOpen(false);
                                  }}
                                  className={cn(
                                    "w-full text-left px-3 py-1.5 text-xs flex items-center justify-between transition-colors cursor-pointer",
                                    isSelected
                                      ? "bg-indigo-600/20 text-indigo-300 font-bold border-l-2 border-indigo-500"
                                      : "text-slate-300 hover:bg-slate-800/80 hover:text-white"
                                  )}
                                >
                                  <div className="min-w-0 pr-2">
                                    <span className="font-mono font-bold block">{cKey}</span>
                                    <span className="text-[9.5px] text-slate-400 truncate block">{caseMeta.label}</span>
                                  </div>
                                  {isSelected && <Check className="w-3.5 h-3.5 text-indigo-400 shrink-0" />}
                                </button>
                              );
                            })}
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Dynamic Timeline Nodes matching selected case */}
                  <div className="space-y-2 mt-2">
                    {currentAuditCase.timeline.map((item) => (
                      <div key={item.num} className="flex items-start gap-2 text-xs">
                        <span className="text-[9.5px] text-slate-500 font-mono pt-0.5 w-11 shrink-0">
                          {item.time}
                        </span>
                        <div className={cn("w-4 h-4 rounded-md border flex items-center justify-center font-bold text-[9px] shrink-0 mt-0.5", item.numColor)}>
                          {item.num}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span className="font-semibold text-white text-[10.5px] truncate">{item.title}</span>
                            <span className={cn("px-1.5 py-0.2 rounded text-[8px] font-bold border shrink-0", item.badgeClass)}>
                              {item.badge}
                            </span>
                          </div>
                          <p className="text-[9px] text-slate-400 truncate">{item.desc}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800/80">
                  <button
                    onClick={() => setActiveTab('audit')}
                    className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <span>View full audit logs (Cryptographic SHA-256 Ledger)</span>
                    <span>→</span>
                  </button>
                </div>
              </Card>
            </motion.div>

            {/* Col 2: Fairness & Bias Monitor with Interactive Timeline (4 cols) */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.14 }}
              className="lg:col-span-4 flex flex-col"
            >
              <Card className="p-3.5 sm:p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-2.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                    <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-1.5">
                      <span>Fairness & Bias Monitor</span>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                            <p>Demographic parity and statistical treatment balance checks</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </CardTitle>

                    {/* Interactive Timeline Selector Dropdown */}
                    <div className="relative">
                      <button
                        onClick={() => setIsTimelineMenuOpen(!isTimelineMenuOpen)}
                        className="flex items-center gap-1 text-[10.5px] font-semibold text-slate-300 bg-slate-900 border border-slate-800 hover:border-slate-700 px-2 py-0.5 rounded-lg cursor-pointer transition-colors shadow-sm"
                      >
                        <span>{selectedTimeline}</span>
                        <ChevronDown className={cn("w-3 h-3 text-slate-400 transition-transform", isTimelineMenuOpen ? "rotate-180" : "")} />
                      </button>

                      {isTimelineMenuOpen && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setIsTimelineMenuOpen(false)} />
                          <div className="absolute right-0 mt-1 w-36 bg-[#090E1B] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden py-1">
                            {timelineOptions.map((opt) => {
                              const isSelected = selectedTimeline === opt;
                              return (
                                <button
                                  key={opt}
                                  onClick={() => handleTimelineSelect(opt)}
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
                  </div>

                  {/* Sub-header */}
                  <div className="flex items-center justify-between text-xs pt-0.5">
                    <span className="text-[10px] text-slate-400 font-medium">Uplift parity across key segments</span>
                    <button className="text-[9.5px] text-indigo-400 hover:underline">View details →</button>
                  </div>

                  {/* Dynamic Segment Table */}
                  <div className="overflow-x-auto pt-0.5">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-[8.5px] text-slate-400 uppercase font-bold tracking-wider">
                          <th className="py-1 px-1.5">SEGMENT</th>
                          <th className="py-1 px-1.5">CASES</th>
                          <th className="py-1 px-1.5">AVG UPLIFT</th>
                          <th className="py-1 px-1.5">PARITY GAP</th>
                          <th className="py-1 px-1.5 text-right">STATUS</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {currentDataset.fairnessSegments.map((s) => (
                          <tr key={s.name} className="hover:bg-slate-900/40">
                            <td className="py-1.5 px-1.5 font-medium text-white text-[10px] truncate max-w-[90px]">
                              {s.name}
                            </td>
                            <td className="py-1.5 px-1.5 text-slate-400 tabular-nums text-[10px]">
                              {s.cases}
                            </td>
                            <td className="py-1.5 px-1.5 text-emerald-400 font-bold tabular-nums text-[10px]">
                              {s.uplift}
                            </td>
                            <td className="py-1.5 px-1.5 text-slate-400 tabular-nums text-[10px]">
                              {s.gap}
                            </td>
                            <td className="py-1.5 px-1.5 text-right text-emerald-400 font-bold text-[10px]">
                              {s.status}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Dynamic Model Fairness Summary Metrics */}
                  <div className="pt-2 space-y-1 border-t border-slate-800/80">
                    <span className="text-[9.5px] font-bold text-white block">Model fairness summary</span>
                    <div className="grid grid-cols-4 gap-1 text-center text-[9px]">
                      <div className="p-1 rounded-xl bg-slate-900/90 border border-slate-800">
                        <span className="text-slate-400 block text-[7.5px] leading-tight">Disparate Impact</span>
                        <span className="font-black text-white text-[10.5px] block mt-0.5">{currentDataset.modelFairness.disparateImpact}</span>
                        <span className="text-[7.5px] text-slate-500 block">&gt; 0.80</span>
                      </div>
                      <div className="p-1 rounded-xl bg-slate-900/90 border border-slate-800">
                        <span className="text-slate-400 block text-[7.5px] leading-tight">Equal Opportunity</span>
                        <span className="font-black text-white text-[10.5px] block mt-0.5">{currentDataset.modelFairness.equalOpportunity}</span>
                        <span className="text-[7.5px] text-slate-500 block">&gt; 0.80</span>
                      </div>
                      <div className="p-1 rounded-xl bg-slate-900/90 border border-slate-800">
                        <span className="text-slate-400 block text-[7.5px] leading-tight">Calibration Gap</span>
                        <span className="font-black text-emerald-400 text-[10.5px] block mt-0.5">{currentDataset.modelFairness.calibrationGap}</span>
                        <span className="text-[7.5px] text-slate-500 block">&lt; 5%</span>
                      </div>
                      <div className="p-1 rounded-xl bg-slate-900/90 border border-slate-800">
                        <span className="text-slate-400 block text-[7.5px] leading-tight">Overall</span>
                        <span className="font-black text-emerald-400 text-[10.5px] block mt-0.5">{currentDataset.modelFairness.overall}</span>
                        <span className="text-[7.5px] text-emerald-500 block">No issues</span>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>

            {/* Col 3: Trusted Execution Environment (TEE) (4 cols) */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.18 }}
              className="lg:col-span-4 flex flex-col"
            >
              <Card className="p-3.5 sm:p-4 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-2.5 shadow-2xl backdrop-blur-md h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between pb-1 border-b border-slate-800">
                    <div>
                      <CardTitle className="text-xs sm:text-sm font-bold text-white flex items-center gap-1.5">
                        <span>Trusted Execution Environment (TEE)</span>
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-200 cursor-pointer" />
                            </TooltipTrigger>
                            <TooltipContent className="bg-slate-900 border border-slate-700 text-xs">
                              <p>Hardware-isolated confidential compute simulation ensuring zero data exposure</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </CardTitle>
                      <p className="text-[10px] text-slate-400">Prototype Security Boundary • Simulated Confidential Enclave</p>
                    </div>
                  </div>

                  {/* Glowing Purple Secure Enclave Box */}
                  <div className="mt-2 p-3 rounded-2xl bg-[#140F28]/90 border border-purple-500/50 shadow-lg shadow-purple-950/40 space-y-2">
                    <div className="flex items-center justify-center gap-1.5 text-purple-300 font-bold text-xs tracking-wider">
                      <Lock className="w-3.5 h-3.5 text-purple-400" />
                      <span>SECURE TEE ENCLAVE (SIMULATED)</span>
                    </div>

                    <ul className="space-y-1 text-[10px]">
                      <li className="flex items-center gap-1.5 text-slate-300">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 fill-emerald-400/20 shrink-0" />
                        <span>Decision logic isolated</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-slate-300">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 fill-emerald-400/20 shrink-0" />
                        <span>Customer data encrypted in transit & at rest</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-slate-300">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 fill-emerald-400/20 shrink-0" />
                        <span>No raw PII leaves enclave</span>
                      </li>
                      <li className="flex items-center gap-1.5 text-slate-300">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400 fill-emerald-400/20 shrink-0" />
                        <span>Tamper-evident SHA-256 execution</span>
                      </li>
                    </ul>

                    <div className="text-center text-[9px] text-purple-300/80 font-mono pt-0.5 border-t border-purple-500/20 truncate" title={govData?.teeStatus?.enclave_hash || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}>
                      Enclave Digest: {govData?.teeStatus?.enclave_hash ? `${govData.teeStatus.enclave_hash.slice(0, 18)}...` : 'e3b0c44298fc1c14...'}
                    </div>
                  </div>

                  {/* Safe Output Box */}
                  <div className="mt-2 p-2 rounded-xl bg-[#0B1A30]/80 border border-blue-500/30 text-center space-y-0.5 shadow-sm">
                    <span className="text-[9.5px] font-black text-cyan-300 tracking-wider block uppercase">
                      PROTOTYPE SECURITY BOUNDARY
                    </span>
                    <span className="text-[8.5px] text-slate-400 block">
                      Confidential ML decisioning active • Zero data leakage
                    </span>
                  </div>
                </div>

                {/* Bottom Security Tags */}
                <div className="flex items-center justify-between text-[8.5px] text-slate-400 pt-1.5 border-t border-slate-800/80">
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Data encrypted in transit
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Enclave attested
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Zero data leakage
                  </span>
                </div>
              </Card>
            </motion.div>
          </div>
        </>
      )}

      {/* Footer Note */}
      <div className="p-2 text-center text-[10.5px] text-slate-500 border-t border-slate-800/80">
        ⓘ All metrics are compared against baseline (current manual/legacy process) • Metrics updated daily at 12:00 AM IST
      </div>
    </motion.div>
  );
};
