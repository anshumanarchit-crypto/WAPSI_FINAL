export type ActionType = 
  | 'NO_ACTION' 
  | 'RETRY' 
  | 'WHATSAPP' 
  | 'VOICE' 
  | 'EMAIL' 
  | 'INCENTIVE';

export type CaseStatus = 
  | 'DETECTED' 
  | 'SCORED' 
  | 'READY' 
  | 'REVIEW' 
  | 'APPROVED' 
  | 'ACTIONED' 
  | 'RECOVERED' 
  | 'FAILED' 
  | 'ESCALATED' 
  | 'MONITORING';

export type DomainType = 
  | 'SUBSCRIPTIONS' 
  | 'CHECKOUT' 
  | 'RECEIVABLES_B2B';

export type DecisionSource = 
  | 'NETWORK' 
  | 'MERCHANT' 
  | 'NETWORK_MERCHANT';

export type RoutingDecision = 
  | 'AUTONOMOUS' 
  | 'HUMAN_REVIEW' 
  | 'BLOCKED';

export interface TransactionFeatures {
  transaction_id: string;
  merchant_id: string;
  customer_id_hash: string;
  customer_name: string;
  customer_handle: string;
  amount: number;
  currency: string;
  payment_method: 'UPI' | 'CARD' | 'NETBANKING' | 'NACH' | 'WALLET';
  issuer: string;
  failure_code: string;
  failure_reason: string;
  attempt_count: number;
  max_attempts: number;
  contacts_made: number;
  max_contacts: number;
  customer_age_days: number;
  previous_transactions: number;
  previous_success_rate: number;
  previous_failed_payments: number;
  days_since_last_success: number;
  hour: number;
  day_of_week: number;
  subscription: boolean;
  merchant_category: string;
  customer_segment: 'PRIME' | 'STANDARD' | 'NEW' | 'AT_RISK';
  historical_recovery_rate: number;
  historical_whatsapp_response: number;
  historical_retry_response: number;
  historical_email_response: number;
  historical_voice_response: number;
  domain: DomainType;
}

export interface RecoveryCase {
  caseId: string;
  customerId: string;
  customerName: string;
  customerHandle: string;
  merchantId: string;
  domain: DomainType;
  amount: number;
  failureReason: string;
  failureCode?: string;
  attempts: number;
  maxAttempts: number;
  contactsMade: number;
  maxContacts: number;
  issuer?: string;
  status: CaseStatus;
  
  // Causal ML probabilities
  naturalRecoveryProbability: number; // e.g. 0.48 (48%)
  treatmentProbability: number;      // e.g. 0.72 (72%)
  incrementalUplift: number;         // e.g. 0.24 (+24%)
  
  // Economic metrics
  expectedRecoveredValue?: number;
  expectedNetRecoveryValue?: number;
  interventionCost?: number;
  
  recommendedAction: ActionType;
  recommendedActionLabel: string;
  recommendedTime: string;
  optimalWindow: string;
  
  decisionConfidence: number; // e.g. 0.96 (96%)
  decisionSource: DecisionSource;
  isOOD: boolean; // Out of distribution / limited evidence
  humanReviewRequired?: RoutingDecision;
  
  createdAt: string;
  updatedAt: string;
}

export interface ActionScore {
  action: ActionType;
  label: string;
  recoveryProbability: number;
  incrementalUplift: number;
  
  // Explicit Cost and Expected Net Value breakdown
  interventionCost?: number;
  incentiveCost?: number;
  operationalCost?: number;
  riskPenalty?: number;
  totalCost?: number;
  
  grossRecoveredValue?: number;       // P(Y=1|t) * amount
  expectedRecoveredValue?: number;    // tau(t) * amount
  expectedNetRecoveryValue?: number;  // gross - totalCost - riskPenalty
  incrementalNetRecoveryValue?: number; // incremental - totalCost - riskPenalty
  
  estimatedValue?: number; // legacy backward compatibility alias
  eligible: boolean;
  ineligibilityReason?: string;
  confidence?: number;
}

export interface SHAPAttribution {
  featureName: string;
  label: string;
  contribution: number; // e.g. +0.18 (+18%) or -0.06 (-6%)
  displayValue: string;
}

export interface HistoricalPrecedent {
  caseId: string;
  customerType: string;
  similarity: number;
  actionTaken: ActionType;
  outcome: 'RECOVERED' | 'FAILED';
  amount: number;
  daysAgo: number;
}

export interface NetworkPrior {
  networkWeight: number;      // e.g. 0.70 (70%)
  merchantWeight: number;     // e.g. 0.30 (30%)
  networkSampleSize: number;   // e.g. 12842931
  merchantSampleSize: number;  // e.g. 200
  coldStartBenefit: string;
}

export interface PolicyCheckItem {
  rule: string;
  description: string;
  passed: boolean;
  currentValue: string;
  limitValue: string;
}

export interface PolicyResult {
  passed: boolean;
  checksTotal: number;
  checksPassed: number;
  checks: PolicyCheckItem[];
  status?: 'PASS' | 'REVIEW' | 'BLOCK';
  reasons?: string[];
  overrideApplied?: boolean;
}

export interface TimingWindowScore {
  windowId: string;
  label: string;
  recommendedHour: number;
  timeWindowText: string;
  recoveryProbability: number;
  incrementalUplift: number;
  expectedNetValue: number;
  isOptimal: boolean;
  reason: string;
}

export interface RejectedAlternative {
  action: ActionType;
  label: string;
  recoveryProbability: number;
  expectedNetValue: number;
  reason: string;
}

export interface DecisionOutput {
  caseId: string;
  naturalRecoveryProbability: number;
  bestAction: ActionType;
  bestActionLabel: string;
  recommendedAction?: ActionType; // alias
  recommendedActionLabel?: string; // alias
  actionScores: ActionScore[];
  selectedActionScore?: ActionScore;
  incrementalUplift: number;
  confidence: number;
  expectedRecoveredValue?: number;
  expectedNetRecoveryValue?: number;
  humanReviewRequired?: RoutingDecision;
  
  timing: {
    recommendedHour: number;
    recommendedTimeText: string;
    optimalWindowText: string;
    optimalWindow?: TimingWindowScore;
    windows?: TimingWindowScore[];
    curvePoints: { hour: number; probability: number }[];
  };
  explanation: SHAPAttribution[];
  decisionReasons?: string[];
  rejectedAlternatives?: RejectedAlternative[];
  counterfactuals?: Record<ActionType, ActionScore>;
  precedents: HistoricalPrecedent[];
  networkPrior: NetworkPrior;
  policy: PolicyResult;
  uncertainty: {
    conformalInterval: [number, number];
    isOOD: boolean;
    coverageLevel: number;
  };
  executionReceipt?: {
    executionId: string;
    modelHash: string;
    policyHash: string;
    attestationStatus: string;
    timestamp: string;
  };
}

export interface ModelHealth {
  overallScore: number;
  upliftModelStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  hazardModelStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  policyEngineStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  dataPipelineStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  featureQualityStatus: 'GOOD' | 'FAIR' | 'POOR';
  auuc: number;
  qini: number;
  medianConfidence: number;
  conformalCoverage: number;
  oodCasesCount: number;
  psiScore?: number;
  driftStatus?: 'STABLE' | 'WARNING' | 'CRITICAL';
}

export interface BatchAutopilotResult {
  totalProcessed: number;
  totalGMVAtRisk: number;
  expectedNaturalRecovery: number;
  expectedRecoveredValue: number;
  expectedIncrementalRecovery: number;
  expectedIncrementalRevenue: number;
  totalInterventionCost: number;
  expectedNetRecoveredValue: number;
  autonomousCount: number;
  humanReviewCount: number;
  blockedCount: number;
  humanReviewRate: number;
  projectedUplift: number;
  retriesSavedPercent: number;
  contactsSavedPercent: number;
  actionDistribution: Record<ActionType, number>;
  processedDecisions: DecisionOutput[];
}

export interface ModelDriftReport {
  overallStatus: 'STABLE' | 'WARNING' | 'CRITICAL';
  status?: 'STABLE' | 'WARNING' | 'CRITICAL';
  psi: number;
  failureCodeShift: { name: string; baseline: number; current: number; delta: number }[];
  paymentMethodShift: { name: string; baseline: number; current: number; delta: number }[];
  channelResponseShift: { channel: string; baseline: number; current: number; delta: number }[];
  confidenceShift: { baseline: number; current: number };
  impactOnRouting: string;
  actionTaken?: string;
  features?: Record<string, { psi: number; status: 'STABLE' | 'WARNING' | 'CRITICAL' }>;
}

export interface ClosedLoopUpdateResult {
  caseId: string;
  action: ActionType;
  actionLabel: string;
  amount: number;
  recovered: boolean;
  timestamp: string;
  beforeStats: {
    attempts: number;
    successes: number;
    responseRate: number;
    confidence: number;
  };
  afterStats: {
    attempts: number;
    successes: number;
    responseRate: number;
    confidence: number;
  };
  posteriorShift: string;
  nextDecisionImpact: string;
  auditHash: string;
}

export interface FairnessMetrics {
  disparateImpact: number;
  equalOpportunity: number;
  calibrationError: number;
  segments: {
    segmentName: string;
    sampleSize: number;
    avgUplift: number;
    parityGap: number;
    status: 'FAIR' | 'INVESTIGATING' | 'DISPARITY_DETECTED';
  }[];
}

export interface AuditEvent {
  id: string;
  caseId: string;
  timestamp: string;
  stage: 'DETECTED' | 'CLASSIFIED' | 'DECIDED' | 'VALIDATED' | 'EXECUTED';
  title: string;
  description: string;
  statusBadge: string;
  actor: string;
  enclaveAttested?: boolean;
  action?: string;
  hash?: string;
  prevHash?: string;
  block_hash?: string;
  previous_hash?: string;
}
