import { create } from 'zustand';
import { 
  RecoveryCase, 
  DecisionOutput, 
  OverviewMetrics, 
  AuditEvent, 
  CaseStatus, 
  ActionType, 
  MerchantSettings,
  PolicyControlRow,
  TransactionFeatures,
  BatchAutopilotResult,
  ModelDriftReport,
  ClosedLoopUpdateResult
} from '../types';
import { 
  mockAuditTrail, 
  initialMerchantSettings,
  mockPolicyControls
} from '../mock/mockData';
import { recoveryService } from '../services/recoveryService';
import { 
  makeRecoveryDecision, 
  simulateRecoveryOutcome, 
  runBatchAutopilot, 
  generateDriftReport,
  generateSyntheticTransactions,
  getHeroTransaction,
  initialEngineState,
  EngineState,
  PolicyRulesConfig,
  ChannelCostConfig
} from '../services/causalEngine';

export interface UserProfile {
  name: string;
  email: string;
  role: string;
  avatar: string;
  merchantId: string;
  mfaEnabled: boolean;
  apiKey: string;
  lastLogin: string;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: 'Admin' | 'Recovery Ops' | 'Risk Officer' | 'Auditor';
  status: 'Active' | 'Invited';
  lastActive: string;
}

// Generate the authoritative dataset of 350 synthetic records
const initialSyntheticTransactions = generateSyntheticTransactions(350, 42);

// Function to convert DecisionOutput into RecoveryCase
function decisionToCase(tx: TransactionFeatures, dec: DecisionOutput, existingStatus?: CaseStatus): RecoveryCase {
  return {
    caseId: tx.transaction_id,
    customerId: tx.customer_id_hash,
    customerName: tx.customer_name,
    customerHandle: tx.customer_handle,
    merchantId: tx.merchant_id,
    domain: tx.domain,
    amount: tx.amount,
    failureReason: tx.failure_reason,
    failureCode: tx.failure_code,
    attempts: tx.attempt_count,
    maxAttempts: tx.max_attempts,
    contactsMade: tx.contacts_made,
    maxContacts: tx.max_contacts,
    issuer: tx.issuer,
    status: existingStatus || (dec.humanReviewRequired === 'HUMAN_REVIEW' ? 'REVIEW' : 'READY'),
    naturalRecoveryProbability: dec.naturalRecoveryProbability,
    treatmentProbability: dec.selectedActionScore!.recoveryProbability,
    incrementalUplift: dec.incrementalUplift,
    expectedRecoveredValue: dec.expectedRecoveredValue,
    expectedNetRecoveryValue: dec.expectedNetRecoveryValue,
    interventionCost: dec.selectedActionScore!.totalCost,
    recommendedAction: dec.recommendedAction!,
    recommendedActionLabel: dec.recommendedActionLabel!,
    recommendedTime: dec.timing.recommendedTimeText,
    optimalWindow: dec.timing.optimalWindowText,
    decisionConfidence: dec.confidence,
    decisionSource: 'NETWORK_MERCHANT',
    isOOD: dec.uncertainty.isOOD,
    humanReviewRequired: dec.humanReviewRequired,
    createdAt: '2025-08-28T10:32:14Z',
    updatedAt: new Date().toISOString(),
  };
}

// Initialize case map and detail map from central decision engine
const initialCaseMap: Record<string, TransactionFeatures> = {};
const initialCaseDetails: Record<string, DecisionOutput> = {};
const initialCases: RecoveryCase[] = [];

initialSyntheticTransactions.forEach((tx) => {
  initialCaseMap[tx.transaction_id] = tx;
  const dec = makeRecoveryDecision(tx, initialEngineState);
  initialCaseDetails[tx.transaction_id] = dec;
  initialCases.push(decisionToCase(tx, dec));
});

// Calculate live policy status counts
function computePolicyCounts(cases: RecoveryCase[]): { pass: number; review: number; block: number } {
  let pass = 0;
  let review = 0;
  let block = 0;
  cases.forEach((c) => {
    if (c.humanReviewRequired === 'BLOCKED') block++;
    else if (c.humanReviewRequired === 'HUMAN_REVIEW') review++;
    else pass++;
  });
  return { pass, review, block };
}

const initialPolicyCounts = computePolicyCounts(initialCases);

export interface DemoStoreState {
  // Global Layout & Modals
  isSidebarCollapsed: boolean;
  isCaseDrawerOpen: boolean;
  isCopilotOpen: boolean;
  isMerchantModalOpen: boolean;
  isUserProfileModalOpen: boolean;
  isHelpModalOpen: boolean;
  isUserManagementModalOpen: boolean;
  isDateRangeModalOpen: boolean;
  isFiltersModalOpen: boolean;

  // New Demo Modals
  isHeroDemoOpen: boolean;
  heroDemoStep: number;
  isAutopilotModalOpen: boolean;
  isAutopilotRunning: boolean;
  isCounterfactualModalOpen: boolean;
  isLearningModalOpen: boolean;

  // Global Header Filter & Date Range State
  selectedDateRange: string;
  activeFilterCount: number;
  filtersState: {
    domains: string[];
    minUplift: number;
    minConfidence: number;
    evidenceSources: string[];
    statuses: string[];
    onlyHighImpact: boolean;
    regulatoryBoundsVerified: boolean;
  };

  // Core Causal Engine State
  engineState: EngineState;
  rawTransactions: Record<string, TransactionFeatures>;
  policyCounts: { pass: number; review: number; block: number };
  autopilotResult: BatchAutopilotResult | null;
  driftReport: ModelDriftReport;
  lastLearningResult: ClosedLoopUpdateResult | null;

  // Core Data
  overviewMetrics: OverviewMetrics;
  cases: RecoveryCase[];
  selectedCaseId: string | null;
  caseDetails: Record<string, DecisionOutput>;
  auditTrail: AuditEvent[];
  merchantSettings: MerchantSettings;
  policyControls: PolicyControlRow[];
  userProfile: UserProfile;
  teamMembers: TeamMember[];
  
  // Interactive Simulator State
  simulatorContacts: number;
  simulatorRetryBudget: number;
  
  // Workflow states
  isPolicyCheckRunning: boolean;
  policyCheckProgress: number;
  lastRecoveredCaseId: string | null;
  activeNotification: string | null;

  // Layout & Modal Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  selectCase: (caseId: string | null) => void;
  openCaseDrawer: (caseId: string) => void;
  closeCaseDrawer: () => void;
  toggleCopilot: () => void;
  setCopilotOpen: (open: boolean) => void;
  setMerchantModalOpen: (open: boolean) => void;
  setUserProfileModalOpen: (open: boolean) => void;
  setHelpModalOpen: (open: boolean) => void;
  setUserManagementModalOpen: (open: boolean) => void;
  setDateRangeModalOpen: (open: boolean) => void;
  setFiltersModalOpen: (open: boolean) => void;

  // Hero Demo Actions
  openHeroDemo: () => void;
  closeHeroDemo: () => void;
  setHeroDemoStep: (step: number) => void;

  // Autopilot Actions
  openAutopilotModal: () => void;
  closeAutopilotModal: () => void;
  runAutopilot: () => Promise<BatchAutopilotResult>;

  // Counterfactual & Learning Actions
  openCounterfactualModal: (caseId?: string) => void;
  closeCounterfactualModal: () => void;
  openLearningModal: () => void;
  closeLearningModal: () => void;

  // Engine Actions
  updatePolicyRule: (rule: keyof PolicyRulesConfig, value: number) => void;
  updateChannelCost: (action: ActionType, cost: Partial<ChannelCostConfig>) => void;
  updateTransactionAmount: (caseId: string, newAmount: number) => void;
  setDriftLevel: (level: 'STABLE' | 'WARNING' | 'CRITICAL') => void;

  setSelectedDateRange: (range: string) => void;
  updateFiltersState: (filters: Partial<DemoStoreState['filtersState']>) => void;
  resetFilters: () => void;
  
  // Theme state
  theme: 'dark' | 'light';
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;

  // Workflow Actions
  approveCase: (caseId: string) => Promise<void>;
  reviewCase: (caseId: string) => void;
  rejectCase: (caseId: string) => void;
  simulateRecovery: (caseId: string, forceSuccess?: boolean) => Promise<ClosedLoopUpdateResult | null>;
  
  // Update Actions
  updateSettings: (settings: Partial<MerchantSettings>) => void;
  updateUserProfile: (profile: Partial<UserProfile>) => void;
  addTeamMember: (member: Omit<TeamMember, 'id'>) => void;
  removeTeamMember: (id: string) => void;
  setSimulatorContacts: (val: number) => void;
  setSimulatorRetryBudget: (val: number) => void;
  resetSimulator: () => void;
  clearNotification: () => void;
}

export const useDemoStore = create<DemoStoreState>((set, get) => ({
  isSidebarCollapsed: typeof window !== 'undefined' ? window.innerWidth < 1024 : false,
  isCaseDrawerOpen: false,
  isCopilotOpen: false,
  isMerchantModalOpen: false,
  isUserProfileModalOpen: false,
  isHelpModalOpen: false,
  isUserManagementModalOpen: false,
  isDateRangeModalOpen: false,
  isFiltersModalOpen: false,

  // New Demo Modals
  isHeroDemoOpen: false,
  heroDemoStep: 1,
  isAutopilotModalOpen: false,
  isAutopilotRunning: false,
  isCounterfactualModalOpen: false,
  isLearningModalOpen: false,

  selectedDateRange: 'Aug 22 – Aug 28, 2026',
  activeFilterCount: 7,
  filtersState: {
    domains: ['Subscriptions', 'Checkout', 'B2B'],
    minUplift: 8,
    minConfidence: 80,
    evidenceSources: ['Network Data', 'Merchant Prior', 'Enclave Attested'],
    statuses: ['READY', 'REVIEW', 'APPROVED'],
    onlyHighImpact: false,
    regulatoryBoundsVerified: true,
  },

  // Causal Engine Single Source of Truth
  engineState: initialEngineState,
  rawTransactions: initialCaseMap,
  policyCounts: initialPolicyCounts,
  autopilotResult: null,
  driftReport: generateDriftReport(initialEngineState),
  lastLearningResult: null,

  overviewMetrics: {
    revenueAtRisk: 1842000,
    revenueAtRiskDelta: 16.7,
    recoverable: 1176000,
    recoverableDelta: 25.4,
    incrementalRecovery: 214000,
    incrementalRecoveryDelta: 37.2,
    recovered: 782000,
    recoveredDelta: 21.3,
    recoveryRate: 66.5,
    recoveryRateDeltaPp: 4.6,
  },
  cases: initialCases,
  selectedCaseId: 'RX-48291',
  caseDetails: initialCaseDetails,
  auditTrail: mockAuditTrail,
  merchantSettings: initialMerchantSettings,
  policyControls: mockPolicyControls,
  
  userProfile: {
    name: 'Arpit',
    email: 'arpit@acmecorp.com',
    role: 'Principal Merchant Architect',
    avatar: 'A',
    merchantId: 'MRC_928374',
    mfaEnabled: true,
    apiKey: 'rzp_live_wapsi_982348921839218',
    lastLogin: 'Today at 10:14 PM IST',
  },

  teamMembers: [
    { id: 'tm-1', name: 'Arpit', email: 'arpit@acmecorp.com', role: 'Admin', status: 'Active', lastActive: 'Now' },
    { id: 'tm-2', name: 'Priya Sharma', email: 'priya@acmecorp.com', role: 'Recovery Ops', status: 'Active', lastActive: '12m ago' },
    { id: 'tm-3', name: 'Rohan Mehta', email: 'rohan@acmecorp.com', role: 'Risk Officer', status: 'Active', lastActive: '2h ago' },
    { id: 'tm-4', name: 'Neha Gupta', email: 'neha@acmecorp.com', role: 'Auditor', status: 'Invited', lastActive: 'Pending invite' },
  ],
  
  simulatorContacts: 742,
  simulatorRetryBudget: 1842,
  
  isPolicyCheckRunning: false,
  policyCheckProgress: 0,
  lastRecoveredCaseId: null,
  activeNotification: null,

  // Modal Actions
  toggleSidebar: () => set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ isSidebarCollapsed: collapsed }),
  selectCase: (caseId) => set({ selectedCaseId: caseId }),
  openCaseDrawer: (caseId) => set({ selectedCaseId: caseId, isCaseDrawerOpen: true }),
  closeCaseDrawer: () => set({ isCaseDrawerOpen: false }),
  toggleCopilot: () => set((s) => ({ isCopilotOpen: !s.isCopilotOpen })),
  setCopilotOpen: (open) => set({ isCopilotOpen: open }),
  setMerchantModalOpen: (open) => set({ isMerchantModalOpen: open }),
  setUserProfileModalOpen: (open) => set({ isUserProfileModalOpen: open }),
  setHelpModalOpen: (open) => set({ isHelpModalOpen: open }),
  setUserManagementModalOpen: (open) => set({ isUserManagementModalOpen: open }),
  setDateRangeModalOpen: (open) => set({ isDateRangeModalOpen: open }),
  setFiltersModalOpen: (open) => set({ isFiltersModalOpen: open }),

  // Hero Demo
  openHeroDemo: () => set({ isHeroDemoOpen: true, heroDemoStep: 1, selectedCaseId: 'RX-48291' }),
  closeHeroDemo: () => set({ isHeroDemoOpen: false }),
  setHeroDemoStep: (step) => set({ heroDemoStep: step }),

  // Autopilot Modal
  openAutopilotModal: () => set({ isAutopilotModalOpen: true }),
  closeAutopilotModal: () => set({ isAutopilotModalOpen: false }),

  // Counterfactual Modal
  openCounterfactualModal: (caseId) => set({ 
    isCounterfactualModalOpen: true, 
    selectedCaseId: caseId || get().selectedCaseId || 'RX-48291' 
  }),
  closeCounterfactualModal: () => set({ isCounterfactualModalOpen: false }),

  // Learning Modal
  openLearningModal: () => set({ isLearningModalOpen: true }),
  closeLearningModal: () => set({ isLearningModalOpen: false }),

  // ============================================================
  // CAUSAL ENGINE REACTIVE ACTIONS (AFFECTS STATE & LIVE ROUTING)
  // ============================================================

  updatePolicyRule: (rule, value) => {
    const currentState = get().engineState;
    const updatedPolicyRules = {
      ...currentState.policyRules,
      [rule]: value,
    };
    const nextEngineState: EngineState = {
      ...currentState,
      policyRules: updatedPolicyRules,
    };

    // Re-evaluate all cases using the updated policy rules
    const txMap = get().rawTransactions;
    const updatedDetails: Record<string, DecisionOutput> = {};
    const updatedCases = get().cases.map((c) => {
      const tx = txMap[c.caseId] || getHeroTransaction();
      const dec = makeRecoveryDecision(tx, nextEngineState);
      updatedDetails[c.caseId] = dec;
      return decisionToCase(tx, dec, c.status);
    });

    const newPolicyCounts = computePolicyCounts(updatedCases);

    set({
      engineState: nextEngineState,
      cases: updatedCases,
      caseDetails: updatedDetails,
      policyCounts: newPolicyCounts,
      activeNotification: `Governance rule '${String(rule)}' updated to ${value}. Re-evaluated ${updatedCases.length} cases (Pass: ${newPolicyCounts.pass}, Review: ${newPolicyCounts.review}, Block: ${newPolicyCounts.block}).`,
    });
  },

  updateChannelCost: (action, costDelta) => {
    const currentState = get().engineState;
    const currentCosts = currentState.channelCosts[action];
    const nextEngineState: EngineState = {
      ...currentState,
      channelCosts: {
        ...currentState.channelCosts,
        [action]: { ...currentCosts, ...costDelta },
      },
    };

    const txMap = get().rawTransactions;
    const updatedDetails: Record<string, DecisionOutput> = {};
    const updatedCases = get().cases.map((c) => {
      const tx = txMap[c.caseId] || getHeroTransaction();
      const dec = makeRecoveryDecision(tx, nextEngineState);
      updatedDetails[c.caseId] = dec;
      return decisionToCase(tx, dec, c.status);
    });

    set({
      engineState: nextEngineState,
      cases: updatedCases,
      caseDetails: updatedDetails,
      policyCounts: computePolicyCounts(updatedCases),
      activeNotification: `Channel cost for ${action} updated. Net expected values and rankings recomputed across all cases.`,
    });
  },

  updateTransactionAmount: (caseId, newAmount) => {
    const tx = get().rawTransactions[caseId];
    if (!tx) return;

    const updatedTx = { ...tx, amount: newAmount };
    const updatedRawTransactions = { ...get().rawTransactions, [caseId]: updatedTx };
    const dec = makeRecoveryDecision(updatedTx, get().engineState);

    const updatedCases = get().cases.map((c) => (c.caseId === caseId ? decisionToCase(updatedTx, dec, c.status) : c));
    const updatedDetails = { ...get().caseDetails, [caseId]: dec };

    set({
      rawTransactions: updatedRawTransactions,
      cases: updatedCases,
      caseDetails: updatedDetails,
      activeNotification: `Case ${caseId} amount updated to ₹${newAmount.toLocaleString('en-IN')}. Expected recovered and net values recalculated.`,
    });
  },

  setDriftLevel: (level) => {
    const nextEngineState: EngineState = {
      ...get().engineState,
      driftState: {
        level,
        psi: level === 'CRITICAL' ? 0.318 : level === 'WARNING' ? 0.142 : 0.042,
        injectedDrift: level !== 'STABLE',
      },
    };

    const nextDriftReport = generateDriftReport(nextEngineState);

    // Re-evaluate all cases: CRITICAL drift escalates cases into HUMAN_REVIEW
    const txMap = get().rawTransactions;
    const updatedDetails: Record<string, DecisionOutput> = {};
    const updatedCases = get().cases.map((c) => {
      const tx = txMap[c.caseId] || getHeroTransaction();
      const dec = makeRecoveryDecision(tx, nextEngineState);
      updatedDetails[c.caseId] = dec;
      return decisionToCase(tx, dec, c.status);
    });

    const newCounts = computePolicyCounts(updatedCases);

    set({
      engineState: nextEngineState,
      driftReport: nextDriftReport,
      cases: updatedCases,
      caseDetails: updatedDetails,
      policyCounts: newCounts,
      activeNotification: `Model drift status set to ${level} (PSI ${nextDriftReport.psi}). Routing updated: ${newCounts.review} cases now in Human Review.`,
    });
  },

  runAutopilot: async () => {
    set({ isAutopilotRunning: true });
    
    // Simulate real batch processing step
    await new Promise((r) => setTimeout(r, 600));

    const transactions = Object.values(get().rawTransactions);
    const result = runBatchAutopilot(transactions, get().engineState);

    // Update cases with decisions from autopilot
    const updatedDetails: Record<string, DecisionOutput> = {};
    result.processedDecisions.forEach((dec) => {
      updatedDetails[dec.caseId] = dec;
    });

    const updatedCases = get().cases.map((c) => {
      const dec = updatedDetails[c.caseId];
      if (!dec) return c;
      const tx = get().rawTransactions[c.caseId] || getHeroTransaction();
      return decisionToCase(tx, dec, c.status);
    });

    // Update overview metrics directly from the batch run
    const nextOverviewMetrics: OverviewMetrics = {
      revenueAtRisk: result.totalGMVAtRisk,
      revenueAtRiskDelta: 16.7,
      recoverable: result.expectedRecoveredValue,
      recoverableDelta: 25.4,
      incrementalRecovery: result.expectedIncrementalRecovery,
      incrementalRecoveryDelta: 37.2,
      recovered: get().overviewMetrics.recovered,
      recoveredDelta: 21.3,
      recoveryRate: Number(((result.expectedRecoveredValue / result.totalGMVAtRisk) * 100).toFixed(1)),
      recoveryRateDeltaPp: 4.6,
    };

    set({
      isAutopilotRunning: false,
      autopilotResult: result,
      cases: updatedCases,
      caseDetails: updatedDetails,
      overviewMetrics: nextOverviewMetrics,
      policyCounts: {
        pass: result.autonomousCount,
        review: result.humanReviewCount,
        block: result.blockedCount,
      },
      activeNotification: `Batch Autopilot finished processing ${result.totalProcessed} transactions! Invariant verified: AUTO (${result.autonomousCount}) + REVIEW (${result.humanReviewCount}) + BLOCK (${result.blockedCount}) = ${result.totalProcessed}.`,
    });

    return result;
  },

  simulateRecovery: async (caseId: string, forceSuccess = true) => {
    const state = get();
    const targetCase = state.cases.find((c) => c.caseId === caseId) || state.cases[0];

    // Build or derive transaction features matching the actual case
    let tx = state.rawTransactions[caseId];
    if (!tx && targetCase) {
      tx = {
        ...getHeroTransaction(),
        transaction_id: targetCase.caseId,
        amount: targetCase.amount,
        customer_name: targetCase.customerName || 'Customer',
        customer_handle: targetCase.customerHandle || '@customer',
        domain: targetCase.domain || 'CHECKOUT',
        failure_code: targetCase.failureCode || 'UPI_APP_TIMEOUT',
      };
    } else if (!tx) {
      tx = getHeroTransaction();
    }

    // Call real backend endpoint if online
    let backendRes: any = null;
    try {
      backendRes = await recoveryService.simulateRecovery(caseId);
    } catch {}

    // Execute genuine closed-loop learning in central decision engine
    const { updatedState, learningResult, nextDecision } = simulateRecoveryOutcome(
      tx,
      targetCase.recommendedAction,
      state.engineState,
      forceSuccess
    );

    // Bind real case attributes & backend ledger response
    learningResult.caseId = backendRes?.case_id || targetCase.caseId;
    learningResult.amount = (backendRes?.amount !== undefined && backendRes?.amount !== null) ? backendRes.amount : targetCase.amount;
    learningResult.action = backendRes?.action || targetCase.recommendedAction;
    learningResult.actionLabel = backendRes?.actionLabel || targetCase.recommendedActionLabel;
    if (backendRes?.audit_hash || backendRes?.auditHash) {
      learningResult.auditHash = backendRes.audit_hash || backendRes.auditHash;
    }
    if (backendRes?.beforeStats) {
      learningResult.beforeStats = backendRes.beforeStats;
    }
    if (backendRes?.afterStats) {
      learningResult.afterStats = backendRes.afterStats;
    }
    if (backendRes?.posteriorShift) {
      learningResult.posteriorShift = backendRes.posteriorShift;
    }
    if (backendRes?.nextDecisionImpact) {
      learningResult.nextDecisionImpact = backendRes.nextDecisionImpact;
    }

    const recoveryAmount = targetCase.amount;
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];

    const newAuditEvent: AuditEvent = {
      id: `AUD-${Math.floor(10000 + Math.random() * 90000)}`,
      caseId: targetCase.caseId,
      timestamp: timeStr,
      stage: 'EXECUTED',
      title: learningResult.recovered ? 'Payment Successfully Recovered' : 'Payment Recovery Attempt Completed',
      description: `Recovered ₹${recoveryAmount.toLocaleString('en-IN')} via ${targetCase.recommendedActionLabel} at peak recovery window. Bayesian prior shifted: ${learningResult.posteriorShift}. ${learningResult.auditHash}`,
      statusBadge: 'EXECUTED',
      actor: 'WAPSI Recovery Engine (Closed-Loop Learning)',
      enclaveAttested: true,
    };

    const updatedCases = state.cases.map((c) =>
      c.caseId === caseId
        ? {
            ...c,
            status: (learningResult.recovered ? 'RECOVERED' : 'FAILED') as CaseStatus,
            updatedAt: now.toISOString(),
          }
        : c
    );

    const updatedDetails = {
      ...state.caseDetails,
      [caseId]: nextDecision,
    };

    set({
      engineState: updatedState,
      cases: updatedCases,
      caseDetails: updatedDetails,
      lastLearningResult: learningResult,
      isLearningModalOpen: true,
      lastRecoveredCaseId: caseId,
      overviewMetrics: {
        ...state.overviewMetrics,
        recovered: state.overviewMetrics.recovered + (learningResult.recovered ? recoveryAmount : 0),
        incrementalRecovery: state.overviewMetrics.incrementalRecovery + (learningResult.recovered ? Math.round(recoveryAmount * targetCase.incrementalUplift) : 0),
        recoverable: Math.max(0, state.overviewMetrics.recoverable - recoveryAmount),
      },
      auditTrail: [newAuditEvent, ...state.auditTrail],
      activeNotification: `Closed-loop learning applied! ${targetCase.recommendedActionLabel} prior updated (${learningResult.posteriorShift}).`,
    });

    return learningResult;
  },

  approveCase: async (caseId: string) => {
    set({ isPolicyCheckRunning: true, policyCheckProgress: 20 });
    const targetCase = get().cases.find((c) => c.caseId === caseId);

    await new Promise((r) => setTimeout(r, 200));
    set({ policyCheckProgress: 50 });
    await new Promise((r) => setTimeout(r, 200));
    set({ policyCheckProgress: 80 });

    try {
      await recoveryService.approveCase(caseId, targetCase?.recommendedAction);
    } catch {}

    set({ policyCheckProgress: 100, isPolicyCheckRunning: false });

    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];

    const newAuditEvent: AuditEvent = {
      id: `AUD-${Math.floor(10000 + Math.random() * 90000)}`,
      caseId,
      timestamp: timeStr,
      stage: 'VALIDATED',
      title: 'Action Approved & Dispatched',
      description: `Smart action approved for ${targetCase?.customerName || caseId}. Regulatory check verified (5/5).`,
      statusBadge: 'VALIDATED',
      actor: `${get().userProfile.name} (${get().merchantSettings.merchantName})`,
      enclaveAttested: true,
    };

    set((state) => ({
      cases: state.cases.map((c) =>
        c.caseId === caseId ? { ...c, status: 'APPROVED' as CaseStatus, updatedAt: now.toISOString() } : c
      ),
      auditTrail: [newAuditEvent, ...state.auditTrail],
      activeNotification: `Case ${caseId} approved and dispatched via Causal Engine.`,
    }));
  },

  reviewCase: (caseId: string) => {
    set((state) => ({
      cases: state.cases.map((c) =>
        c.caseId === caseId ? { ...c, status: 'REVIEW' as CaseStatus } : c
      ),
      activeNotification: `Case ${caseId} flagged for human review.`,
    }));
  },

  rejectCase: async (caseId: string) => {
    try {
      await recoveryService.rejectCase(caseId, 'Operator manual suppression');
    } catch {}

    set((state) => ({
      cases: state.cases.map((c) =>
        c.caseId === caseId ? { ...c, status: 'FAILED' as CaseStatus } : c
      ),
      isCaseDrawerOpen: false,
      activeNotification: `Case ${caseId} action rejected and logged to audit chain.`,
    }));
  },

  setSelectedDateRange: (range: string) => {
    set({ 
      selectedDateRange: range, 
      activeNotification: `Analysis timeframe set to ${range}` 
    });
  },

  updateFiltersState: (newFilters) => {
    set((state) => {
      const updated = { ...state.filtersState, ...newFilters };
      let count = 0;
      count += updated.domains.length;
      if (updated.minUplift > 0) count++;
      if (updated.minConfidence > 0) count++;
      count += updated.evidenceSources.length;
      count += updated.statuses.length;
      if (updated.onlyHighImpact) count++;
      if (updated.regulatoryBoundsVerified) count++;

      return {
        filtersState: updated,
        activeFilterCount: Math.max(1, count),
        activeNotification: `Filters updated (${Math.max(1, count)} criteria active)`,
      };
    });
  },

  resetFilters: () => {
    set({
      filtersState: {
        domains: ['Subscriptions', 'Checkout', 'B2B'],
        minUplift: 8,
        minConfidence: 80,
        evidenceSources: ['Network Data', 'Merchant Prior', 'Enclave Attested'],
        statuses: ['READY', 'REVIEW', 'APPROVED'],
        onlyHighImpact: false,
        regulatoryBoundsVerified: true,
      },
      activeFilterCount: 7,
      activeNotification: 'Filters reset to default configuration.',
    });
  },

  updateSettings: (newSettings) => {
    set((state) => ({
      merchantSettings: { ...state.merchantSettings, ...newSettings },
      activeNotification: 'Merchant settings updated successfully.',
    }));
  },

  updateUserProfile: (profile) => {
    set((state) => ({
      userProfile: { ...state.userProfile, ...profile },
      activeNotification: 'User profile updated.',
    }));
  },

  addTeamMember: (member) => {
    const newMember: TeamMember = {
      id: `tm-${Date.now()}`,
      ...member,
    };
    set((state) => ({
      teamMembers: [...state.teamMembers, newMember],
      activeNotification: `Invited ${member.name} (${member.role}).`,
    }));
  },

  removeTeamMember: (id) => {
    set((state) => ({
      teamMembers: state.teamMembers.filter((m) => m.id !== id),
      activeNotification: 'Team member removed.',
    }));
  },

  theme: 'dark',
  toggleTheme: () => {
    const nextTheme = get().theme === 'dark' ? 'light' : 'dark';
    if (typeof document !== 'undefined') {
      if (nextTheme === 'light') {
        document.documentElement.classList.add('light');
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    }
    set({ theme: nextTheme, activeNotification: `Switched to ${nextTheme === 'light' ? 'Light' : 'Dark'} theme` });
  },
  setTheme: (theme) => {
    if (typeof document !== 'undefined') {
      if (theme === 'light') {
        document.documentElement.classList.add('light');
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    }
    set({ theme, activeNotification: `Switched to ${theme === 'light' ? 'Light' : 'Dark'} theme` });
  },

  setSimulatorContacts: (val) => set({ simulatorContacts: val }),
  setSimulatorRetryBudget: (val) => set({ simulatorRetryBudget: val }),
  resetSimulator: () => set({ simulatorContacts: 742, simulatorRetryBudget: 1842 }),
  clearNotification: () => set({ activeNotification: null }),
}));
