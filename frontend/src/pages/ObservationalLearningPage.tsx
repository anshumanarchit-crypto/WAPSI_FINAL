import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  BrainCircuit, 
  Database, 
  Download, 
  ShieldCheck, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  FileSpreadsheet, 
  Lock, 
  Calendar, 
  Filter, 
  ArrowDownToLine, 
  Sparkles,
  Layers,
  Cpu
} from 'lucide-react';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { WapsiBrandedHeader } from '../components/shared/WapsiBrandedHeader';
import { apiClient, ObservationalMetricsResponse, ObservationalExportResponse } from '../services/api/apiClient';
import { useDemoStore } from '../store/demoStore';
import { cn } from '../lib/utils';

export const ObservationalLearningPage: React.FC = () => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const [merchantId, setMerchantId] = useState('04a2aaf8-8c8a-4d99-852c-cefc80e82019');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [eligibleOnly, setEligibleOnly] = useState(true);
  const [exportLimit, setExportLimit] = useState(100);

  // 1. Fetch live metrics from Gate 5 endpoint
  const { 
    data: metricsData, 
    isLoading: isMetricsLoading, 
    refetch: refetchMetrics 
  } = useQuery({
    queryKey: ['observationalMetrics', merchantId],
    queryFn: () => apiClient.getObservationalMetrics(merchantId),
    refetchInterval: 15000,
  });

  // 2. State for export data
  const [exportData, setExportData] = useState<ObservationalExportResponse | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleFetchExport = async () => {
    setIsExporting(true);
    setExportError(null);
    try {
      const res = await apiClient.exportObservationalData({
        merchantId,
        eligibleOnly,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        limit: exportLimit,
      });
      setExportData(res);
    } catch (err: any) {
      setExportError(err?.message || 'Failed to export observational dataset');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDownloadJsonl = () => {
    if (!exportData || !exportData.records || exportData.records.length === 0) return;
    const jsonlContent = exportData.records.map((r) => JSON.stringify(r)).join('\n');
    const blob = new Blob([jsonlContent], { type: 'application/x-jsonlines' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `wapsi_retraining_dataset_${merchantId.slice(0, 8)}_${Date.now()}.jsonl`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const metrics = metricsData?.metrics || {
    total_observations: 0,
    mature_observations: 0,
    eligible_dml_records: 0,
    eligible_bandit_records: 0,
    invalid_propensity_records: 0,
    action_distribution: {},
    propensity_summary: {},
    overlap_violation_rate: 0.0,
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 pb-12">
      <Topbar title="Observational Feedback & Retraining Pipeline" />

      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {/* Branded Header Banner */}
        <WapsiBrandedHeader 
          title="Causal Observational Intelligence & Retraining Pipeline"
          subtitle="Real-Time Contextual Decision Logging, Verified Settlement Outcome Ingestion & Offline DML Pipeline (Gate 5)"
        />

        {/* Top Operational Telemetry Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">Logged Contexts</span>
            <div className="text-xl font-bold font-mono text-white mt-1">
              {metrics.total_observations.toLocaleString()}
            </div>
            <span className="text-[10px] text-slate-400 mt-0.5 block">Total decision records</span>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">Mature Outcomes</span>
            <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
              {metrics.mature_observations.toLocaleString()}
            </div>
            <span className="text-[10px] text-emerald-400/80 mt-0.5 block">Settlement reconciled</span>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">DML Eligible</span>
            <div className="text-xl font-bold font-mono text-indigo-400 mt-1">
              {metrics.eligible_dml_records.toLocaleString()}
            </div>
            <span className="text-[10px] text-indigo-300/80 mt-0.5 block">Neyman-orthogonal valid</span>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">Bandit Updates</span>
            <div className="text-xl font-bold font-mono text-purple-400 mt-1">
              {metrics.eligible_bandit_records.toLocaleString()}
            </div>
            <span className="text-[10px] text-purple-300/80 mt-0.5 block">LinUCB online updates</span>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">Overlap Bound</span>
            <div className="text-xl font-bold font-mono text-cyan-400 mt-1">
              {Math.max(0, 100 - metrics.overlap_violation_rate * 100).toFixed(1)}%
            </div>
            <span className="text-[10px] text-cyan-300/80 mt-0.5 block">Positivity common support</span>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
            <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">Invalid Propensity</span>
            <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
              {metrics.invalid_propensity_records}
            </div>
            <span className="text-[10px] text-emerald-400/80 mt-0.5 block">0 bounds violations</span>
          </Card>
        </div>

        {/* Section 2: Mathematical Foundation & Architecture */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/90 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <BrainCircuit className="w-4 h-4 text-indigo-400" />
                <CardTitle className="text-sm font-bold text-white">Closed-Loop Bandit Adaptation</CardTitle>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                Sherman-Morrison Rank-1
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              When a verified Razorpay settlement or case expiration webhook arrives, WAPSI&apos;s closed-loop engine dynamically retrieves the original decision context X_i and computes the deterministic business reward: R_i = margin &times; amount_recovered &minus; cost.
            </p>

            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 font-mono text-[11px] text-indigo-200 space-y-1.5">
              <div>// Online Policy Covariance & Reward Accumulation:</div>
              <div className="text-emerald-400">A_a ← A_a + x_i · x_i^T</div>
              <div className="text-purple-400">b_a ← b_a + r_i · x_i</div>
              <div className="text-slate-400">// Symmetrized: A_a = 0.5 * (A_a + A_a^T)</div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-slate-300">Duplicate settlement idempotency</span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-slate-300">Late payments gracefully corrected</span>
              </div>
            </div>
          </Card>

          <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/90 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <CardTitle className="text-sm font-bold text-white">DML Retraining Data Contract</CardTitle>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                PII-Excluded Safe
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Exported observational datasets strictly conform to <code className="text-purple-300">wapsi.causal.dml.MultiActionDoubleMachineLearning</code> standards. All post-treatment variables (<code className="text-slate-400">y_*, tau_*</code>) are filtered to guarantee Neyman orthogonality and prevent treatment leakage.
            </p>

            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 font-mono text-[11px] text-slate-300 space-y-1">
              <div><strong className="text-indigo-300">Numerical features:</strong> amount, attempts_used, prior_recovery_rate, hour, fatigue_score</div>
              <div><strong className="text-purple-300">Categorical features:</strong> domain, decline_reason, issuer, bin_bucket</div>
              <div><strong className="text-emerald-300">Treatment & Outcome:</strong> treatment taxonomy, binary recovered (0/1)</div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                <Lock className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="text-slate-300">Customer PII strictly stripped</span>
              </div>
              <div className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="text-slate-300">Strict multi-tenant isolation</span>
              </div>
            </div>
          </Card>
        </div>

        {/* Section 3: Retraining Dataset Exporter Tool */}
        <Card className="p-6 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-5 shadow-2xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-indigo-400" />
                <CardTitle className="text-base font-bold text-white">Retraining Dataset Query & Exporter</CardTitle>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Generate authenticated JSONL training samples for offline causal model calibration
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchMetrics()}
                disabled={isMetricsLoading}
                className="text-xs gap-1.5"
              >
                <RefreshCw className={cn("w-3.5 h-3.5", isMetricsLoading && "animate-spin")} />
                <span>Refresh Metrics</span>
              </Button>
            </div>
          </div>

          {/* Form Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs">
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-400">Tenant / Merchant UUID</label>
              <input 
                type="text" 
                value={merchantId}
                onChange={(e) => setMerchantId(e.target.value)}
                placeholder="04a2aaf8-8c8a..."
                className="w-full px-3 py-2 rounded-xl font-mono text-xs bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-400">Start Date (ISO / YYYY-MM-DD)</label>
              <input 
                type="text" 
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                placeholder="2026-11-01"
                className="w-full px-3 py-2 rounded-xl font-mono text-xs bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-400">End Date (ISO / YYYY-MM-DD)</label>
              <input 
                type="text" 
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                placeholder="2026-11-04"
                className="w-full px-3 py-2 rounded-xl font-mono text-xs bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-400">Max Samples</label>
              <select
                value={exportLimit}
                onChange={(e) => setExportLimit(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl text-xs bg-slate-950 border border-slate-800 text-white focus:outline-none focus:border-indigo-500"
              >
                <option value={50}>50 records</option>
                <option value={100}>100 records</option>
                <option value={500}>500 records</option>
                <option value={1000}>1,000 records</option>
              </select>
            </div>

            <div className="flex items-end gap-2">
              <Button
                variant="primary"
                size="sm"
                onClick={handleFetchExport}
                disabled={isExporting || !merchantId}
                className="w-full text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white py-2.5 rounded-xl shadow-lg shadow-indigo-600/30 gap-1.5"
              >
                {isExporting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Querying...</span>
                  </>
                ) : (
                  <>
                    <ArrowDownToLine className="w-3.5 h-3.5" />
                    <span>Execute Export Query</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {exportError && (
            <div className="p-3.5 rounded-xl bg-red-950/60 border border-red-500/40 text-red-200 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{exportError}</span>
            </div>
          )}

          {/* Export Results Preview */}
          {exportData && (
            <div className="space-y-3 pt-3 border-t border-slate-800 animate-in fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white">
                    Found {exportData.record_count} Verified Records for Merchant {merchantId.slice(0, 8)}...
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    DML Formatted
                  </span>
                </div>

                {exportData.records.length > 0 && (
                  <Button
                    variant="success"
                    size="sm"
                    onClick={handleDownloadJsonl}
                    className="text-xs font-bold gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download Dataset (.jsonl)</span>
                  </Button>
                )}
              </div>

              {exportData.records.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-400 rounded-xl bg-slate-950/80 border border-slate-800">
                  Zero mature observational records found for the specified filters. When payment failure cases are decided and verified via webhooks, they will appear here.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] font-semibold border-b border-slate-800">
                      <tr>
                        <th className="py-2 px-3">Case ID</th>
                        <th className="py-2 px-3">Domain</th>
                        <th className="py-2 px-3">Amount</th>
                        <th className="py-2 px-3">Decline Code</th>
                        <th className="py-2 px-3">Treatment</th>
                        <th className="py-2 px-3">Propensity (p̂)</th>
                        <th className="py-2 px-3">Recovered</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800 bg-slate-900/40 font-mono text-[11px]">
                      {exportData.records.slice(0, 8).map((r, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/50">
                          <td className="py-2 px-3 text-indigo-300 font-bold">{r.case_id}</td>
                          <td className="py-2 px-3 text-slate-300">{r.domain}</td>
                          <td className="py-2 px-3 text-white">₹{r.amount}</td>
                          <td className="py-2 px-3 text-slate-400">{r.decline_reason}</td>
                          <td className="py-2 px-3 text-purple-300">{r.treatment}</td>
                          <td className="py-2 px-3 text-emerald-300">{r.assigned_propensity ? r.assigned_propensity.toFixed(3) : 'N/A'}</td>
                          <td className="py-2 px-3">
                            <span className={cn(
                              "px-2 py-0.5 rounded text-[10px] font-bold",
                              r.recovered === 1 ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-400"
                            )}>
                              {r.recovered === 1 ? 'RECOVERED' : 'EXPIRED'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </Card>
      </main>
    </div>
  );
};
