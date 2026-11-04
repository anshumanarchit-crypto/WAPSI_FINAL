import React from 'react';
import { motion } from 'framer-motion';

interface MiniBarChartProps {
  data?: number[];
  color?: 'rose' | 'amber' | 'emerald' | 'purple' | 'cyan';
  className?: string;
}

export const MiniBarChart: React.FC<MiniBarChartProps> = ({
  data = [30, 45, 60, 75, 90, 100],
  color = 'purple',
  className = '',
}) => {
  const maxVal = Math.max(...data, 1);

  const getBarColor = () => {
    switch (color) {
      case 'rose':
        return 'bg-gradient-to-t from-rose-600 to-rose-400 shadow-rose-500/30';
      case 'amber':
        return 'bg-gradient-to-t from-amber-600 to-amber-400 shadow-amber-500/30';
      case 'emerald':
        return 'bg-gradient-to-t from-emerald-600 to-emerald-400 shadow-emerald-500/30';
      case 'cyan':
        return 'bg-gradient-to-t from-cyan-600 to-cyan-400 shadow-cyan-500/30';
      default:
        return 'bg-gradient-to-t from-indigo-600 to-purple-400 shadow-indigo-500/30';
    }
  };

  return (
    <div className={`flex items-end justify-end gap-1.5 h-10 w-20 shrink-0 ${className}`}>
      {data.map((val, idx) => {
        const heightPercent = Math.max(18, (val / maxVal) * 100);
        return (
          <div
            key={idx}
            className="w-2 bg-slate-800/80 rounded-t-sm overflow-hidden flex flex-col justify-end h-full"
          >
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${heightPercent}%` }}
              transition={{ duration: 0.6, delay: idx * 0.08, ease: 'easeOut' }}
              className={`w-full rounded-t-sm shadow-sm ${getBarColor()}`}
            />
          </div>
        );
      })}
    </div>
  );
};
