/**
 * Comprehensive Functional Verification Suite for WAPSI Causal Decision Engine.
 * Tests all 18 requirements from user prompt:
 * 1. Natural recovery calculation
 * 2. Treatment probabilities calculation
 * 3. Uplift calculation
 * 4. Expected Net Value calculation
 * 5. Action selection (argmax net value)
 * 6. Economic edge case (Incentive highest prob, but WhatsApp highest Net Value)
 * 7. Counterfactual consistency
 * 8. Policy gating
 * 9. Human review routing
 * 10. Learning state update
 * 11. Batch aggregation
 * 12. AUTO + REVIEW + BLOCK invariant
 * 13. Governance threshold sensitivity
 * 14. Intervention cost sensitivity
 * 15. Transaction amount sensitivity
 * 16. Customer response sensitivity
 * 17. Drift sensitivity
 * 18. Timing optimization
 */

import { 
  getHeroTransaction, 
  makeRecoveryDecision, 
  calculateActionOutcome, 
  predictNaturalRecovery, 
  initialEngineState, 
  simulateRecoveryOutcome, 
  runBatchAutopilot, 
  generateSyntheticTransactions,
  generateDriftReport,
  optimizeTiming,
  evaluatePolicy,
  EngineState
} from '../src/services/causalEngine';

let passed = 0;
let failed = 0;

function assert(condition: boolean, testName: string, detail?: string) {
  if (condition) {
    console.log(`✅ PASS: ${testName}`);
    passed++;
  } else {
    console.error(`❌ FAIL: ${testName}${detail ? ` — ${detail}` : ''}`);
    failed++;
  }
}

console.log('============================================================');
console.log('      WAPSI CAUSAL ENGINE FUNCTIONAL TEST SUITE');
console.log('============================================================\n');

const heroTx = getHeroTransaction();

// 1. Natural Recovery Calculation
const p0 = predictNaturalRecovery(heroTx);
assert(p0 >= 0.40 && p0 <= 0.55, '1. Natural Recovery Prediction', `p0 = ${p0}, expected ~0.48`);

// 2. Treatment Probabilities Calculation
const noActionScore = calculateActionOutcome(heroTx, 'NO_ACTION', initialEngineState);
const retryScore = calculateActionOutcome(heroTx, 'RETRY', initialEngineState);
const waScore = calculateActionOutcome(heroTx, 'WHATSAPP', initialEngineState);
const voiceScore = calculateActionOutcome(heroTx, 'VOICE', initialEngineState);
const incScore = calculateActionOutcome(heroTx, 'INCENTIVE', initialEngineState);

assert(
  noActionScore.recoveryProbability === p0 &&
  retryScore.recoveryProbability > p0 &&
  waScore.recoveryProbability > retryScore.recoveryProbability &&
  voiceScore.recoveryProbability >= waScore.recoveryProbability &&
  incScore.recoveryProbability > voiceScore.recoveryProbability,
  '2. Treatment Probabilities Calculation Monotonicity',
  `P0: ${p0}, Retry: ${retryScore.recoveryProbability}, WA: ${waScore.recoveryProbability}, Voice: ${voiceScore.recoveryProbability}, Inc: ${incScore.recoveryProbability}`
);

// 3. Uplift Calculation
assert(
  Math.abs(waScore.incrementalUplift - (waScore.recoveryProbability - p0)) < 0.001,
  '3. Uplift Calculation: tau = P(t) - P(0)',
  `WA Uplift: ${waScore.incrementalUplift}, Diff: ${waScore.recoveryProbability - p0}`
);

// 4. Expected Net Value Calculation
// Net Value = Gross - Cost - Risk
const expectedNetWA = Math.round(waScore.grossRecoveredValue - waScore.totalCost - waScore.riskPenalty);
assert(
  waScore.expectedNetRecoveryValue === expectedNetWA,
  '4. Expected Net Value Formula',
  `Computed: ${waScore.expectedNetRecoveryValue}, Formula: ${expectedNetWA}`
);

// 5. Action Selection (argmax Expected Net Value)
const heroDecision = makeRecoveryDecision(heroTx, initialEngineState);
assert(
  heroDecision.bestAction === 'WHATSAPP',
  '5. Action Selection: WhatsApp selected',
  `Selected: ${heroDecision.bestAction}, NetValue: ${heroDecision.expectedNetRecoveryValue}`
);

// 6. Economic Edge Case Proof:
// Incentive has HIGHEST recovery prob, but WHATSAPP has HIGHEST expected net value
assert(
  incScore.recoveryProbability > waScore.recoveryProbability &&
  waScore.expectedNetRecoveryValue > incScore.expectedNetRecoveryValue &&
  waScore.expectedNetRecoveryValue > voiceScore.expectedNetRecoveryValue,
  '6. Economic Edge Case (Highest prob != Highest Net Value)',
  `Incentive Prob: ${incScore.recoveryProbability} (Net: ₹${incScore.expectedNetRecoveryValue}), Voice Prob: ${voiceScore.recoveryProbability} (Net: ₹${voiceScore.expectedNetRecoveryValue}), WA Prob: ${waScore.recoveryProbability} (Net: ₹${waScore.expectedNetRecoveryValue})`
);

// 7. Counterfactual Consistency
assert(
  heroDecision.counterfactuals !== undefined &&
  heroDecision.counterfactuals.NO_ACTION.expectedNetRecoveryValue === noActionScore.expectedNetRecoveryValue &&
  heroDecision.counterfactuals.WHATSAPP.expectedNetRecoveryValue === waScore.expectedNetRecoveryValue &&
  heroDecision.counterfactuals.INCENTIVE.expectedNetRecoveryValue === incScore.expectedNetRecoveryValue,
  '7. Counterfactual Consistency with Central Engine',
  'All 6 counterfactuals generated identically'
);

// 8. Policy Gating
const policyResult = evaluatePolicy(heroTx, 'WHATSAPP', waScore, initialEngineState);
assert(policyResult.status === 'PASS' && policyResult.checksPassed === 5, '8. Policy Gating (Hero case PASS 5/5)');

// 9. Human-in-the-loop Routing
assert(heroDecision.humanReviewRequired === 'AUTONOMOUS', '9. Human-in-the-loop: Hero case AUTONOMOUS');

// 10. Closed-loop Learning State Update
const simResult = simulateRecoveryOutcome(heroTx, 'WHATSAPP', initialEngineState, true);
assert(
  simResult.learningResult.afterStats.attempts === initialEngineState.learningState.WHATSAPP.attempts + 1 &&
  simResult.learningResult.afterStats.successes === initialEngineState.learningState.WHATSAPP.successes + 1 &&
  simResult.learningResult.afterStats.responseRate >= simResult.learningResult.beforeStats.responseRate,
  '10. Closed-loop Learning: Mutable prior update',
  `Before: ${simResult.learningResult.beforeStats.responseRate}, After: ${simResult.learningResult.afterStats.responseRate}`
);

// 11 & 12. Batch Autopilot & INVARIANT: AUTO + REVIEW + BLOCK == TOTAL
const sampleBatch = generateSyntheticTransactions(100, 42);
const batchResult = runBatchAutopilot(sampleBatch, initialEngineState);
assert(
  batchResult.totalProcessed === 100 &&
  batchResult.autonomousCount + batchResult.humanReviewCount + batchResult.blockedCount === 100,
  '11 & 12. Batch Autopilot & INVARIANT (AUTO + REVIEW + BLOCK == TOTAL)',
  `Total: ${batchResult.totalProcessed}, AUTO: ${batchResult.autonomousCount}, REVIEW: ${batchResult.humanReviewCount}, BLOCK: ${batchResult.blockedCount}`
);

// 13. Governance Threshold Sensitivity (increasing confidence threshold changes routing)
const strictState: EngineState = {
  ...initialEngineState,
  policyRules: {
    ...initialEngineState.policyRules,
    confidenceThreshold: 0.99, // ultra high confidence threshold forces cases into review
  },
};
const strictDecision = makeRecoveryDecision(heroTx, strictState);
assert(strictDecision.humanReviewRequired === 'HUMAN_REVIEW', '13. Governance Threshold Sensitivity', 'Confidence threshold 0.99 forces HUMAN_REVIEW');

// 14. Intervention Cost Sensitivity (increasing WhatsApp cost demotes WhatsApp)
const highCostState: EngineState = {
  ...initialEngineState,
  channelCosts: {
    ...initialEngineState.channelCosts,
    WHATSAPP: {
      ...initialEngineState.channelCosts.WHATSAPP,
      interventionCost: 500.0, // huge WhatsApp fee
    },
  },
};
const highCostDecision = makeRecoveryDecision(heroTx, highCostState);
assert(highCostDecision.bestAction !== 'WHATSAPP', '14. Intervention Cost Sensitivity', `High WA cost changed best action to ${highCostDecision.bestAction}`);

// 15. Transaction Amount Sensitivity
const tx1000 = { ...heroTx, amount: 1000 };
const tx10000 = { ...heroTx, amount: 10000 };
const dec1000 = makeRecoveryDecision(tx1000, initialEngineState);
const dec10000 = makeRecoveryDecision(tx10000, initialEngineState);
assert(
  dec10000.expectedNetRecoveryValue > dec1000.expectedNetRecoveryValue &&
  dec10000.selectedActionScore!.grossRecoveredValue > dec1000.selectedActionScore!.grossRecoveredValue,
  '15. Transaction Amount Sensitivity',
  `Amount 1k Net: ${dec1000.expectedNetRecoveryValue}, Amount 10k Net: ${dec10000.expectedNetRecoveryValue}`
);

// 16. Customer Response Sensitivity
const lowRespTx = { ...heroTx, historical_whatsapp_response: 0.15 };
const highRespTx = { ...heroTx, historical_whatsapp_response: 0.95 };
const lowRespScore = calculateActionOutcome(lowRespTx, 'WHATSAPP', initialEngineState);
const highRespScore = calculateActionOutcome(highRespTx, 'WHATSAPP', initialEngineState);
assert(
  highRespScore.recoveryProbability > lowRespScore.recoveryProbability,
  '16. Customer Historical Response Sensitivity',
  `Low (15%): ${lowRespScore.recoveryProbability}, High (95%): ${highRespScore.recoveryProbability}`
);

// 17. Drift Sensitivity
const driftCriticalState: EngineState = {
  ...initialEngineState,
  driftState: {
    level: 'CRITICAL',
    psi: 0.312,
    injectedDrift: true,
  },
};
const driftDecision = makeRecoveryDecision(heroTx, driftCriticalState);
assert(
  driftDecision.humanReviewRequired === 'HUMAN_REVIEW',
  '17. Drift Sensitivity: CRITICAL drift escalates cases to HUMAN_REVIEW',
  `Routing: ${driftDecision.humanReviewRequired}`
);

// 18. Timing Optimization
const timingRes = optimizeTiming(heroTx, 'WHATSAPP', initialEngineState);
assert(
  timingRes.optimalWindow.windowId === 'HOURS_18_24' && timingRes.optimalWindow.isOptimal,
  '18. Timing Optimization (18–24h window peak for insufficient funds)',
  `Optimal Window: ${timingRes.optimalWindow.label} (${timingRes.optimalWindow.timeWindowText})`
);

console.log('\n============================================================');
console.log(`TOTAL TESTS: ${passed + failed} | PASSED: ${passed} | FAILED: ${failed}`);
console.log('============================================================\n');

if (failed > 0) {
  process.exit(1);
}
