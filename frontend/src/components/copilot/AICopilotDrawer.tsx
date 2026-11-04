import React, { useState } from 'react';
import { 
  Sparkles, 
  X, 
  Send, 
  Bot, 
  User, 
  TrendingUp, 
  ShieldCheck, 
  Clock, 
  ArrowRight,
  RefreshCw
} from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';
import { Button } from '../ui/Button';
import { cn } from '../../lib/utils';

interface Message {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
  recommendations?: { title: string; action: string }[];
}

export const AICopilotDrawer: React.FC = () => {
  const isCopilotOpen = useDemoStore((state) => state.isCopilotOpen);
  const setCopilotOpen = useDemoStore((state) => state.setCopilotOpen);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'm1',
      sender: 'ai',
      text: 'Hello! I am your WAPSI Causal Copilot. I analyze incremental recovery probabilities, optimal intervention windows, and policy constraints to help maximize net recovered revenue. How can I assist you today?',
      timestamp: 'Just now',
    }
  ]);

  const presetQueries = [
    'Why is recovery falling for Checkout domain?',
    'Which high-value cases should we approve now?',
    'Explain why No Action was recommended for RX-48297',
    'What explains the +37.2% incremental uplift this week?',
  ];

  const handleSend = async (queryText?: string) => {
    const textToSend = queryText || input;
    if (!textToSend.trim()) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!queryText) setInput('');
    setIsTyping(true);

    await new Promise((r) => setTimeout(r, 650));

    let aiResponseText = '';
    let recommendations: { title: string; action: string }[] | undefined = undefined;

    if (textToSend.includes('Checkout')) {
      aiResponseText = `Checkout recovery is seeing a slight dip due to a 4.2% increase in issuer-side gateway timeouts during peak evening hours (8 PM - 10 PM IST). 

Causal model insight: Retrying immediately produces a negligible +2.4% uplift, but delaying retry to **T+14 hours (next morning 10:30 AM)** boosts incremental recovery probability from 42% to 68% (+26% uplift).`;
      recommendations = [
        { title: 'Schedule Batch Retries for 10:30 AM', action: 'Schedule' },
      ];
    } else if (textToSend.includes('approve') || textToSend.includes('high-value')) {
      aiResponseText = `Currently, there are **21 High-Impact cases** ready for execution with median confidence of 94%. 

Case **RX-48291 (₹8,999)** and Case **RX-48295 (₹6,500)** have optimal execution windows opening in the next 2 hours. Both cases have 5/5 policy approvals (NPCI attempt 2/4, TRAI budget 2/5).`;
      recommendations = [
        { title: 'Open Case RX-48291 in Queue', action: 'View Case' },
      ];
    } else if (textToSend.includes('RX-48297') || textToSend.includes('No Action')) {
      aiResponseText = `For Case **RX-48297 (Customer #6671, ₹3,499)**, the natural recovery probability ($P_0$) is already **61%**. 

Model evaluation:
- Natural Recovery ($P_0$): 61%
- Treatment with WhatsApp ($P_t$): 63%
- Incremental Uplift ($\\tau$): Only **+2.1%**

Since incremental uplift is below our configured merchant threshold (+5%), WAPSI chose **No Action** to save message costs and prevent customer fatigue.`;
    } else {
      aiResponseText = `Our Causal Uplift Engine generated **₹2.14L in true incremental recovery** this week (+37.2% vs baseline). 

Key drivers:
1. **Timing hazard optimization**: Executing retries during salary credit windows (1st-5th of month) yielded +25.7% uplift.
2. **Network Prior Signal**: 74% weight given to Razorpay network cross-merchant intelligence on HDFC and ICICI payment failures.
3. **Cannibalization Avoidance**: 385 cases were placed in No Action monitoring, saving ₹34,200 in communications.`;
    }

    const aiMsg: Message = {
      id: `ai-${Date.now()}`,
      sender: 'ai',
      text: aiResponseText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      recommendations,
    };

    setMessages((prev) => [...prev, aiMsg]);
    setIsTyping(false);
  };

  if (!isCopilotOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-[#0B0F19] border-l border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
              WAPSI AI Copilot
            </h2>
            <span className="text-[10px] text-emerald-400 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Causal Reasoning Active
            </span>
          </div>
        </div>
        <button
          onClick={() => setCopilotOpen(false)}
          className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Preset Queries */}
      <div className="p-3 border-b border-slate-800/80 bg-[#080B11]/60">
        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
          Suggested Inquiries
        </span>
        <div className="flex flex-wrap gap-1.5">
          {presetQueries.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(q)}
              className="text-left text-[11px] px-2.5 py-1.5 rounded-md bg-slate-900/90 border border-slate-800 text-slate-300 hover:border-indigo-500/50 hover:text-indigo-200 transition-all leading-tight"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={cn(
              'flex gap-2.5 max-w-[90%]',
              m.sender === 'user' ? 'ml-auto flex-row-reverse' : ''
            )}
          >
            <div
              className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs font-bold',
                m.sender === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gradient-to-tr from-purple-600 to-indigo-600 text-white shadow-sm'
              )}
            >
              {m.sender === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>
            <div
              className={cn(
                'p-3 rounded-xl text-xs space-y-1.5 shadow-sm leading-relaxed whitespace-pre-wrap',
                m.sender === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-none'
                  : 'bg-[#0F172A] border border-slate-800 text-slate-200 rounded-tl-none'
              )}
            >
              <p>{m.text}</p>
              {m.recommendations && (
                <div className="mt-2 pt-2 border-t border-slate-800 space-y-1">
                  {m.recommendations.map((rec, i) => (
                    <div
                      key={i}
                      className="p-2 rounded bg-indigo-950/40 border border-indigo-500/30 flex items-center justify-between text-[11px] text-indigo-200"
                    >
                      <span>{rec.title}</span>
                      <ArrowRight className="w-3 h-3 text-indigo-400" />
                    </div>
                  ))}
                </div>
              )}
              <span className="text-[9px] text-slate-400 block text-right pt-0.5">
                {m.timestamp}
              </span>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-2.5">
            <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-purple-600 to-indigo-600 text-white flex items-center justify-center shrink-0">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="p-3 rounded-xl bg-[#0F172A] border border-slate-800 text-xs text-slate-400 flex items-center gap-1.5">
              <RefreshCw className="w-3 h-3 animate-spin text-indigo-400" />
              <span>Analyzing causal model graph...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input Box */}
      <div className="p-3 border-t border-slate-800 bg-slate-900/80">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about recovery, policy, or uplift..."
            className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <Button type="submit" size="sm" variant="primary" disabled={!input.trim()}>
            <Send className="w-3.5 h-3.5" />
          </Button>
        </form>
      </div>
    </div>
  );
};
