import React from 'react';

interface RadialScoreGaugeProps {
  score: number;
  maxScore?: number;
  label?: string;
  sublabel?: string;
  size?: number;
  strokeWidth?: number;
  color?: 'emerald' | 'indigo' | 'amber' | 'cyan' | string;
}

export const RadialScoreGauge: React.FC<RadialScoreGaugeProps> = ({
  score,
  maxScore = 100,
  label = 'Health Score',
  sublabel,
  size = 84,
  strokeWidth = 7,
  color = 'emerald',
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(Math.max(score / maxScore, 0), 1);
  const strokeDashoffset = circumference - progress * circumference;

  const colorPresets: Record<string, { track: string; strokeStart: string; strokeEnd: string; glow: string }> = {
    emerald: {
      track: '#064E3B',
      strokeStart: '#34D399',
      strokeEnd: '#059669',
      glow: 'rgba(16,185,129,0.4)',
    },
    cyan: {
      track: '#164E63',
      strokeStart: '#38BDF8',
      strokeEnd: '#0284C7',
      glow: 'rgba(14,165,233,0.4)',
    },
    indigo: {
      track: '#1E1B4B',
      strokeStart: '#818CF8',
      strokeEnd: '#4F46E5',
      glow: 'rgba(99,102,241,0.4)',
    },
    amber: {
      track: '#78350F',
      strokeStart: '#FBBF24',
      strokeEnd: '#D97706',
      glow: 'rgba(245,158,11,0.4)',
    },
  };

  const colorConfig = colorPresets[color] || colorPresets.emerald;

  return (
    <div
      className="relative flex flex-col items-center justify-center shrink-0 select-none"
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="transform -rotate-90"
        style={{ filter: `drop-shadow(0 0 8px ${colorConfig.glow})` }}
      >
        <defs>
          <linearGradient id={`gaugeGradient-${color}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={colorConfig.strokeStart} />
            <stop offset="100%" stopColor={colorConfig.strokeEnd} />
          </linearGradient>
        </defs>

        {/* Background Track (Image 1 style) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={colorConfig.track}
          strokeWidth={strokeWidth}
          fill="none"
          strokeOpacity={0.8}
        />

        {/* Active Animated Value Stroke */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={`url(#gaugeGradient-${color})`}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>

      {/* Center Display: 95 + Health Score */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-2xl font-black text-white leading-none tracking-tight">
          {score}
        </span>
        {label && (
          <span className="text-[8px] font-medium text-slate-300 mt-1 leading-tight">
            {label}
          </span>
        )}
      </div>
    </div>
  );
};
