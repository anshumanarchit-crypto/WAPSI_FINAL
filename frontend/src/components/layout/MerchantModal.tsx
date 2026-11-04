import React, { useState } from 'react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { 
  Building2, 
  X, 
  CheckCircle2, 
  Save, 
  ShieldCheck, 
  DollarSign, 
  Globe, 
  Mail, 
  MapPin, 
  Clock 
} from 'lucide-react';

export const MerchantModal: React.FC = () => {
  const isMerchantModalOpen = useDemoStore((state) => state.isMerchantModalOpen);
  const setMerchantModalOpen = useDemoStore((state) => state.setMerchantModalOpen);
  const merchantSettings = useDemoStore((state) => state.merchantSettings);
  const updateSettings = useDemoStore((state) => state.updateSettings);

  const [formData, setFormData] = useState(merchantSettings);

  if (!isMerchantModalOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateSettings(formData);
    setMerchantModalOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="bg-[#0F172A] border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="p-5 bg-[#0B0F19] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                Merchant Configuration & Identity
                <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  Verified Entity
                </span>
              </h2>
              <p className="text-xs text-slate-400">Modify live Acme Corp merchant profile and recovery thresholds</p>
            </div>
          </div>
          <button
            onClick={() => setMerchantModalOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Merchant / Business Name</label>
              <Input
                value={formData.merchantName}
                onChange={(e) => setFormData({ ...formData, merchantName: e.target.value })}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Merchant ID</label>
              <Input
                value={formData.merchantId}
                onChange={(e) => setFormData({ ...formData, merchantId: e.target.value })}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Business Type</label>
              <Input
                value={formData.businessType}
                onChange={(e) => setFormData({ ...formData, businessType: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Industry</label>
              <Input
                value={formData.industry}
                onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Website URL</label>
              <Input
                value={formData.website}
                onChange={(e) => setFormData({ ...formData, website: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Registered Billing Email</label>
              <Input
                type="email"
                value={formData.registeredEmail}
                onChange={(e) => setFormData({ ...formData, registeredEmail: e.target.value })}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Country</label>
              <Input
                value={formData.country}
                onChange={(e) => setFormData({ ...formData, country: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold">Timezone</label>
              <Input
                value={formData.timezone}
                onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
              />
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
            <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider block">
              Engine Threshold Parameters
            </span>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-slate-400 text-[11px] block">Confidence Threshold (%)</label>
                <Input
                  type="number"
                  value={formData.confidenceThreshold}
                  onChange={(e) => setFormData({ ...formData, confidenceThreshold: Number(e.target.value) })}
                />
              </div>
              <div>
                <label className="text-slate-400 text-[11px] block">Min Uplift (%)</label>
                <Input
                  type="number"
                  value={formData.minUpliftThreshold}
                  onChange={(e) => setFormData({ ...formData, minUpliftThreshold: Number(e.target.value) })}
                />
              </div>
              <div>
                <label className="text-slate-400 text-[11px] block">Retry Limit (Attempts)</label>
                <Input
                  type="number"
                  value={formData.retryAttemptLimit}
                  onChange={(e) => setFormData({ ...formData, retryAttemptLimit: Number(e.target.value) })}
                />
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setMerchantModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" className="gap-1.5">
              <Save className="w-4 h-4" />
              Save Merchant Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
