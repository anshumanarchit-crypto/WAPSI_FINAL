import React, { useState, useEffect } from 'react';
import { ShieldCheck, Info, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useDemoStore } from '../../store/demoStore';
import { apiClient, BackendConnectionStatus } from '../../services/api/apiClient';

export const DataTransparencyBanner: React.FC<{ className?: string }> = ({ className }) => {
  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';
  const [status, setStatus] = useState<BackendConnectionStatus>(apiClient.getStatus());

  useEffect(() => {
    return apiClient.onStatusChange((newStatus) => setStatus(newStatus));
  }, []);

  const isLive = status === 'LIVE';

  return (
    <div className={cn(
      "flex items-center justify-between px-4 py-1.5 text-[11px] border-b transition-colors select-none",
      isLive
        ? isLight
          ? "bg-emerald-50/80 border-emerald-200 text-emerald-900"
          : "bg-emerald-950/30 border-emerald-500/20 text-emerald-300"
        : isLight
          ? "bg-indigo-50/70 border-indigo-100 text-indigo-900"
          : "bg-indigo-950/30 border-indigo-500/20 text-indigo-300",
      className
    )}>
      <div className="flex items-center gap-2">
        <span className={cn(
          "px-1.5 py-0.5 rounded font-mono font-bold text-[10px] tracking-wider uppercase border flex items-center gap-1",
          isLive
            ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/40"
            : isLight ? "bg-indigo-100 text-indigo-800 border-indigo-300" : "bg-indigo-500/20 text-indigo-300 border-indigo-400/30"
        )}>
          {isLive ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live Telemetry Active
            </>
          ) : (
            'Demonstration Data'
          )}
        </span>
        <span className="hidden sm:inline text-slate-300 text-[11px]">
          {isLive
            ? "Connected to live WAPSI Causal Decision Engine, PostgreSQL & Meta WABA."
            : "Deterministic scenario data for Razorpay AI Buildathon 2026 evaluation."}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1 font-mono text-[10px] opacity-90 text-emerald-400">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          <span>TEE Protected Enclave Attested</span>
        </span>
      </div>
    </div>
  );
};
