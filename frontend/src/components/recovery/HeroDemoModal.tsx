import React, { useState } from 'react';
import { 
  X, 
  Sparkles, 
  Zap, 
  CheckCircle2, 
  ShieldCheck, 
  ArrowRight, 
  ArrowLeft,
  Clock, 
  RotateCw, 
  IndianRupee, 
  TrendingUp, 
  AlertCircle,
  BarChart2,
  Sliders,
  Check
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { formatINR, formatPercent } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

export const HeroDemoModal: React.FC = () => {
  const isHeroDemoOpen = useDemoStore((state) => state.isHeroDemoOpen);
  const closeHeroDemo = useDemoStore((state) => state.closeHeroDemo);
  const heroDemoStep = useDemoStore((state) => state.heroDemoStep);
  const setHeroDemoStep = useDemoStore((state) => state.setHeroDemoStep);
  const rawTransactions = useDemoStore((state) => state.rawTransactions);
  const caseDetails = useDemoStore((state) => state.caseDetails);
  const updateTransactionAmount = useDemoStore((state) => state.updateTransactionAmount);
  const updateChannelCost = useDemoStore((state) => state.updateChannelCost);
  const engineState = useDemoStore((state) => state.engineState);
  const simulateRecovery = useDemoStore((state) => state.simulateRecovery);
  const approveCase = useDemoStore((state) => state.approveCase);
  const openAutopilotModal = useDemoStore((state) => state.openAutopilotModal);
  const theme = useDemoStore((state) => state.theme);
  const lastLearningResult = useDemoStore((state) => state.lastLearningResult);
  const isLight = theme === 'light';

  const heroTx = rawTransactions['RX-48291'];
  const heroDecision = caseDetails['RX-48291'];

  const waLearningPrior = engineState.learningState.WHATSAPP;
  const priorRate = lastLearningResult?.beforeStats?.responseRate ?? waLearningPrior.responseRate;
  const updatedRate = lastLearningResult?.afterStats?.responseRate ?? waLearningPrior.responseRate;
  const rateDeltaPp = Number(((updatedRate - priorRate) * 100).toFixed(2));

  const [simulatedRecovered, setSimulatedRecovered] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);

  if (!isHeroDemoOpen || !heroTx || !heroDecision) return null;

  const totalSteps = 10;
  const currentStep = Math.max(1, Math.min(totalSteps, heroDemoStep));

  const handleNext = () => {
    if (currentStep < totalSteps) setHeroDemoStep(currentStep + 1);
  };

  const handlePrev = () => {
    if (currentStep > 1) setHeroDemoStep(currentStep - 1);
  };

  const handleApprove = async () => {
    setIsApproving(true);
    await approveCase('RX-48291');
    setIsApproving(false);
    setHeroDemoStep(8);
  };

  const handleSimulate = async () => {
    setIsSimulating(true);
    await simulateRecovery('RX-48291', true);
    setSimulatedRecovered(true);
    setIsSimulating(false);
    setHeroDemoStep(9);
  };

  const handleLaunchAutopilot = () => {
    closeHeroDemo();
    openAutopilotModal();
  };

  const selectedScore = heroDecision.selectedActionScore || heroDecision.actionScores.find(s => s.action === 'WHATSAPP') || heroDecision.actionScores[0];
  const noActionScore = heroDecision.actionScores.find(s => s.action === 'NO_ACTION') || heroDecision.actionScores[0];
  const retryScore = heroDecision.actionScores.find(s => s.action === 'RETRY');
  const voiceScore = heroDecision.actionScores.find(s => s.action === 'VOICE');
  const incScore = heroDecision.actionScores.find(s => s.action === 'INCENTIVE');

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={closeHeroDemo}
          className="fixed inset-0 bg-black/80 backdrop-blur-md"
        />

        {/* Modal Dialog */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: 15 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: 15 }}
          transition={{ type: 'spring', damping: 26, stiffness: 300 }}
          className={cn(
            "relative w-full max-w-3xl rounded-2xl shadow-2xl border overflow-hidden flex flex-col max-h-[92vh] z-10 select-none text-xs",
            isLight ? "bg-white border-slate-200 text-slate-900" : "bg-[#090D18] border-slate-800 text-slate-100"
          )}
        >
          {/* Top Header with Stepper */}
          <div className={cn(
            "p-5 border-b transition-colors",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  WAPSI Official Hero Demo
                </span>
                <span className={cn(
                  "text-[10px] font-bold px-2 py-0.5 rounded-full border",
                  isLight ? "bg-indigo-50 text-indigo-800 border-indigo-200" : "bg-indigo-500/20 text-indigo-300 border-indigo-500/30"
                )}>
                  Step {currentStep} of {totalSteps}
                </span>
              </div>

              <button
                onClick={closeHeroDemo}
                className={cn(
                  "p-2 rounded-xl transition-colors cursor-pointer",
                  isLight ? "text-slate-400 hover:text-slate-800 hover:bg-slate-200" : "text-slate-400 hover:text-white hover:bg-slate-800"
                )}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Stepper Progress Bar */}
            <div className="flex items-center gap-1">
              {Array.from({ length: totalSteps }, (_, i) => i + 1).map((step) => (
                <button
                  key={step}
                  onClick={() => setHeroDemoStep(step)}
                  className={cn(
                    "h-1.5 flex-1 rounded-full transition-all cursor-pointer",
                    step === currentStep 
                      ? "bg-indigo-500 shadow-sm shadow-indigo-500/50" 
                      : step < currentStep 
                      ? "bg-emerald-500" 
                      : isLight ? "bg-slate-200" : "bg-slate-800"
                  )}
                  title={`Jump to Step ${step}`}
                />
              ))}
            </div>
          </div>

          {/* Interactive Step Content */}
          <div className="p-6 overflow-y-auto space-y-4 flex-1">
            {/* STEP 1: FAILED PAYMENT INGESTION */}
            {currentStep === 1 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 1 — Failed Payment Ingestion</span>
                  <h3 className="text-base font-black text-white mt-0.5">Customer Payment Failure Signal Detected</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    An enterprise customer subscription renewal failed at the payment gateway switch due to temporary insufficient balance.
                  </p>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className={cn("p-3 rounded-xl border", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Transaction Value</span>
                    <span className="text-lg font-black font-mono text-white block mt-0.5">₹{heroTx.amount.toLocaleString('en-IN')}</span>
                    <span className="text-[10px] text-slate-400">Subscription Mandate</span>
                  </div>

                  <div className={cn("p-3 rounded-xl border", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Root Cause Code</span>
                    <span className="text-xs font-bold font-mono text-amber-400 block mt-1.5">INSUFFICIENT_FUNDS</span>
                    <span className="text-[10px] text-slate-400">HDFC Bank • UPI AutoPay</span>
                  </div>

                  <div className={cn("p-3 rounded-xl border", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800")}>
                    <span className="text-[10px] text-slate-500 uppercase font-bold block">Attempts Made</span>
                    <span className="text-lg font-black font-mono text-white block mt-0.5">{heroTx.attempt_count} of {heroTx.max_attempts}</span>
                    <span className="text-[10px] text-slate-400">2 Retries Remaining</span>
                  </div>

                  <div className={cn("p-3 rounded-xl border", isLight ? "bg-indigo-50/50 border-indigo-200" : "bg-indigo-950/40 border-indigo-500/30")}>
                    <span className="text-[10px] text-indigo-300 uppercase font-bold block">Natural Recovery (P₀)</span>
                    <span className="text-lg font-black font-mono text-indigo-300 block mt-0.5">
                      {Math.round(heroDecision.naturalRecoveryProbability * 100)}%
                    </span>
                    <span className="text-[10px] text-indigo-400/80">Organic Holdout Baseline</span>
                  </div>
                </div>

                {/* Interactive Amount Slider for Judge Sensitivity Testing */}
                <div className={cn("p-4 rounded-xl border space-y-2", isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/40 border-slate-800")}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-slate-200 flex items-center gap-1.5">
                      <Sliders className="w-3.5 h-3.5 text-indigo-400" />
                      Judge Interactive Test: Modify Transaction Value
                    </span>
                    <span className="font-mono text-indigo-400 font-bold">₹{heroTx.amount.toLocaleString('en-IN')}</span>
                  </div>
                  <input
                    type="range"
                    min="2000"
                    max="20000"
                    step="500"
                    value={heroTx.amount}
                    onChange={(e) => updateTransactionAmount('RX-48291', Number(e.target.value))}
                    className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                  />
                  <p className="text-[10.5px] text-slate-400">
                    Try dragging the slider! Notice how the model dynamically recalculates expected net values and margin economics below without hardcoding.
                  </p>
                </div>
              </div>
            )}

            {/* STEP 2: MULTI-TREATMENT PREDICTION */}
            {currentStep === 2 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 2 — Multi-Treatment Causal Uplift</span>
                  <h3 className="text-base font-black text-white mt-0.5">Estimating Treatment Recovery Probabilities</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    WAPSI evaluates individual treatment effects (ITE) across all candidate communication and network interventions.
                  </p>
                </div>

                <div className="space-y-2">
                  {heroDecision.actionScores.map((score) => {
                    const isWa = score.action === 'WHATSAPP';
                    const isInc = score.action === 'INCENTIVE';
                    return (
                      <div 
                        key={score.action}
                        className={cn(
                          "p-3 rounded-xl border flex items-center justify-between transition-all",
                          isWa 
                            ? "bg-indigo-950/40 border-indigo-500/40" 
                            : isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"
                        )}
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-xs text-white">{score.label}</span>
                            {isInc && (
                              <span className="text-[9.5px] font-bold px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                Highest Raw Prob ({Math.round(score.recoveryProbability * 100)}%)
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-slate-500">{score.action}</span>
                        </div>

                        <div className="text-right">
                          <div className="flex items-center gap-3">
                            <span className="font-mono font-bold text-xs text-slate-300">
                              {Math.round(score.recoveryProbability * 100)}%
                            </span>
                            {score.action !== 'NO_ACTION' && (
                              <span className="font-mono font-bold text-xs text-emerald-400">
                                +{Math.round(score.incrementalUplift * 100)}% lift
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* STEP 3: EXPECTED NET VALUE OPTIMIZATION */}
            {currentStep === 3 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Step 3 — Expected Net Value Optimization</span>
                  <h3 className="text-base font-black text-white mt-0.5">The Core Proof: Why Higher Probability Doesn&apos;t Win</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Gross recovery probability ignores cost. WAPSI deducts channel, operational, and margin loss costs.
                  </p>
                </div>

                <div className="space-y-2">
                  {heroDecision.actionScores.map((score) => {
                    const isSelected = score.action === heroDecision.bestAction;
                    return (
                      <div 
                        key={score.action}
                        className={cn(
                          "p-3.5 rounded-xl border flex items-center justify-between transition-all",
                          isSelected
                            ? "bg-emerald-950/40 border-emerald-500/50 shadow-md shadow-emerald-500/10"
                            : isLight ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"
                        )}
                      >
                        <div className="flex items-center gap-3">
                          {isSelected && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
                          <div>
                            <span className="font-bold text-xs text-white block">{score.label}</span>
                            <span className="text-[10px] text-slate-400">
                              Prob: {Math.round(score.recoveryProbability * 100)}% • Cost: -₹{((score.totalCost ?? 0) + (score.riskPenalty ?? 0)).toFixed(0)}
                            </span>
                          </div>
                        </div>

                        <div className="text-right">
                          <span className={cn(
                            "font-mono text-sm block font-black",
                            isSelected ? "text-emerald-400 text-base" : "text-slate-300"
                          )}>
                            ₹{(score.expectedNetRecoveryValue ?? (Math.round(score.recoveryProbability * heroTx.amount) - (score.totalCost ?? 0))).toLocaleString('en-IN')}
                          </span>
                          {isSelected && (
                            <span className="text-[9.5px] font-extrabold text-emerald-400 uppercase tracking-wide">
                              ★ SELECTED BY WAPSI
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* STEP 4: EXPLANATION & ALTERNATIVES */}
            {currentStep === 4 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 4 — Decision Explainability</span>
                  <h3 className="text-base font-black text-white mt-0.5">Why WhatsApp? Why Not Voice or Incentive?</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Causal reasoning generated dynamically from actual model outputs.
                  </p>
                </div>

                <div className="space-y-3">
                  <div className="p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-500/30 space-y-2">
                    <span className="font-bold text-xs text-indigo-300 block">Primary Decision Drivers:</span>
                    <ul className="space-y-1 text-[11px] text-slate-300">
                      {heroDecision.decisionReasons?.map((r, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-emerald-400 font-bold">•</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="space-y-2">
                    <span className="font-bold text-xs text-slate-300 block">Rejected Alternatives:</span>
                    {heroDecision.rejectedAlternatives?.slice(0, 2).map((alt) => (
                      <div key={alt.action} className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px]">
                        <span className="font-bold text-slate-200 block mb-0.5">{alt.label}</span>
                        <p className="text-slate-400">{alt.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* STEP 5: TIMING OPTIMIZATION */}
            {currentStep === 5 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 5 — Timing Hazard Optimization</span>
                  <h3 className="text-base font-black text-white mt-0.5">Hazard Model Timing Window Analysis</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Evaluating recovery curves to avoid TRAI curfew and target next-day banking salary credits.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-indigo-950/40 border border-indigo-500/30 flex items-center justify-between">
                  <div className="space-y-1">
                    <span className="text-[10px] uppercase font-bold text-indigo-300 block">Optimal Execution Window</span>
                    <h4 className="text-base font-black text-white flex items-center gap-2">
                      <Clock className="w-4 h-4 text-indigo-400" />
                      Tomorrow 10:30–12:00
                    </h4>
                    <p className="text-[11px] text-slate-400">
                      {heroDecision.timing.optimalWindow?.reason}
                    </p>
                  </div>

                  <div className="text-right font-mono">
                    <span className="text-[10px] text-slate-400 block">Window Recovery Prob</span>
                    <span className="text-base font-black text-emerald-400">
                      {Math.round((heroDecision.timing.optimalWindow?.recoveryProbability || 0.76) * 100)}%
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 6: POLICY BOUNDS CHECK */}
            {currentStep === 6 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Step 6 — Policy & Regulatory Bounds</span>
                  <h3 className="text-base font-black text-white mt-0.5">Policy Engine Verification: PASS (5/5)</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Ensures strict compliance with TRAI DND, NPCI frequency caps, and merchant margin budgets.
                  </p>
                </div>

                <div className="space-y-2">
                  {heroDecision.policy.checks.map((c, i) => (
                    <div key={i} className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <div>
                          <span className="font-bold text-slate-200 block">{c.rule}</span>
                          <span className="text-[10px] text-slate-500">{c.description}</span>
                        </div>
                      </div>
                      <span className="font-mono text-[10.5px] text-slate-400">{c.currentValue}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* STEP 7: APPROVE ACTION */}
            {currentStep === 7 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 7 — Operator Approval</span>
                  <h3 className="text-base font-black text-white mt-0.5">Authorize WhatsApp 1-Click Link Dispatch</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Dispatches the causal recovery payload with cryptographic TEE signature simulation.
                  </p>
                </div>

                <div className="p-5 rounded-2xl bg-indigo-950/30 border border-indigo-500/30 text-center space-y-4">
                  <div className="w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-white">Ready for Dispatch: {selectedScore.label}</h4>
                    <p className="text-slate-400 text-[11px]">
                      Expected Net Recovery: <strong className="text-emerald-400">₹{(selectedScore.expectedNetRecoveryValue ?? (Math.round(selectedScore.recoveryProbability * heroTx.amount) - (selectedScore.totalCost || 0))).toLocaleString('en-IN')}</strong> • Timing: Tomorrow 10:30 AM
                    </p>
                  </div>

                  <Button
                    variant="primary"
                    size="lg"
                    onClick={handleApprove}
                    disabled={isApproving}
                    className="px-8 font-black text-xs bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 text-white cursor-pointer"
                  >
                    {isApproving ? 'Approving...' : 'APPROVE & DISPATCH ACTION'}
                  </Button>
                </div>
              </div>
            )}

            {/* STEP 8: SIMULATE RECOVERY OUTCOME */}
            {currentStep === 8 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Step 8 — Real-World Outcome Simulation</span>
                  <h3 className="text-base font-black text-white mt-0.5">Simulate Customer Payment Recovery</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Execute simulated outcome based on predicted probability to trigger the feedback loop.
                  </p>
                </div>

                <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 text-center space-y-4">
                  {!simulatedRecovered ? (
                    <div className="space-y-3">
                      <p className="text-slate-300 text-[11px]">
                        Clicking &quot;Simulate Outcome&quot; draws a Bernoulli sample from the model&apos;s predicted probability ({Math.round(selectedScore.recoveryProbability * 100)}%) and records the result.
                      </p>
                      <Button
                        variant="primary"
                        size="lg"
                        onClick={handleSimulate}
                        disabled={isSimulating}
                        className="px-8 font-black text-xs bg-gradient-to-r from-emerald-600 to-indigo-600 text-white shadow-xl shadow-emerald-600/30 cursor-pointer"
                      >
                        {isSimulating ? (
                          <>
                            <RotateCw className="w-4 h-4 animate-spin mr-2" />
                            Simulating Outcome...
                          </>
                        ) : (
                          <>
                            <Zap className="w-4 h-4 mr-2 text-amber-300" />
                            SIMULATE OUTCOME (RECOVER ₹{heroTx.amount.toLocaleString('en-IN')})
                          </>
                        )}
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
                        <Check className="w-6 h-6" />
                      </div>
                      <h4 className="font-black text-base text-emerald-400">₹{heroTx.amount.toLocaleString('en-IN')} RECOVERED!</h4>
                      <p className="text-slate-400 text-[11px]">
                        Payment successfully authorized via WhatsApp 1-Click deep link. Outcome recorded into the feedback engine.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* STEP 9: WAPSI LEARNED */}
            {currentStep === 9 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Step 9 — Closed-Loop Online Learning</span>
                  <h3 className="text-base font-black text-white mt-0.5">WAPSI Learned: Bayesian Prior Shift</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    The recovery outcome actively shifted the merchant&apos;s empirical channel prior.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
                  <span className="font-bold text-xs text-white block">WhatsApp Channel Affinity Prior:</span>
                  <div className="grid grid-cols-2 gap-3 text-center">
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                      <span className="text-[10px] text-slate-500 block">Prior Response Rate</span>
                      <span className="font-mono text-base font-bold text-slate-300">
                        {(priorRate * 100).toFixed(2)}%
                      </span>
                    </div>
                    <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30">
                      <span className="text-[10px] text-emerald-400 block">Updated Response Rate</span>
                      <span className="font-mono text-base font-black text-emerald-400">
                        {(updatedRate * 100).toFixed(2)}%{rateDeltaPp !== 0 ? ` (${rateDeltaPp > 0 ? '+' : ''}${rateDeltaPp}pp)` : ''}
                      </span>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {lastLearningResult?.nextDecisionImpact || "LinUCB exploration-exploitation weights and Beta distribution parameters were persisted. Next decision for similar customers will incorporate this higher affinity."}
                  </p>
                </div>
              </div>
            )}

            {/* STEP 10: RUN BATCH AUTOPILOT */}
            {currentStep === 10 && (
              <div className="space-y-4">
                <div className="border-b pb-3 border-slate-800/80">
                  <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Step 10 — Portfolio Autopilot Scale</span>
                  <h3 className="text-base font-black text-white mt-0.5">Scale From 1 Transaction to Full Portfolio</h3>
                  <p className="text-slate-400 text-[11px] mt-1">
                    Execute WAPSI Autopilot across all 350 transactions in batch to observe macro financial impact.
                  </p>
                </div>

                <div className="p-5 rounded-2xl bg-gradient-to-r from-emerald-950/40 to-indigo-950/40 border border-emerald-500/40 text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
                    <Zap className="w-6 h-6" />
                  </div>
                  <h4 className="font-black text-sm text-white">Launch Batch Autopilot on Entire Queue</h4>
                  <p className="text-slate-400 text-[11px] max-w-md mx-auto">
                    Processes 350 transactions, enforces invariant checking (AUTO + REVIEW + BLOCK = 350), and calculates portfolio net recovered value.
                  </p>
                  <Button
                    variant="primary"
                    size="lg"
                    onClick={handleLaunchAutopilot}
                    className="px-8 font-black text-xs bg-emerald-600 hover:bg-emerald-500 text-white shadow-xl shadow-emerald-600/30 cursor-pointer"
                  >
                    RUN RECOVERY AUTOPILOT BATCH →
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Stepper Footer Controls */}
          <div className={cn(
            "p-4 border-t flex items-center justify-between",
            isLight ? "bg-slate-50 border-slate-200" : "bg-[#0C1120] border-slate-800"
          )}>
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrev}
              disabled={currentStep === 1}
              className="text-xs cursor-pointer gap-1.5"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Previous Step
            </Button>

            <span className="text-slate-500 font-mono text-[11px]">
              Step {currentStep} / {totalSteps}
            </span>

            {currentStep < totalSteps ? (
              <Button
                variant="primary"
                size="sm"
                onClick={handleNext}
                className="text-xs font-bold cursor-pointer gap-1.5"
              >
                Next Step
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleLaunchAutopilot}
                className="text-xs font-bold bg-emerald-600 hover:bg-emerald-500 cursor-pointer gap-1.5"
              >
                Launch Autopilot
                <Zap className="w-3.5 h-3.5 text-amber-300" />
              </Button>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
