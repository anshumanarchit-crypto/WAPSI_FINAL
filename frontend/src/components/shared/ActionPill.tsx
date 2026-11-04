import React from 'react';
import { cn } from '../../lib/utils';
import { ActionType } from '../../types';
import { RotateCw, MessageCircle, Phone, Mail, Gift, ShieldAlert } from 'lucide-react';
import { useDemoStore } from '../../store/demoStore';

interface ActionPillProps {
  action: ActionType | string;
  label?: string;
  className?: string;
}

export const ActionPill: React.FC<ActionPillProps> = ({ action, label, className }) => {
  const theme = useDemoStore((state) => state.theme);

  const getActionConfig = (a: string) => {
    const isLight = theme === 'light';
    switch (a.toUpperCase()) {
      case 'RETRY':
        return {
          icon: <RotateCw className={cn("w-3 h-3", isLight ? "text-indigo-600" : "text-indigo-400")} />,
          style: isLight 
            ? 'bg-indigo-50 text-indigo-700 border-indigo-200 font-semibold' 
            : 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
          text: label || 'Retry',
        };
      case 'WHATSAPP':
        return {
          icon: <MessageCircle className={cn("w-3 h-3", isLight ? "text-emerald-600" : "text-emerald-400")} />,
          style: isLight 
            ? 'bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold' 
            : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
          text: label || 'WhatsApp Nudge',
        };
      case 'VOICE':
        return {
          icon: <Phone className={cn("w-3 h-3", isLight ? "text-cyan-600" : "text-cyan-400")} />,
          style: isLight 
            ? 'bg-cyan-50 text-cyan-800 border-cyan-200 font-semibold' 
            : 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
          text: label || 'Voice Call',
        };
      case 'EMAIL':
        return {
          icon: <Mail className={cn("w-3 h-3", isLight ? "text-blue-600" : "text-blue-400")} />,
          style: isLight 
            ? 'bg-blue-50 text-blue-800 border-blue-200 font-semibold' 
            : 'bg-blue-500/15 text-blue-300 border-blue-500/30',
          text: label || 'Email + Link',
        };
      case 'INCENTIVE':
        return {
          icon: <Gift className={cn("w-3 h-3", isLight ? "text-amber-600" : "text-amber-400")} />,
          style: isLight 
            ? 'bg-amber-50 text-amber-800 border-amber-200 font-semibold' 
            : 'bg-amber-500/15 text-amber-300 border-amber-500/30',
          text: label || 'Incentive Link',
        };
      case 'NO_ACTION':
        return {
          icon: <ShieldAlert className={cn("w-3 h-3", isLight ? "text-slate-600" : "text-slate-400")} />,
          style: isLight 
            ? 'bg-slate-100 text-slate-700 border-slate-300 font-semibold shadow-sm' 
            : 'bg-slate-800 text-slate-300 border-slate-700',
          text: label || 'No Action (Monitor)',
        };
      default:
        return {
          icon: null,
          style: isLight 
            ? 'bg-slate-100 text-slate-700 border-slate-300' 
            : 'bg-slate-800 text-slate-300 border-slate-700',
          text: label || action,
        };
    }
  };

  const config = getActionConfig(action);

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border transition-colors',
        config.style,
        className
      )}
    >
      {config.icon}
      <span>{config.text}</span>
    </span>
  );
};
