export * from './mlContracts';

export interface OverviewMetrics {
  revenueAtRisk: number;
  revenueAtRiskDelta: number;
  recoverable: number;
  recoverableDelta: number;
  incrementalRecovery: number;
  incrementalRecoveryDelta: number;
  recovered: number;
  recoveredDelta: number;
  recoveryRate: number;
  recoveryRateDeltaPp: number;
}

export interface RecoveryPulsePoint {
  day: string;
  date: string;
  recovered: number;
  baseline: number;
  incremental: number;
  isPeak?: boolean;
}

export interface DomainRecoveryShare {
  domain: string;
  percentage: number;
  amount: number;
  color: string;
}

export interface FailureReasonItem {
  reason: string;
  percentage: number;
  count: number;
}

export interface FunnelStep {
  step: string;
  count: number;
  percentage: number;
}

export interface OpportunityAction {
  action: string;
  casesCount: number;
  amount: number;
  color: string;
}

export interface PolicyControlRow {
  id: string;
  name: string;
  description: string;
  currentValue: string;
  limitValue: string;
  progressPercent: number;
  status: 'Within Limit' | 'Near Limit' | 'Limit Exceeded' | 'Healthy';
  complianceLevel: 'COMPLIANT' | 'WARNING' | 'BREACH';
}

export interface MerchantSettings {
  merchantName: string;
  merchantId: string;
  businessType: string;
  industry: string;
  website: string;
  registeredEmail: string;
  country: string;
  timezone: string;
  
  // Business Overview
  activeCustomers: number;
  monthlyGMV: number;
  recoveryEnabledPercent: number;
  aov: number;
  successRate: number;
  estIncrementalRecovery: number;
  
  // Engine & Model Settings
  confidenceThreshold: number;
  minUpliftThreshold: number;
  retryAttemptLimit: number;
  contactBudgetPerCustomer: number;
  recoveryWindowHours: [number, number];
  modelVersion: string;
  modelStatus: string;
  
  // Notifications
  alerts: {
    criticalAlerts: boolean;
    recoveryUpdates: boolean;
    dailySummary: boolean;
    policyViolations: boolean;
    systemUpdates: boolean;
  };
  channels: {
    email: boolean;
    sms: boolean;
    inApp: boolean;
  };
}
