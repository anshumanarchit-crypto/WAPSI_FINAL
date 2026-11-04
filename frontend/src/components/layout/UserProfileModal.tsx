import React, { useState } from 'react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { 
  User, 
  X, 
  ShieldCheck, 
  Key, 
  LogOut, 
  Save, 
  CheckCircle2, 
  Smartphone,
  Copy
} from 'lucide-react';

export const UserProfileModal: React.FC = () => {
  const isUserProfileModalOpen = useDemoStore((state) => state.isUserProfileModalOpen);
  const setUserProfileModalOpen = useDemoStore((state) => state.setUserProfileModalOpen);
  const userProfile = useDemoStore((state) => state.userProfile);
  const updateUserProfile = useDemoStore((state) => state.updateUserProfile);

  const [formData, setFormData] = useState(userProfile);
  const [copiedKey, setCopiedKey] = useState(false);

  if (!isUserProfileModalOpen) return null;

  const handleCopyKey = () => {
    navigator.clipboard?.writeText(userProfile.apiKey);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    updateUserProfile(formData);
    setUserProfileModalOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="bg-[#0F172A] border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="p-5 bg-[#0B0F19] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-600 to-purple-600 border border-indigo-400/40 flex items-center justify-center font-black text-sm text-white shadow-md">
              {formData.avatar}
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                {formData.name}
                <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  Active
                </span>
              </h2>
              <p className="text-xs text-indigo-300">{formData.role}</p>
            </div>
          </div>
          <button
            onClick={() => setUserProfileModalOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSave} className="p-5 space-y-4 text-xs">
          <div className="space-y-3">
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Full Name</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Email Address</label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-slate-300 font-semibold block mb-1">Operator Role</label>
              <Input
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                required
              />
            </div>
          </div>

          {/* Security & API Key */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-indigo-400" />
                Merchant API Live Secret
              </span>
              <button
                type="button"
                onClick={handleCopyKey}
                className="text-[10px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
              >
                <Copy className="w-3 h-3" />
                {copiedKey ? 'Copied!' : 'Copy API Key'}
              </button>
            </div>
            <div className="font-mono text-[11px] text-slate-400 bg-slate-900 px-2.5 py-1.5 rounded border border-slate-800 truncate">
              {formData.apiKey}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-1">
              <Smartphone className="w-3.5 h-3.5 text-emerald-400" />
              <span>Two-Factor Authentication (MFA): <strong className="text-emerald-400">Enabled</strong></span>
            </div>
          </div>

          <div className="text-[10px] text-slate-500">
            Last logged in: {formData.lastLogin}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => setUserProfileModalOpen(false)}
              className="text-xs"
            >
              <LogOut className="w-3.5 h-3.5 mr-1" />
              Sign Out
            </Button>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setUserProfileModalOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" className="gap-1.5">
                <Save className="w-3.5 h-3.5" />
                Save Profile
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
