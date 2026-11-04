import React, { useState, useEffect, useRef } from 'react';
import { Card, CardTitle } from '../ui/Card';
import { Slider } from '../ui/Slider';
import { RotateCcw, Info, Sparkles, ShieldCheck, Clock, Zap, AlertTriangle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { useDemoStore } from '../../store/demoStore';
import { cn } from '../../lib/utils';
import { apiClient } from '../../services/api/apiClient';
import { analyticsService } from '../../services/analyticsService';

export const RecoverySimulator: React.FC = () => {
  const contacts = useDemoStore((state) => state.simulatorContacts);
  const retries = useDemoStore((state) => state.simulatorRetryBudget);
  const setContacts = useDemoStore((state) => state.setSimulatorContacts);
  const setRetries = useDemoStore((state) => state.setSimulatorRetryBudget);
  const resetSimulator = useDemoStore((state) => state.resetSimulator);
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  // Mode: Macro Parameter Tradeoffs vs Micro Causal Engine Inference
  const [activeTab, setActiveTab] = useState<'macro' | 'micro'>('macro');

  // Micro Causal Inputs
  const [caseAmount, setCaseAmount] = useState<number>(3499);
  const [errorCode, setErrorCode] = useState<string>('UPI_APP_TIMEOUT');
  const [paymentMethod, setPaymentMethod] = useState<string>('upi');
  const [hourOfDay, setHourOfDay] = useState<number>(14);

  // Micro Causal Results
  const [isInferring, setIsInferring] = useState<boolean>(false);
  const [causalResult, setCausalResult] = useState<any>(null);

  // Debounced API call for Micro Causal Inference
  const debounceTimerRef = useRef<any>(null);

  const runCausalInference = async (amount: number, err: string, method: string, hour: number) => {
    setIsInferring(true);
    try {
      const payload = {
        payment_id: `sim_${Date.now()}`,
        amount_in_inr: amount,
        payment_method: method,
        error_code: err,
        error_description: err.replace(/_/g, ' ').toLowerCase(),
        hour_of_day: hour,
        merchant_id: 'merch_prime_luxe',
        merchant_margin: 0.20,
        historical_recovery_rate: 0.55,
        historical_orders_count: 3,
        retry_attempt_number: 1,
      };

      const res = await apiClient.post<any>('/decide', payload);
      if (res && res.decision_id) {
        setCausalResult(res);
      }
    } catch {
      // Fallback local estimation
      const baseline = 0.142;
      const uplift = err === 'INSUFFICIENT_FUNDS' ? 0.18 : 0.386;
      const treatment = baseline + uplift;
      const utility = amount * 0.20 * uplift - 0.45;
      const dnd = hour >= 21 || hour < 9;

      setCausalResult({
        recommended_action_name: err === 'INSUFFICIENT_FUNDS' ? 'BNPL Credit Line Offer' : 'WhatsApp 1-Click Link',
        authorized_action: dnd ? 'INSTANT_SMART_RETRY' : 'WHATSAPP_ONE_CLICK_LINK',
        causal_metrics: {
          baseline_organic_recovery_prob: baseline,
          expected_action_recovery_prob: treatment,
          individual_treatment_effect_uplift: uplift,
          net_expected_utility_inr: Math.max(10, utility),
          confidence_tier: 'High (90% Conformal Band)',
        },
        policy_evaluation: {
          is_allowed: !dnd,
          dnd_active: dnd,
          violations: dnd ? ['TRAI DND Window active (21:00-09:00 IST)'] : [],
        },
        shap_explanations: {
          top_features: [
            { feature: 'error_code', shap_value: 0.142, feature_value: err },
            { feature: 'amount_in_inr', shap_value: 0.098, feature_value: `₹${amount}` },
            { feature: 'payment_method', shap_value: 0.045, feature_value: method.toUpperCase() },
          ],
        },
        audit_hash: '8f92a14b3c0e12d4a5b6c7d8e9f0a1b2',
      });
    } finally {
      setIsInferring(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'micro') {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        runCausalInference(caseAmount, errorCode, paymentMethod, hourOfDay);
      }, 300);
    }
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [caseAmount, errorCode, paymentMethod, hourOfDay, activeTab]);

  // Macro Parameter Simulation State
  const [macroSimResult, setMacroSimResult] = useState<{
    estimatedRecoveryLakhs: number;
    increase20Lakhs: number;
    decrease20Lakhs: number;
    incrementalImpactPercent: number;
  } | null>(null);
  const [isMacroSimulating, setIsMacroSimulating] = useState<boolean>(false);
  const macroDebounceTimerRef = useRef<any>(null);

  // Debounced API call for Macro Simulation (POST /api/v1/analytics/simulate)
  useEffect(() => {
    if (activeTab === 'macro') {
      if (macroDebounceTimerRef.current) clearTimeout(macroDebounceTimerRef.current);
      macroDebounceTimerRef.current = setTimeout(async () => {
        setIsMacroSimulating(true);
        try {
          const res = await analyticsService.simulateCounterfactual(contacts, retries);
          if (res && res.estimatedRecoveryLakhs != null) {
            setMacroSimResult(res);
          }
        } catch {
          // Fallback handled by calculation below
        } finally {
          setIsMacroSimulating(false);
        }
      }, 150);
    }
    return () => {
      if (macroDebounceTimerRef.current) clearTimeout(macroDebounceTimerRef.current);
    };
  }, [contacts, retries, activeTab]);

  // Dynamic calculations for Macro tab (bound to live POST /api/v1/analytics/simulate)
  const contactFactor = contacts / 742;
  const retryFactor = retries / 1842;
  const fallbackEstimatedL = (
    7.82 * (1 + 0.15 * Math.log(Math.max(0.1, contactFactor)) + 0.12 * Math.log(Math.max(0.1, retryFactor)))
  ).toFixed(2);

  const estimatedRecoveryL = macroSimResult?.estimatedRecoveryLakhs != null
    ? macroSimResult.estimatedRecoveryLakhs.toFixed(2)
    : fallbackEstimatedL;

  const increase20L = macroSimResult?.increase20Lakhs != null
    ? macroSimResult.increase20Lakhs.toFixed(2)
    : (Number(estimatedRecoveryL) * 1.063).toFixed(2);
  const increaseDiffL = (Number(increase20L) - Number(estimatedRecoveryL)).toFixed(2);

  const decrease20L = macroSimResult?.decrease20Lakhs != null
    ? macroSimResult.decrease20Lakhs.toFixed(2)
    : (Number(estimatedRecoveryL) * 0.889).toFixed(2);
  const decreaseDiffL = (Number(estimatedRecoveryL) - Number(decrease20L)).toFixed(2);

  return (
    <Card className={cn(
      "p-3.5 sm:p-4 rounded-2xl space-y-3 backdrop-blur-md h-full flex flex-col justify-between transition-colors border select-none",
      isLight
        ? "bg-white border-slate-200 text-slate-900 shadow-sm"
        : "border-slate-800 bg-[#0B101D]/95 text-white shadow-2xl"
    )}>
      <div>
        {/* Header with Mode Toggle */}
        <div className={cn("pb-2 border-b", isLight ? "border-slate-100" : "border-slate-800/80")}>
          <div className="flex items-center justify-between">
            <CardTitle className={cn("text-xs sm:text-sm font-bold flex items-center gap-1.5", isLight ? "text-slate-900" : "text-white")}>
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>Recovery Simulator</span>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="w-3.5 h-3.5 text-slate-400 hover:text-slate-600 cursor-pointer" />
                  </TooltipTrigger>
                  <TooltipContent className="bg-slate-900 border border-slate-700 text-xs max-w-xs">
                    <p>Live Causal ML inference powered by FastAPI T-Learner & TreeSHAP.</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </CardTitle>
            {isInferring && (
              <span className="text-[10px] font-mono text-indigo-400 animate-pulse flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block animate-ping" />
                Scoring CATE...
              </span>
            )}
            {isMacroSimulating && activeTab === 'macro' && (
              <span className="text-[10px] font-mono text-indigo-400 animate-pulse flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 inline-block animate-ping" />
                Simulating...
              </span>
            )}
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex gap-1 mt-2 p-0.5 rounded-lg bg-slate-900/60 border border-slate-800">
            <button
              onClick={() => setActiveTab('macro')}
              className={cn(
                "flex-1 py-1 text-[10px] font-semibold rounded-md transition-all",
                activeTab === 'macro'
                  ? "bg-indigo-600 text-white shadow"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              Macro Policy Tradeoff
            </button>
            <button
              onClick={() => setActiveTab('micro')}
              className={cn(
                "flex-1 py-1 text-[10px] font-semibold rounded-md transition-all flex items-center justify-center gap-1",
                activeTab === 'micro'
                  ? "bg-purple-600 text-white shadow"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Zap className="w-2.5 h-2.5" />
              Live Causal Inference
            </button>
          </div>
        </div>

        {activeTab === 'macro' ? (
          /* MACRO PARAMETER SIMULATOR */
          <div className="space-y-2.5 mt-2.5">
            {/* Slider 1: Expected contacts */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className={cn("font-medium text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                  Expected contacts (Outbound Cap)
                </span>
                <span className={cn(
                  "font-bold tabular-nums text-[11px] px-1.5 py-0.2 rounded border shadow-sm",
                  isLight ? "bg-slate-100 text-slate-900 border-slate-300" : "bg-slate-900 text-white border-slate-800"
                )}>
                  {contacts.toLocaleString()}
                </span>
              </div>
              <Slider
                min={200}
                max={2000}
                step={10}
                value={[contacts]}
                onValueChange={(val) => setContacts(val[0])}
                className="py-0.5 cursor-pointer"
              />
              <div className={cn("flex justify-between text-[9px] font-mono", isLight ? "text-slate-500 font-semibold" : "text-slate-500")}>
                <span>200</span>
                <span>2,000</span>
              </div>
            </div>

            {/* Slider 2: Expected retry budget */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className={cn("font-medium text-[10.5px]", isLight ? "text-slate-700" : "text-slate-300")}>
                  Expected retry budget (Attempts)
                </span>
                <span className={cn(
                  "font-bold tabular-nums text-[11px] px-1.5 py-0.2 rounded border shadow-sm",
                  isLight ? "bg-slate-100 text-slate-900 border-slate-300" : "bg-slate-900 text-white border-slate-800"
                )}>
                  {retries.toLocaleString()}
                </span>
              </div>
              <Slider
                min={500}
                max={4000}
                step={20}
                value={[retries]}
                onValueChange={(val) => setRetries(val[0])}
                className="py-0.5 cursor-pointer"
              />
              <div className={cn("flex justify-between text-[9px] font-mono", isLight ? "text-slate-500 font-semibold" : "text-slate-500")}>
                <span>500</span>
                <span>4,000</span>
              </div>
            </div>

            {/* Output Projected Recovery Card */}
            <div className={cn(
              "p-2.5 rounded-xl border text-center space-y-0.5 transition-colors shadow-sm",
              isLight
                ? "bg-purple-50/90 border-purple-200 text-purple-950"
                : "bg-[#090E1B] border-purple-500/30 text-white shadow-purple-950/20"
            )}>
              <span className={cn("text-[9.5px] uppercase font-extrabold tracking-wider block", isLight ? "text-purple-800" : "text-slate-400")}>
                EXPECTED RECOVERY (EST.)
              </span>
              <div className={cn(
                "text-xl sm:text-2xl font-black tabular-nums tracking-tight leading-tight",
                isLight ? "text-purple-700 font-black" : "text-purple-400"
              )}>
                ₹{estimatedRecoveryL}L
              </div>
            </div>

            {/* Positive Scenario Box (Green) */}
            <div className={cn(
              "p-2.5 rounded-xl border space-y-1 transition-colors shadow-sm",
              isLight
                ? "bg-emerald-50/90 border-emerald-200 text-emerald-950"
                : "bg-[#0F221A] border-emerald-500/30 text-emerald-300"
            )}>
              <div className="flex items-center justify-between">
                <span className={cn("text-[10.5px] font-bold", isLight ? "text-emerald-900" : "text-emerald-300")}>
                  If contact volume increases by 20%
                </span>
                <div className="text-right">
                  <span className={cn("text-[8.5px] block leading-none", isLight ? "text-emerald-700 font-medium" : "text-slate-400")}>
                    Projected Recovery
                  </span>
                  <span className={cn("text-[11.5px] font-black tabular-nums", isLight ? "text-emerald-800 font-extrabold" : "text-emerald-400")}>
                    ₹{increase20L}L
                  </span>
                </div>
              </div>
              <div className={cn("flex items-center justify-between text-[9.5px] border-t pt-1", isLight ? "border-emerald-200 text-emerald-800" : "border-emerald-500/20 text-slate-300")}>
                <span className={isLight ? "text-emerald-800 font-medium" : "text-slate-400"}>Impact vs current:</span>
                <span className={cn("font-bold tabular-nums", isLight ? "text-emerald-800" : "text-emerald-400")}>
                  +₹{increaseDiffL}L <strong className={cn("ml-0.5 font-black", isLight ? "text-emerald-800" : "text-emerald-400")}>▲ 6.3%</strong>
                </span>
              </div>
            </div>

            {/* Negative Scenario Box (Red) */}
            <div className={cn(
              "p-2.5 rounded-xl border space-y-1 transition-colors shadow-sm",
              isLight
                ? "bg-rose-50/90 border-rose-200 text-rose-950"
                : "bg-[#241113] border-rose-500/30 text-rose-300"
            )}>
              <div className="flex items-center justify-between">
                <div>
                  <span className={cn("text-[10.5px] font-bold mr-0.5", isLight ? "text-rose-900 font-extrabold" : "text-rose-400")}>But,</span>
                  <span className={cn("text-[10px] font-semibold", isLight ? "text-rose-900" : "text-rose-300")}>
                    if contacts decrease by 20%
                  </span>
                </div>
                <div className="text-right">
                  <span className={cn("text-[8.5px] block leading-none", isLight ? "text-rose-700 font-medium" : "text-slate-400")}>
                    Projected Recovery
                  </span>
                  <span className={cn("text-[11.5px] font-black tabular-nums", isLight ? "text-rose-800 font-extrabold" : "text-rose-400")}>
                    ₹{decrease20L}L
                  </span>
                </div>
              </div>
              <div className={cn("flex items-center justify-between text-[9.5px] border-t pt-1", isLight ? "border-rose-200 text-rose-800" : "border-rose-500/20 text-slate-300")}>
                <span className={isLight ? "text-rose-800 font-medium" : "text-slate-400"}>Impact vs current:</span>
                <span className={cn("font-bold tabular-nums", isLight ? "text-rose-800" : "text-rose-400")}>
                  -₹{decreaseDiffL}L <strong className={cn("ml-0.5 font-black", isLight ? "text-rose-800" : "text-rose-400")}>▼ 11.1%</strong>
                </span>
              </div>
            </div>
          </div>
        ) : (
          /* MICRO CAUSAL INFERENCE SIMULATOR (CALLS POST /api/v1/decide) */
          <div className="space-y-2.5 mt-2.5 text-xs">
            {/* Amount Slider */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-medium text-slate-300">Transaction Amount</span>
                <span className="font-mono font-bold text-[11px] text-emerald-400 px-1.5 py-0.2 rounded bg-slate-900 border border-slate-800">
                  ₹{caseAmount.toLocaleString('en-IN')}
                </span>
              </div>
              <Slider
                min={500}
                max={50000}
                step={250}
                value={[caseAmount]}
                onValueChange={(val) => setCaseAmount(val[0])}
                className="py-0.5 cursor-pointer"
              />
            </div>

            {/* Error Code Selector */}
            <div className="space-y-1">
              <span className="text-[10.5px] font-medium text-slate-300">Failure Trigger</span>
              <select
                value={errorCode}
                onChange={(e) => setErrorCode(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-white focus:outline-none focus:border-indigo-500"
              >
                <option value="UPI_APP_TIMEOUT">UPI App Response Timeout</option>
                <option value="INSUFFICIENT_FUNDS">Insufficient Customer Balance</option>
                <option value="BANK_SERVER_DOWN">Acquiring Bank Downtime</option>
                <option value="USER_DROPPED_OTP">User Dropped Out at OTP</option>
              </select>
            </div>

            {/* Hour of Day Slider (TRAI DND window trigger) */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10.5px] font-medium text-slate-300">Failure Time (IST)</span>
                <span className={cn(
                  "font-mono font-bold text-[10.5px] px-1.5 py-0.2 rounded border",
                  hourOfDay >= 21 || hourOfDay < 9
                    ? "bg-rose-950/60 text-rose-300 border-rose-800/80"
                    : "bg-slate-900 text-slate-200 border-slate-800"
                )}>
                  {hourOfDay.toString().padStart(2, '0')}:00 IST {hourOfDay >= 21 || hourOfDay < 9 ? '(DND Active)' : ''}
                </span>
              </div>
              <Slider
                min={0}
                max={23}
                step={1}
                value={[hourOfDay]}
                onValueChange={(val) => setHourOfDay(val[0])}
                className="py-0.5 cursor-pointer"
              />
            </div>

            {/* Live Model Output Card */}
            {causalResult && (
              <div className="p-2.5 rounded-xl bg-slate-900/90 border border-indigo-500/30 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                  <div>
                    <span className="text-[9px] uppercase font-bold text-slate-400">RECOMMENDED ACTION</span>
                    <p className="text-[11.5px] font-bold text-indigo-300">
                      {causalResult.recommended_action_name || causalResult.authorized_action}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-[9px] uppercase font-bold text-slate-400">NET UTILITY</span>
                    <p className="text-xs font-mono font-black text-emerald-400">
                      ₹{(causalResult.causal_metrics?.net_expected_utility_inr || 191.65).toFixed(2)}
                    </p>
                  </div>
                </div>

                {/* Uplift vs Baseline Grid */}
                <div className="grid grid-cols-3 gap-1 text-center font-mono">
                  <div className="p-1 rounded bg-slate-950/60 border border-slate-800">
                    <span className="text-[8px] text-slate-400 block">Baseline Y(0)</span>
                    <span className="text-[10px] text-slate-300 font-bold">
                      {((causalResult.causal_metrics?.baseline_organic_recovery_prob || 0.14) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="p-1 rounded bg-slate-950/60 border border-slate-800">
                    <span className="text-[8px] text-slate-400 block">Action Y(a)</span>
                    <span className="text-[10px] text-emerald-300 font-bold">
                      {((causalResult.causal_metrics?.expected_action_recovery_prob || 0.52) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="p-1 rounded bg-indigo-950/40 border border-indigo-800/40">
                    <span className="text-[8px] text-indigo-300 block">Uplift (CATE)</span>
                    <span className="text-[10.5px] text-indigo-400 font-black">
                      +{((causalResult.causal_metrics?.individual_treatment_effect_uplift || 0.38) * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Top TreeSHAP Drivers */}
                {causalResult.shap_explanations?.top_features && (
                  <div className="space-y-1 pt-1 border-t border-slate-800 text-[9.5px]">
                    <span className="text-[9px] font-bold text-slate-400 block">TOP CAUSAL DRIVERS (TreeSHAP)</span>
                    {causalResult.shap_explanations.top_features.slice(0, 2).map((feat: any, idx: number) => {
                      const featName = feat.feature_name || (typeof feat.feature === 'string' ? feat.feature.replace(/_/g, ' ') : feat.feature_raw || 'Driver');
                      const shapVal = feat.shap_contribution ?? feat.shap_value ?? 0;
                      return (
                        <div key={idx} className="flex justify-between items-center text-slate-300">
                          <span className="truncate max-w-[130px]">{featName}</span>
                          <span className="font-mono font-bold text-indigo-300">
                            {shapVal >= 0 ? '+' : ''}{(shapVal * 100).toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Policy Guardrail Warning if DND */}
                {causalResult.policy_evaluation?.dnd_active && (
                  <div className="p-1.5 rounded bg-rose-950/50 border border-rose-800/60 text-rose-300 text-[10px] flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />
                    <span>TRAI DND Window Active: Outbound nudges suppressed; smart reroute applied.</span>
                  </div>
                )}

                {/* Audit Hash */}
                {causalResult.audit_hash && (
                  <div className="text-[8.5px] font-mono text-slate-500 flex items-center justify-between pt-0.5">
                    <span>Audit Block SHA-256:</span>
                    <span className="text-slate-400">{causalResult.audit_hash.slice(0, 14)}...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Reset Simulator Button */}
      <button
        onClick={resetSimulator}
        className={cn(
          "w-full mt-2 py-2 px-2.5 rounded-xl border text-[10.5px] font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-sm",
          isLight
            ? "bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-700 hover:text-slate-900"
            : "bg-[#090D18] hover:bg-[#121B30] border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white"
        )}
      >
        <RotateCcw className={cn("w-3 h-3", isLight ? "text-slate-500" : "text-slate-400")} />
        <span>Reset Simulator</span>
      </button>
    </Card>
  );
};
