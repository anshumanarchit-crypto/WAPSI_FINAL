import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  Cpu, 
  Activity, 
  Layers, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Clock, 
  ShieldCheck, 
  Server, 
  Lock, 
  Zap,
  RotateCw,
  Send,
  CheckCircle,
  XCircle,
  HelpCircle
} from 'lucide-react';
import { Topbar } from '../components/layout/Topbar';
import { Card, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { WapsiBrandedHeader } from '../components/shared/WapsiBrandedHeader';
import { apiClient, WorkerHealthResponse, IntegrationsStatusResponse } from '../services/api/apiClient';
import { useDemoStore } from '../store/demoStore';
import { cn } from '../lib/utils';

export const WorkerOperationsPage: React.FC = () => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  const [pollingInterval, setPollingInterval] = useState<number>(10000);

  // 1. Fetch live worker health from Gate 4 endpoint
  const { 
    data: workerHealth, 
    isLoading: isWorkerLoading, 
    refetch: refetchWorker 
  } = useQuery({
    queryKey: ['workerHealth'],
    queryFn: () => apiClient.getWorkerHealth(),
    refetchInterval: pollingInterval,
  });

  // 2. Fetch live integration status for database dialect
  const { data: integrations } = useQuery({
    queryKey: ['integrationsStatus'],
    queryFn: () => apiClient.getIntegrationsStatus(),
    refetchInterval: 30000,
  });

  const outbox = workerHealth?.outbox || {
    PENDING_APPROVAL: 0,
    QUEUED: workerHealth?.queue_depth || 0,
    SENDING: workerHealth?.active_leases || 0,
    SENT: 0,
    RETRY: 0,
    DEAD_LETTER: 0,
    RECONCILIATION_REQUIRED: 0,
    CANCELLED: 0,
    REJECTED: 0,
    TOTAL: workerHealth?.queue_depth || 0,
  };

  const statusTiles = [
    { label: 'Pending Approval', count: outbox.PENDING_APPROVAL, color: 'text-amber-400', border: 'border-amber-500/30', bg: 'bg-amber-950/20', desc: 'Awaiting human-in-the-loop authorization' },
    { label: 'Queued for Dispatch', count: outbox.QUEUED, color: 'text-indigo-400', border: 'border-indigo-500/30', bg: 'bg-indigo-950/20', desc: 'Ready for atomic worker claim' },
    { label: 'Active Leases (Sending)', count: outbox.SENDING, color: 'text-cyan-400', border: 'border-cyan-500/30', bg: 'bg-cyan-950/20', desc: 'Locked by worker daemon' },
    { label: 'Delivered (Sent)', count: outbox.SENT, color: 'text-emerald-400', border: 'border-emerald-500/30', bg: 'bg-emerald-950/20', desc: 'Outbound dispatch successful' },
    { label: 'Backoff Retrying', count: outbox.RETRY, color: 'text-yellow-400', border: 'border-yellow-500/30', bg: 'bg-yellow-950/20', desc: 'Exponential backoff with jitter' },
    { label: 'Dead Letter Queue', count: outbox.DEAD_LETTER, color: 'text-rose-400', border: 'border-rose-500/30', bg: 'bg-rose-950/20', desc: 'Permanent exhaustion / non-retryable' },
    { label: 'Reconciliation Needed', count: outbox.RECONCILIATION_REQUIRED, color: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-950/20', desc: 'Ambiguous provider network state' },
    { label: 'Operator Suppressed', count: outbox.REJECTED + outbox.CANCELLED, color: 'text-slate-400', border: 'border-slate-700', bg: 'bg-slate-900/40', desc: 'Manual suppression or opt-out' },
  ];

  return (
    <div className="flex-1 flex flex-col min-w-0 pb-12">
      <Topbar title="Recovery Worker Operations & Outbox Daemon" />

      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {/* Branded Header Banner */}
        <WapsiBrandedHeader 
          title="Background Worker Daemon & Transactional Outbox"
          subtitle="Durable Outbox Queueing, Worker Leases, Atomicity Guarantees & Provider Dispatch Engine (Gate 4)"
        />

        {/* Top Worker Status Strip */}
        <Card className="p-5 rounded-2xl border border-slate-800 bg-[#0B101D]/95 space-y-4 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                <Server className="w-6 h-6 text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base font-bold text-white">Recovery Background Worker Daemon</CardTitle>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    {workerHealth?.status || 'HEALTHY'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Daemon Engine: <strong className="text-white font-mono">{workerHealth?.worker?.worker_id || 'worker_daemon_primary'}</strong> | 
                  Lease Duration: <strong className="text-white font-mono">{workerHealth?.worker?.lease_duration_seconds || 60}s</strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={pollingInterval}
                onChange={(e) => setPollingInterval(Number(e.target.value))}
                className="text-xs bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1.5 text-slate-300 focus:outline-none"
              >
                <option value={5000}>Auto-refresh: 5s</option>
                <option value={10000}>Auto-refresh: 10s</option>
                <option value={30000}>Auto-refresh: 30s</option>
              </select>

              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchWorker()}
                disabled={isWorkerLoading}
                className="text-xs gap-1.5"
              >
                <RefreshCw className={cn("w-3.5 h-3.5", isWorkerLoading && "animate-spin")} />
                <span>Refresh</span>
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-medium">Claim Concurrency</span>
              <div className="text-sm font-bold text-white font-mono mt-0.5">SKIP LOCKED</div>
              <span className="text-[10px] text-emerald-400/90 mt-0.5 block">Zero duplicate dispatches</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-medium">Database Dialect</span>
              <div className="text-sm font-bold text-white font-mono mt-0.5 uppercase">{integrations?.database?.dialect || 'PostgreSQL'}</div>
              <span className="text-[10px] text-blue-400/90 mt-0.5 block">{integrations?.database?.latency_ms || 119}ms query roundtrip</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-medium">Active Worker Leases</span>
              <div className="text-sm font-bold text-cyan-400 font-mono mt-0.5">{workerHealth?.active_leases || 0} claimed</div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Auto-reclaimed on crash</span>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-medium">Outbox Queue Depth</span>
              <div className="text-sm font-bold text-indigo-400 font-mono mt-0.5">{workerHealth?.queue_depth || 0} pending</div>
              <span className="text-[10px] text-slate-400 mt-0.5 block">Scheduled & eligible</span>
            </div>
          </div>
        </Card>

        {/* Outbox Status Grid */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              <span>Transactional Outbox Partition Breakdown</span>
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              Last Heartbeat: {workerHealth?.timestamp_utc ? new Date(workerHealth.timestamp_utc).toLocaleTimeString() : 'Active'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {statusTiles.map((tile) => (
              <Card 
                key={tile.label} 
                className={cn(
                  "p-4 rounded-xl border transition-all duration-200 shadow-md",
                  tile.border,
                  tile.bg
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-300">{tile.label}</span>
                  <span className={cn("text-xl font-bold font-mono", tile.color)}>
                    {tile.count}
                  </span>
                </div>
                <p className="text-[10.5px] text-slate-400 mt-2 leading-relaxed">
                  {tile.desc}
                </p>
              </Card>
            ))}
          </div>
        </div>

        {/* Architectural Guarantees */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="p-4 rounded-xl border border-slate-800 bg-[#0B101D]/90 space-y-2">
            <div className="flex items-center gap-2 text-indigo-400 text-xs font-bold">
              <Lock className="w-4 h-4" />
              <span>Dialect-Appropriate Atomicity</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Under PostgreSQL, jobs are claimed using atomic <code className="text-indigo-300">SELECT ... FOR UPDATE SKIP LOCKED</code> transactions, guaranteeing zero worker collision. Under SQLite test isolation, exclusive <code className="text-indigo-300">BEGIN IMMEDIATE</code> locks are enforced.
            </p>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-[#0B101D]/90 space-y-2">
            <div className="flex items-center gap-2 text-purple-400 text-xs font-bold">
              <ShieldCheck className="w-4 h-4" />
              <span>Approval Snapshot Verification</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Prior to external API dispatch over WhatsApp Cloud API or Razorpay, the worker verifies that the recipient and message payload match the exact SHA-256 snapshot registered at operator approval time.
            </p>
          </Card>

          <Card className="p-4 rounded-xl border border-slate-800 bg-[#0B101D]/90 space-y-2">
            <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold">
              <Zap className="w-4 h-4" />
              <span>Idempotent External Providers</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              Every Razorpay Payment Link and Meta WhatsApp template nudge is generated with an immutable idempotency key (<code className="text-emerald-300">idemp_...</code>). Provider HTTP 429 Retry-After headers are honored with bounded exponential backoff.
            </p>
          </Card>
        </div>
      </main>
    </div>
  );
};
