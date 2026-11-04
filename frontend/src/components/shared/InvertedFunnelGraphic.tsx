import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface FunnelBand {
  id: string;
  name: string;
  count: string;
  rate: string;
  description: string;
}

export const InvertedFunnelGraphic: React.FC = () => {
  const [hoveredBand, setHoveredBand] = useState<FunnelBand | null>(null);

  const bands: Record<string, FunnelBand> = {
    detected: { id: 'detected', name: '1. Detected', count: '12,842 cases', rate: '100% Entry', description: 'Failed payments detected via webhooks' },
    scored: { id: 'scored', name: '2. Scored', count: '8,931 cases', rate: '69.5% Evaluated', description: 'Causal uplift & hazard survival evaluated' },
    ready: { id: 'ready', name: '3. Ready', count: '4,231 cases', rate: '47.4% Payoff', description: 'Scheduled for optimal issuer recovery window' },
    actioned: { id: 'actioned', name: '4. Actioned', count: '2,104 cases', rate: '49.7% Dispatched', description: 'Executed via Smart Retry, WhatsApp or Voice' },
    recovered: { id: 'recovered', name: '5. Recovered', count: '1,842 cases', rate: '42.4% Overall Conv.', description: 'Payment captured and settled successfully' },
  };

  return (
    <div className="relative w-28 h-44 flex flex-col items-center justify-center shrink-0">
      {/* Floating Hover Tooltip */}
      <AnimatePresence>
        {hoveredBand && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 5 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 5 }}
            transition={{ duration: 0.15 }}
            className="absolute -top-12 z-30 pointer-events-none whitespace-nowrap bg-slate-900 border border-indigo-500/50 rounded-xl px-3 py-1.5 shadow-2xl shadow-indigo-950/80 text-center"
          >
            <span className="text-[11px] font-bold text-white block">{hoveredBand.name}: <strong className="text-indigo-300">{hoveredBand.count}</strong></span>
            <span className="text-[9px] text-emerald-400 font-semibold">{hoveredBand.rate} • {hoveredBand.description}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <svg
        viewBox="0 0 100 150"
        className="w-full h-full drop-shadow-[0_0_15px_rgba(99,102,241,0.35)] cursor-pointer"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="funnel1" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#7C3AED" />
            <stop offset="100%" stopColor="#6366F1" />
          </linearGradient>
          <linearGradient id="funnel2" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#6366F1" />
            <stop offset="100%" stopColor="#4F46E5" />
          </linearGradient>
          <linearGradient id="funnel3" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#3B82F6" />
            <stop offset="100%" stopColor="#2563EB" />
          </linearGradient>
          <linearGradient id="funnel4" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0EA5E9" />
            <stop offset="100%" stopColor="#0284C7" />
          </linearGradient>
          <linearGradient id="funnelSpout" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#6D28D9" />
          </linearGradient>
        </defs>

        {/* Level 1: Detected (Top wide trapezoid) */}
        <polygon
          points="5,5 95,5 82,32 18,32"
          fill="url(#funnel1)"
          stroke={hoveredBand?.id === 'detected' ? '#FFFFFF' : '#1E1B4B'}
          strokeWidth={hoveredBand?.id === 'detected' ? 2 : 1}
          className="transition-all duration-200 hover:brightness-125"
          onMouseEnter={() => setHoveredBand(bands.detected)}
          onMouseLeave={() => setHoveredBand(null)}
        />

        {/* Level 2: Scored */}
        <polygon
          points="18,34 82,34 71,62 29,62"
          fill="url(#funnel2)"
          stroke={hoveredBand?.id === 'scored' ? '#FFFFFF' : '#1E1B4B'}
          strokeWidth={hoveredBand?.id === 'scored' ? 2 : 1}
          className="transition-all duration-200 hover:brightness-125"
          onMouseEnter={() => setHoveredBand(bands.scored)}
          onMouseLeave={() => setHoveredBand(null)}
        />

        {/* Level 3: Ready */}
        <polygon
          points="29,64 71,64 61,92 39,92"
          fill="url(#funnel3)"
          stroke={hoveredBand?.id === 'ready' ? '#FFFFFF' : '#1E1B4B'}
          strokeWidth={hoveredBand?.id === 'ready' ? 2 : 1}
          className="transition-all duration-200 hover:brightness-125"
          onMouseEnter={() => setHoveredBand(bands.ready)}
          onMouseLeave={() => setHoveredBand(null)}
        />

        {/* Level 4: Actioned */}
        <polygon
          points="39,94 61,94 54,118 46,118"
          fill="url(#funnel4)"
          stroke={hoveredBand?.id === 'actioned' ? '#FFFFFF' : '#1E1B4B'}
          strokeWidth={hoveredBand?.id === 'actioned' ? 2 : 1}
          className="transition-all duration-200 hover:brightness-125"
          onMouseEnter={() => setHoveredBand(bands.actioned)}
          onMouseLeave={() => setHoveredBand(null)}
        />

        {/* Level 5: Recovered (Bottom box spout with arrow) */}
        <g
          className="transition-all duration-200 hover:brightness-125"
          onMouseEnter={() => setHoveredBand(bands.recovered)}
          onMouseLeave={() => setHoveredBand(null)}
        >
          <rect
            x="26"
            y="120"
            width="48"
            height="18"
            rx="4"
            fill="url(#funnelSpout)"
            stroke={hoveredBand?.id === 'recovered' ? '#FFFFFF' : '#A78BFA'}
            strokeWidth={hoveredBand?.id === 'recovered' ? 2 : 1.5}
          />
          <polygon points="50,146 44,138 56,138" fill="#8B5CF6" />
        </g>
      </svg>
    </div>
  );
};
