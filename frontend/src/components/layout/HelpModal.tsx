import React from 'react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { 
  HelpCircle, 
  X, 
  BookOpen, 
  BrainCircuit, 
  ShieldCheck, 
  Zap, 
  ExternalLink,
  MessageCircleQuestion
} from 'lucide-react';

export const HelpModal: React.FC = () => {
  const isHelpModalOpen = useDemoStore((state) => state.isHelpModalOpen);
  const setHelpModalOpen = useDemoStore((state) => state.setHelpModalOpen);

  if (!isHelpModalOpen) return null;

  const faqs = [
    {
      q: 'What is the difference between Natural Recovery (P₀) and Treatment Recovery (Pt)?',
      a: 'Natural Recovery is the probability that a customer pays on their own without any intervention. Treatment Recovery is the probability when contacted. Incremental Uplift (τ = Pt - P₀) measures only the additional value caused by WAPSI.',
    },
    {
      q: 'How does No Action protect customer trust and reduce costs?',
      a: 'When Natural Recovery is already high (e.g. 61%) and treatment gives minimal marginal lift (+2%), sending notifications annoys users and wastes messaging budgets. WAPSI automatically monitors rather than pesters.',
    },
    {
      q: 'How does the Hazard Timing curve work?',
      a: 'Different failure types and banks have specific optimal retry windows (e.g. salary crediting, overnight batch clearing). WAPSI identifies the exact peak hour (e.g. 18h) for highest issuer authorization rates.',
    },
    {
      q: 'What regulatory policies are strictly enforced?',
      a: 'WAPSI validates every execution against NPCI Mandate limits (max 4 attempts), TRAI contact budgets (max 5 communications/month), and demographic fairness constraints in a simulated TEE boundary.',
    }
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
      <div className="bg-[#0F172A] border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="p-5 bg-[#0B0F19] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                WAPSI Help & Documentation Center
              </h2>
              <p className="text-xs text-slate-400">Causal AI Revenue Recovery Guide & FAQs</p>
            </div>
          </div>
          <button
            onClick={() => setHelpModalOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto text-xs">
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 space-y-1">
              <BrainCircuit className="w-4 h-4 text-indigo-400" />
              <span className="font-bold text-white block">Causal Uplift</span>
              <p className="text-[11px] text-slate-400">Predicts who pays because we act.</p>
            </div>
            <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 space-y-1">
              <Zap className="w-4 h-4 text-emerald-400" />
              <span className="font-bold text-white block">Optimal Timing</span>
              <p className="text-[11px] text-slate-400">Peaks retry during issuer recovery hours.</p>
            </div>
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span className="font-bold text-white block">Zero Breach Policy</span>
              <p className="text-[11px] text-slate-400">Enforces NPCI & TRAI caps 100%.</p>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider block">
              Frequently Asked Questions
            </span>
            {faqs.map((faq, idx) => (
              <div key={idx} className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                <span className="font-semibold text-white flex items-start gap-2">
                  <MessageCircleQuestion className="w-3.5 h-3.5 text-indigo-400 mt-0.5 shrink-0" />
                  {faq.q}
                </span>
                <p className="text-[11px] text-slate-400 pl-5 leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0B0F19] border-t border-slate-800 flex justify-end">
          <Button variant="primary" size="sm" onClick={() => setHelpModalOpen(false)}>
            Got it, thanks!
          </Button>
        </div>
      </div>
    </div>
  );
};
