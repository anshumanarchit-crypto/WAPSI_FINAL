import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Target,
  BrainCircuit,
  FileSpreadsheet,
  BarChart3,
  ShieldCheck,
  Users,
  HelpCircle,
  Settings,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Building2
} from 'lucide-react';
import { CyberBrainIcon } from '../shared/CyberBrainIcon';
import { useDemoStore } from '../../store/demoStore';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { WapsiLogo } from '../shared/WapsiLogo';
import { cn } from '../../lib/utils';

export const Sidebar: React.FC = () => {
  const isSidebarCollapsed = useDemoStore((state) => state.isSidebarCollapsed);
  const toggleSidebar = useDemoStore((state) => state.toggleSidebar);
  const toggleCopilot = useDemoStore((state) => state.toggleCopilot);
  const setMerchantModalOpen = useDemoStore((state) => state.setMerchantModalOpen);
  const setUserManagementModalOpen = useDemoStore((state) => state.setUserManagementModalOpen);
  const setHelpModalOpen = useDemoStore((state) => state.setHelpModalOpen);
  const merchantSettings = useDemoStore((state) => state.merchantSettings);
  const cases = useDemoStore((state) => state.cases);
  const dynamicCaseCount = cases.length;

  const navItems = [
    { name: 'Overview', path: '/overview', icon: LayoutDashboard, tooltip: 'Operational pulse & recovery metrics' },
    { name: 'Recovery Center', path: '/recovery-center', icon: Target, tooltip: 'Causal mission control queue & drawer', badge: String(dynamicCaseCount) },
    { name: 'AI Decisions', path: '/ai-decisions', icon: (props: any) => <CyberBrainIcon className={props.className || "w-4 h-4"} />, tooltip: 'Uplift models, timing hazard & network priors' },
    { name: 'Recovery Cases', path: '/recovery-cases', icon: FileSpreadsheet, tooltip: 'Full audit ledger of all transaction attempts' },
    { name: 'Observational ML', path: '/observational-learning', icon: BrainCircuit, tooltip: 'Gate 5 DML logging, propensity & retraining dataset export' },
    { name: 'Worker Operations', path: '/worker-operations', icon: Building2, tooltip: 'Gate 4 worker daemon health, outbox leases & queues' },
    { name: 'Analytics', path: '/analytics', icon: BarChart3, tooltip: 'Causal impact, baseline comparison & simulator' },
    { name: 'Governance', path: '/governance', icon: ShieldCheck, tooltip: 'Policy controls, audit trail & fairness' },
    { name: 'User Management', action: () => setUserManagementModalOpen(true), icon: Users, tooltip: 'Team roles, operator invites & access permissions' },
    { name: 'Help & Docs', action: () => setHelpModalOpen(true), icon: HelpCircle, tooltip: 'Causal AI documentation, guides & FAQs' },
    { name: 'Settings', path: '/settings', icon: Settings, tooltip: 'Engine thresholds, channels & merchant settings' },
  ];

  const renderNavButton = (item: typeof navItems[0]) => {
    const Icon = item.icon;

    if (item.action) {
      const buttonContent = (
        <button
          onClick={item.action}
          className={cn(
            'group relative w-full flex items-center rounded-xl text-xs font-medium border border-transparent transition-all duration-200',
            'text-slate-400 hover:text-slate-100 hover:bg-slate-800/70 hover:border-slate-700/50 hover:shadow-sm',
            isSidebarCollapsed ? 'justify-center h-10 px-0' : 'gap-3 px-3 py-2.5'
          )}
        >
          <Icon className="w-4 h-4 text-slate-400 group-hover:text-indigo-400 group-hover:scale-110 shrink-0 transition-all duration-200" />
          {!isSidebarCollapsed && (
            <span className="truncate group-hover:translate-x-0.5 transition-transform duration-200">
              {item.name}
            </span>
          )}
        </button>
      );

      if (isSidebarCollapsed) {
        return (
          <Tooltip key={item.name}>
            <TooltipTrigger asChild>{buttonContent}</TooltipTrigger>
            <TooltipContent side="right" className="bg-slate-900/95 border border-slate-700/80 backdrop-blur-md text-xs shadow-xl">
              <p className="font-semibold text-white">{item.name}</p>
              <p className="text-[11px] text-slate-400">{item.tooltip}</p>
            </TooltipContent>
          </Tooltip>
        );
      }
      return <div key={item.name}>{buttonContent}</div>;
    }

    const linkContent = (
      <NavLink
        to={item.path!}
        className={({ isActive }) =>
          cn(
            'group relative w-full flex items-center rounded-xl text-xs font-medium border transition-all duration-200',
            isSidebarCollapsed ? 'justify-center h-10 px-0' : 'justify-between px-3 py-2.5',
            isActive
              ? 'bg-gradient-to-r from-indigo-600 via-indigo-600 to-indigo-700 text-white font-semibold border-indigo-400/40 shadow-md shadow-indigo-600/30'
              : 'text-slate-400 border-transparent hover:text-white hover:bg-slate-800/70 hover:border-slate-700/50 hover:shadow-sm'
          )
        }
      >
        {({ isActive }) => (
          <>
            {/* Active Left Indicator Bar */}
            {isActive && !isSidebarCollapsed && (
              <span className="absolute -left-[3px] top-2 bottom-2 w-1 rounded-r-full bg-white/90 shadow-[0_0_8px_rgba(255,255,255,0.8)]" />
            )}

            <div className={cn('flex items-center gap-3 min-w-0', isSidebarCollapsed ? 'justify-center' : '')}>
              <Icon
                className={cn(
                  'w-4 h-4 shrink-0 transition-all duration-200',
                  isActive
                    ? 'text-white drop-shadow-[0_0_6px_rgba(255,255,255,0.6)]'
                    : 'text-slate-400 group-hover:text-indigo-400 group-hover:scale-110'
                )}
              />
              {!isSidebarCollapsed && (
                <span className={cn('truncate transition-transform duration-200', !isActive && 'group-hover:translate-x-0.5')}>
                  {item.name}
                </span>
              )}
            </div>

            {/* Optional Badge or Status */}
            {!isSidebarCollapsed && item.badge && (
              <span
                className={cn(
                  'text-[10px] font-bold px-1.5 py-0.5 rounded-md tracking-wider transition-colors',
                  isActive
                    ? 'bg-white/20 text-white'
                    : 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 group-hover:bg-indigo-500/25'
                )}
              >
                {item.badge}
              </span>
            )}
          </>
        )}
      </NavLink>
    );

    if (isSidebarCollapsed) {
      return (
        <Tooltip key={item.name}>
          <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
          <TooltipContent side="right" className="bg-slate-900/95 border border-slate-700/80 backdrop-blur-md text-xs shadow-xl">
            <p className="font-semibold text-white">{item.name}</p>
            <p className="text-[11px] text-slate-400">{item.tooltip}</p>
          </TooltipContent>
        </Tooltip>
      );
    }

    return <div key={item.name}>{linkContent}</div>;
  };

  return (
    <>
      {/* Mobile Backdrop when sidebar is expanded on small screens */}
      {!isSidebarCollapsed && (
        <div
          onClick={toggleSidebar}
          className="fixed inset-0 bg-black/75 backdrop-blur-xs z-35 md:hidden"
        />
      )}
      <aside
        className={cn(
          'bg-[#080D1A] border-r border-slate-800/80 flex flex-col h-screen fixed left-0 top-0 z-40 select-none transition-all duration-300',
          isSidebarCollapsed
            ? 'w-20 -translate-x-full md:translate-x-0'
            : 'w-64 translate-x-0 shadow-2xl md:shadow-none'
        )}
      >
        {/* Brand Header with Exact WAPSI Constellation Logo */}
        <div className={cn(
          'h-16 px-4 flex items-center border-b border-slate-800/80',
          isSidebarCollapsed ? 'justify-center relative' : 'justify-between'
        )}>
          <div className="flex items-center gap-3">
            <WapsiLogo size={32} />
            {!isSidebarCollapsed && (
              <div className="flex flex-col min-w-0">
                <span className="font-extrabold text-base tracking-wider text-white flex items-center gap-1.5 truncate">
                  WAPSI
                </span>
                <span className="text-[9px] uppercase font-bold tracking-widest text-indigo-400 truncate">
                  AI RECOVERY ENGINE
                </span>
              </div>
            )}
          </div>

          {/* Collapse Toggle Button */}
          <button
            onClick={toggleSidebar}
            className={cn(
              'p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/80 border border-transparent hover:border-slate-700 transition-all duration-200',
              isSidebarCollapsed ? 'absolute -right-3 top-5 bg-[#0B111E] border border-slate-700 shadow-md p-1' : ''
            )}
            title={isSidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {isSidebarCollapsed ? (
              <ChevronRight className="w-3.5 h-3.5 text-indigo-400" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Navigation Links - Perfect vertical alignment */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1.5">
          <TooltipProvider delayDuration={100}>
            {navItems.map((item) => renderNavButton(item))}
          </TooltipProvider>
        </div>

        {/* Bottom Section */}
        <div className="p-3 space-y-2 border-t border-slate-800/80 bg-[#080D1A]">
          {/* Engine Status Widget */}
          {!isSidebarCollapsed ? (
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-slate-900/90 to-emerald-950/20 border border-slate-800/90 hover:border-emerald-500/30 transition-colors">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-[11px] font-bold text-slate-200">Engine Status</span>
                <span className="ml-auto text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                  Operational
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-1 pl-4">All systems running smoothly</p>
            </div>
          ) : (
            <div className="flex justify-center py-1">
              <span className="relative flex h-2.5 w-2.5" title="Operational">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
            </div>
          )}

          {/* Ask WAPSI AI Button */}
          <button
            onClick={toggleCopilot}
            className={cn(
              'w-full rounded-xl bg-gradient-to-r from-indigo-950/90 via-purple-950/80 to-indigo-950/90 hover:from-indigo-900 hover:to-purple-900 border border-indigo-500/30 hover:border-indigo-400/60 text-left transition-all duration-200 group shadow-md shadow-indigo-950/40',
              isSidebarCollapsed ? 'flex justify-center p-2.5' : 'p-2.5'
            )}
            title="Ask WAPSI AI Copilot"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded-lg bg-indigo-500/20 text-indigo-400 group-hover:scale-110 transition-transform">
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
                {!isSidebarCollapsed && (
                  <span className="text-xs font-bold text-indigo-200 group-hover:text-white transition-colors">
                    Ask WAPSI AI
                  </span>
                )}
              </div>
              {!isSidebarCollapsed && (
                <span className="text-indigo-400 group-hover:translate-x-1 transition-transform text-xs font-semibold">
                  →
                </span>
              )}
            </div>
            {!isSidebarCollapsed && (
              <p className="text-[10px] text-slate-400 mt-1">Get intelligent causal insights</p>
            )}
          </button>

          {/* Interactive Acme Corp Merchant Profile Footer */}
          <button
            onClick={() => setMerchantModalOpen(true)}
            className={cn(
              'w-full flex items-center gap-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-800/90 border border-slate-800 hover:border-slate-700 text-left transition-all duration-200 group',
              isSidebarCollapsed ? 'justify-center p-2' : 'p-2'
            )}
            title="Click to view and edit Merchant Configuration"
          >
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-indigo-900 to-purple-900 text-indigo-200 border border-indigo-500/30 flex items-center justify-center font-black text-xs shrink-0 group-hover:scale-105 transition-transform">
              A
            </div>
            {!isSidebarCollapsed && (
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200 truncate group-hover:text-white transition-colors">
                    {merchantSettings.merchantName}
                  </span>
                  <Building2 className="w-3 h-3 text-slate-500 group-hover:text-indigo-400 transition-colors" />
                </div>
                <span className="text-[10px] text-slate-500 block truncate">
                  {merchantSettings.businessType} • Edit
                </span>
              </div>
            )}
          </button>
        </div>
      </aside>
    </>
  );
};

