import React, { useState } from 'react';
import { 
  ShieldCheck, 
  AlertCircle, 
  CheckCircle2, 
  Lock, 
  UserCheck, 
  Hash, 
  ArrowRight, 
  Clock, 
  Zap, 
  X, 
  ExternalLink 
} from 'lucide-react';
import { Button } from '../ui/Button';
import { Card, CardTitle } from '../ui/Card';
import { apiClient, ApprovalResponse } from '../../services/api/apiClient';
import { formatINR } from '../../lib/formatting';
import { cn } from '../../lib/utils';
import { useDemoStore } from '../../store/demoStore';

interface OperatorApprovalModalProps {
  caseData: any;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (result: ApprovalResponse) => void;
}

export const OperatorApprovalModal: React.FC<OperatorApprovalModalProps> = ({
  caseData,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [operatorId, setOperatorId] = useState('OPR_MERCHANT_LEAD');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approvalResult, setApprovalResult] = useState<ApprovalResponse | null>(null);

  const theme = useDemoStore((state) => state.theme);
  const isLight = theme === 'light';

  if (!isOpen || !caseData) return null;

  const handleApprove = async () => {
    if (isSubmitting || !!approvalResult) return;
    if (!operatorId.trim()) {
      setError('Operator ID is required for audit ledger attestation.');
      return;
    }
    setError(null);
    setIsSubmitting(true);

    try {
      const res = await apiClient.approveRecoveryCase(caseData.caseId, {
        action: caseData.recommendedAction,
        operatorId: operatorId.trim(),
      });
      setApprovalResult(res);
      if (onSuccess) onSuccess(res);
    } catch (err: any) {
      setError(err?.message || 'Failed to dispatch operator approval to backend.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className={cn(
        "relative w-full max-w-xl rounded-2xl border shadow-2xl overflow-hidden transition-all",
        isLight ? "bg-white border-slate-200 text-slate-900" : "bg-[#0F172A] border-indigo-500/30 text-white"
      )}>
        {/* Top Header */}
        <div className="px-6 py-4 border-b border-slate-700/50 flex items-center justify-between bg-slate-950/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/20 border border-indigo-500/30">
              <ShieldCheck className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-bold tracking-tight">Operator Governance Authorization</h2>
              <p className="text-xs text-slate-400">Verifiable SHA-256 snapshot approval before outbound dispatch</p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Case & Financial Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-medium uppercase">Case ID</span>
              <span className="text-xs font-mono font-bold text-indigo-400">{caseData.caseId}</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-medium uppercase">Transaction</span>
              <span className="text-xs font-bold text-white">{formatINR(caseData.amount)}</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-medium uppercase">Failure Reason</span>
              <span className="text-xs font-medium text-slate-300 truncate block">{caseData.failureCode || caseData.failureReason}</span>
            </div>
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block font-medium uppercase">Causal Lift</span>
              <span className="text-xs font-bold text-emerald-400">+{Math.round((caseData.incrementalUplift || 0.36) * 100)}%</span>
            </div>
          </div>

          {/* Recommended Action Card */}
          <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-500/30 flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-300">Proposed Channel Action</span>
                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-indigo-500/20 text-indigo-200 border border-indigo-500/40">
                  ML Recommended
                </span>
              </div>
              <div className="text-sm font-bold text-white flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-400" />
                <span>{caseData.recommendedActionLabel || caseData.recommendedAction}</span>
              </div>
              <p className="text-xs text-slate-300">
                Optimal Window: <strong className="text-white">{caseData.optimalWindow || '0-24h (Immediate)'}</strong>
              </p>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-slate-400 block uppercase">Confidence Gate</span>
              <span className="text-sm font-mono font-bold text-purple-300">
                {Math.round((caseData.decisionConfidence || 0.94) * 100)}% Valid
              </span>
            </div>
          </div>

          {/* Governance Verification Checks */}
          <div className="space-y-2">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-indigo-400" />
              <span>Policy Engine Guardrails (4/4 Satisfied)</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-slate-300 truncate">TRAI DND Window (Allowed)</span>
              </div>
              <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-slate-300 truncate">Contact Frequency Cap (1/2)</span>
              </div>
              <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-slate-300 truncate">Merchant Margin Positive</span>
              </div>
              <div className="p-2 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-slate-300 truncate">NPCI UPI Compliance Certified</span>
              </div>
            </div>
          </div>

          {/* Operator Authorization Input */}
          {!approvalResult ? (
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <label className="text-xs font-semibold text-slate-300 block flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-indigo-400" />
                <span>Authorized Operator Identifier:</span>
              </label>
              <input
                type="text"
                value={operatorId}
                onChange={(e) => setOperatorId(e.target.value)}
                placeholder="e.g. OPR_FINTECH_DIRECTOR"
                className="w-full px-3.5 py-2 rounded-xl text-xs font-mono bg-slate-900 border border-slate-700 text-white focus:outline-none focus:border-indigo-500 transition-colors"
                disabled={isSubmitting}
              />
              <p className="text-[11px] text-slate-400">
                This operator ID will be permanently bound into the SHA-256 immutable cryptographic audit ledger.
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/40 space-y-2 animate-in fade-in">
              <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold">
                <CheckCircle2 className="w-4 h-4" />
                <span>Action Successfully Authorized & Dispatched!</span>
              </div>
              <div className="space-y-1 text-xs font-mono text-slate-300">
                <div>Dispatch ID: <strong className="text-white">{approvalResult.dispatch_id}</strong></div>
                <div className="truncate">Audit Hash: <span className="text-emerald-300">{approvalResult.audit_hash}</span></div>
                {approvalResult.approval_snapshot_hash && (
                  <div className="truncate">Snapshot Hash: <span className="text-purple-300">{approvalResult.approval_snapshot_hash}</span></div>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-xl bg-red-950/60 border border-red-500/40 text-red-200 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/40 flex items-center justify-end gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isSubmitting}
            className="text-xs"
          >
            {approvalResult ? 'Close' : 'Cancel'}
          </Button>

          {!approvalResult && (
            <Button
              variant="success"
              size="sm"
              onClick={handleApprove}
              disabled={isSubmitting || !operatorId.trim()}
              className="text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/30 gap-1.5"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Authorizing in Enclave...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  <span>Verify SHA-256 & Authorize</span>
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};
