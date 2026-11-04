import React from 'react';

export const RecoveryHeroArtwork: React.FC = () => {
  return (
    <div className="relative w-[340px] h-[140px] hidden lg:flex items-center justify-center shrink-0 select-none">
      {/* Outer Orbiting Neon Glowing Rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[300px] h-[75px] rounded-full border border-indigo-500/30 blur-[1px] transform -rotate-12" />
        <div className="w-[260px] h-[60px] rounded-full border border-purple-500/40 blur-[1px] transform -rotate-12 shadow-[0_0_20px_rgba(99,102,241,0.3)]" />
      </div>

      {/* Left Small Floating Fintech Card */}
      <div className="absolute left-0 top-7 w-24 h-16 rounded-xl bg-[#0F172A]/90 border border-indigo-500/40 p-2 shadow-2xl backdrop-blur-md transform -rotate-12 z-10">
        <div className="w-3.5 h-3.5 rounded-full bg-cyan-400/20 border border-cyan-400/40 flex items-center justify-center">
          <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
        </div>
        <div className="mt-2 space-y-1">
          <div className="w-12 h-1 bg-slate-700 rounded" />
          <div className="w-8 h-1 bg-indigo-400/60 rounded" />
        </div>
      </div>

      {/* Main Central 3D Glowing Glass Tablet with Chart & Bars */}
      <div className="relative w-48 h-28 rounded-2xl bg-gradient-to-b from-[#1E1B4B]/95 via-[#0F172A]/95 to-[#0B0F19]/95 border border-indigo-400/50 p-3 shadow-2xl shadow-indigo-950/80 backdrop-blur-xl z-20 flex flex-col justify-between transform -rotate-2">
        {/* Tablet Top Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
            <span className="text-[8px] font-bold text-indigo-200 tracking-wider">WAPSI</span>
          </div>
          <div className="flex gap-0.5">
            <div className="w-1 h-1 rounded-full bg-slate-500" />
            <div className="w-1 h-1 rounded-full bg-slate-500" />
          </div>
        </div>

        {/* Purple Glowing Area Chart with Peaks & Bars */}
        <div className="relative h-14 w-full flex items-end">
          <svg viewBox="0 0 100 45" className="w-full h-full overflow-visible">
            <defs>
              <linearGradient id="heroGraphGlow" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0" />
              </linearGradient>
            </defs>
            {/* Background vertical histogram bars */}
            <rect x="10" y="30" width="3" height="15" fill="#312E81" rx="1" />
            <rect x="20" y="24" width="3" height="21" fill="#3730A3" rx="1" />
            <rect x="30" y="16" width="3" height="29" fill="#4338CA" rx="1" />
            <rect x="40" y="28" width="3" height="17" fill="#3730A3" rx="1" />
            <rect x="50" y="12" width="3" height="33" fill="#4F46E5" rx="1" />
            <rect x="60" y="22" width="3" height="23" fill="#4338CA" rx="1" />
            <rect x="70" y="18" width="3" height="27" fill="#6366F1" rx="1" />
            <rect x="80" y="8" width="3" height="37" fill="#818CF8" rx="1" />

            {/* Glowing Area Fill */}
            <path
              d="M 5 38 Q 20 22 35 28 T 55 10 T 75 20 T 95 6 L 95 45 L 5 45 Z"
              fill="url(#heroGraphGlow)"
            />
            {/* Glowing Neon Line */}
            <path
              d="M 5 38 Q 20 22 35 28 T 55 10 T 75 20 T 95 6"
              fill="none"
              stroke="#A855F7"
              strokeWidth="2"
              className="drop-shadow-[0_0_6px_#A855F7]"
            />
            {/* End glowing point */}
            <circle cx="95" cy="6" r="2.5" fill="#FFFFFF" stroke="#C084FC" strokeWidth="1.5" />
          </svg>
        </div>
      </div>

      {/* Floating 3D Rupee Coin with Glowing Neon Halo */}
      <div className="absolute right-12 bottom-1 z-30 flex items-center justify-center">
        <div className="w-12 h-12 rounded-full bg-gradient-to-tr from-indigo-950 via-slate-900 to-purple-900 border-2 border-purple-400/80 shadow-[0_0_20px_rgba(168,85,247,0.6)] flex items-center justify-center transform rotate-6 hover:scale-110 transition-transform">
          <span className="text-base font-black text-purple-200 drop-shadow-[0_0_6px_rgba(255,255,255,0.8)]">
            ₹
          </span>
        </div>
      </div>

      {/* Right Floating Card */}
      <div className="absolute right-0 top-10 w-24 h-16 rounded-xl bg-[#0F172A]/90 border border-purple-500/40 p-2 shadow-2xl backdrop-blur-md transform rotate-12 z-10">
        <div className="flex items-center justify-between">
          <div className="w-2.5 h-1 rounded bg-purple-400" />
          <div className="w-1 h-1 rounded-full bg-emerald-400" />
        </div>
        <div className="mt-3 space-y-1">
          <div className="w-full h-1 bg-slate-800 rounded" />
          <div className="w-2/3 h-1 bg-purple-400/60 rounded" />
        </div>
      </div>
    </div>
  );
};
