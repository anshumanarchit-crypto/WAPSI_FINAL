# 06 — Causal ML & Data Contract Specification

This specification formalizes the exact data contracts required by WAPSI's future Causal Machine Learning Engine (EconML, T-Learner/X-Learner, Survival Hazard models, Conformal Inference).

## 1. Action Types
```typescript
export type ActionType = 
  | 'NO_ACTION' 
  | 'RETRY' 
  | 'WHATSAPP' 
  | 'VOICE' 
  | 'EMAIL' 
  | 'INCENTIVE';
```

## 2. Recovery Case Interface
```typescript
export interface RecoveryCase {
  caseId: string;
  customerId: string;
  merchantId: string;
  domain: 'SUBSCRIPTIONS' | 'CHECKOUT' | 'RECEIVABLES_B2B';
  amount: number;
  failureReason: string;
  failureCode?: string;
  attempts: number;
  maxAttempts: number;
  contactsMade: number;
  maxContacts: number;
  issuer?: string;
  status: 'DETECTED' | 'SCORED' | 'READY' | 'REVIEW' | 'APPROVED' | 'ACTIONED' | 'RECOVERED' | 'FAILED' | 'ESCALATED' | 'MONITORING';
  
  // Causal Probabilities
  naturalRecoveryProbability: number; // P_0 (No Action)
  treatmentProbability: number;      // P_t (With Intervention)
  incrementalUplift: number;         // tau = P_t - P_0
  
  recommendedAction: ActionType;
  recommendedTime: string;
  optimalWindow: string;
  
  decisionConfidence: number; // 0.0 - 1.0 (e.g. 0.96)
  decisionSource: 'NETWORK' | 'MERCHANT' | 'NETWORK_MERCHANT';
  isOOD: boolean; // Out of distribution / limited evidence
  
  createdAt: string;
  updatedAt: string;
}
```

## 3. Decision Output & Explainability Interface
```typescript
export interface ActionScore {
  action: ActionType;
  label: string;
  recoveryProbability: number;
  incrementalUplift: number;
  estimatedValue?: number;
  eligible: boolean;
  ineligibilityReason?: string;
}

export interface SHAPAttribution {
  featureName: string;
  label: string;
  contribution: number; // e.g. +0.18 (+18%) or -0.06 (-6%)
  displayValue: string;
}

export interface HistoricalPrecedent {
  caseId: string;
  similarity: number;
  actionTaken: ActionType;
  outcome: 'RECOVERED' | 'FAILED';
  amount: number;
  daysAgo: number;
}

export interface NetworkPrior {
  networkWeight: number;    // e.g. 0.70 (70%)
  merchantWeight: number;   // e.g. 0.30 (30%)
  networkSampleSize: number; // e.g. 12,842,931
  merchantSampleSize: number; // e.g. 200
  coldStartBenefit: string;
}

export interface PolicyResult {
  passed: boolean;
  checksTotal: number;
  checksPassed: number;
  checks: {
    rule: string;
    description: string;
    passed: boolean;
    currentValue: string;
    limitValue: string;
  }[];
}

export interface DecisionOutput {
  caseId: string;
  naturalRecoveryProbability: number;
  bestAction: ActionType;
  actionScores: ActionScore[];
  incrementalUplift: number;
  confidence: number;
  timing: {
    recommendedHour: number;
    recommendedTimeText: string;
    optimalWindowText: string;
    curvePoints: { hour: number; probability: number }[];
  };
  explanation: SHAPAttribution[];
  precedents: HistoricalPrecedent[];
  networkPrior: NetworkPrior;
  policy: PolicyResult;
  uncertainty: {
    conformalInterval: [number, number];
    isOOD: boolean;
    coverageLevel: number;
  };
}
```

## 4. Model Health & Fairness Interfaces
```typescript
export interface ModelHealth {
  overallScore: number;
  upliftModelStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  hazardModelStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  policyEngineStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  dataPipelineStatus: 'HEALTHY' | 'WARNING' | 'DEGRADED';
  featureQualityStatus: 'GOOD' | 'FAIR' | 'POOR';
  auuc: number;             // e.g. 0.87
  qini: number;             // e.g. 0.31
  medianConfidence: number; // e.g. 0.91 (91%)
  conformalCoverage: number;// e.g. 0.951 (95.1%)
  oodCasesCount: number;    // e.g. 7
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
```
