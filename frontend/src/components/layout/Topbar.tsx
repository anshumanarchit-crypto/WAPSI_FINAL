import React, { useState, useEffect, useRef } from 'react';
import {
  Calendar,
  Filter,
  Bell,
  HelpCircle,
  Search,
  ChevronDown,
  Download,
  Share2,
  Sparkles,
  User,
  Sliders,
  Sun,
  Moon,
  Activity,
  Zap,
  Server,
  Cpu,
  ShieldCheck,
  RefreshCw,
  Power
} from 'lucide-react';
import { Button } from '../ui/Button';
import { useDemoStore } from '../../store/demoStore';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/Tooltip';
import { apiClient, BackendConnectionStatus, HealthStatusResponse } from '../../services/api/apiClient';

interface TopbarProps {
  title?: string;
  subtitle?: string;
  showSearch?: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({ title, subtitle, showSearch = true }) => {
  const toggleCopilot = useDemoStore((state) => state.toggleCopilot);
  const activeNotification = useDemoStore((state) => state.activeNotification);
  const clearNotification = useDemoStore((state) => state.clearNotification);
  const setUserProfileModalOpen = useDemoStore((state) => state.setUserProfileModalOpen);
  const setHelpModalOpen = useDemoStore((state) => state.setHelpModalOpen);
  const setDateRangeModalOpen = useDemoStore((state) => state.setDateRangeModalOpen);
  const setFiltersModalOpen = useDemoStore((state) => state.setFiltersModalOpen);
  const openHeroDemo = useDemoStore((state) => state.openHeroDemo);
  const openAutopilotModal = useDemoStore((state) => state.openAutopilotModal);
  const selectedDateRange = useDemoStore((state) => state.selectedDateRange);
  const activeFilterCount = useDemoStore((state) => state.activeFilterCount);
  const userProfile = useDemoStore((state) => state.userProfile);
  const theme = useDemoStore((state) => state.theme);
  const toggleTheme = useDemoStore((state) => state.toggleTheme);

  const [showNotificationMenu, setShowNotificationMenu] = useState(false);
  const [engineDropdownOpen, setEngineDropdownOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState<BackendConnectionStatus>(apiClient.getStatus());
  const [healthInfo, setHealthInfo] = useState<HealthStatusResponse | null>(apiClient.getLastHealth());
  const [isProbing, setIsProbing] = useState(false);
  const engineDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const unsub = apiClient.onStatusChange((st) => {
      setBackendStatus(st);
      setHealthInfo(apiClient.getLastHealth());
    });

    const timer = setInterval(() => {
      if (!apiClient.isForcedOffline()) {
        apiClient.checkHealth().then((h) => {
          if (h) setHealthInfo(h);
        });
      }
    }, 6000);

    const handleOutsideClick = (e: MouseEvent) => {
      if (engineDropdownRef.current && !engineDropdownRef.current.contains(e.target as Node)) {
        setEngineDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);

    return () => {
      unsub();
      clearInterval(timer);
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, []);

  const handleToggleEngine = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    const forced = apiClient.toggleMode();
    if (forced) {
      useDemoStore.setState({ activeNotification: '🔴 Causal Engine switched to Offline (Client-Side Simulation).' });
    } else {
      useDemoStore.setState({ activeNotification: '🟢 Causal Engine switched to Online (FastAPI Live Backend).' });
    }
  };

  const handleManualProbe = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setIsProbing(true);
    try {
      const h = await apiClient.checkHealth();
      if (h) {
        setHealthInfo(h);
        useDemoStore.setState({ activeNotification: '🟢 Connected to live Causal Decision Engine!' });
      } else {
        useDemoStore.setState({ activeNotification: '🔴 Backend probe failed: Causal Engine is offline.' });
      }
    } finally {
      setIsProbing(false);
    }
  };

  return (
    <header className="h-16 bg-[#0B0F19]/90 backdrop-blur-md border-b border-slate-800/80 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30 select-none gap-4">
      {/* Left Title & Mobile Menu Toggle */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <button
          onClick={() => useDemoStore.getState().toggleSidebar()}
          className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 border border-slate-700/60 shrink-0"
          title="Toggle Navigation Menu"
        >
          <Sliders className="w-4 h-4 text-indigo-400" />
        </button>

        {title && (
          <div className="min-w-0">
            <h1 className="text-sm sm:text-base font-bold text-white tracking-tight flex items-center gap-2 whitespace-nowrap">
              {title}
            </h1>
            {subtitle && <p className="text-xs text-slate-400 truncate hidden md:block">{subtitle}</p>}
          </div>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
        <TooltipProvider delayDuration={150}>
          {/* ⚡ Hero Demo Button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={openHeroDemo}
                className="hidden 2xl:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-amber-500/20 via-indigo-500/20 to-emerald-500/20 border border-amber-500/40 text-xs font-bold text-amber-300 hover:text-white hover:border-amber-400 hover:bg-amber-500/30 transition-all shadow-sm shadow-amber-500/10 cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                <span>⚡ Hero Demo (₹8,999)</span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Launch official 10-step judging demo sequence</p>
            </TooltipContent>
          </Tooltip>

          {/* 🚀 Batch Autopilot Button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={openAutopilotModal}
                className="hidden 2xl:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/60 border border-indigo-500/40 text-xs font-bold text-indigo-300 hover:text-white hover:border-indigo-400 hover:bg-indigo-900/60 transition-all shadow-sm cursor-pointer"
              >
                <Zap className="w-3.5 h-3.5 text-emerald-400" />
                <span>Run Autopilot</span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Process 350 transactions with invariant verification</p>
            </TooltipContent>
          </Tooltip>

          {/* Date Selector */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setDateRangeModalOpen(true)}
                className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs font-medium text-slate-200 hover:border-indigo-500/50 hover:bg-slate-800/80 hover:text-white transition-all shadow-sm"
              >
                <Calendar className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                <span className="font-mono text-slate-200 text-xs hidden sm:inline">{selectedDateRange}</span>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Click to customize analysis window & presets</p>
            </TooltipContent>
          </Tooltip>

          {/* Filter Button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setFiltersModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs font-medium text-slate-200 hover:border-indigo-500/50 hover:bg-slate-800/80 hover:text-white transition-all shadow-sm group"
              >
                <Filter className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-400 transition-colors" />
                <span>Filters</span>
                <span className="min-w-[18px] h-4 px-1 rounded-full bg-indigo-600 text-white text-[10px] flex items-center justify-center font-bold shadow-sm shadow-indigo-600/40">
                  {activeFilterCount}
                </span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>{activeFilterCount} Active causal & policy filters — click to edit</p>
            </TooltipContent>
          </Tooltip>

          {/* Interactive Causal Engine Online / Offline Switch & Controller */}
          <div className="relative" ref={engineDropdownRef}>
            <div
              className={`flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-lg border text-xs font-medium transition-all shadow-sm ${backendStatus === 'LIVE'
                  ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300 hover:border-emerald-500/70'
                  : backendStatus === 'STARTING'
                    ? 'bg-amber-950/40 border-amber-500/40 text-amber-300 hover:border-amber-500/70'
                    : 'bg-rose-950/40 border-rose-500/40 text-rose-300 hover:border-rose-500/70'
                }`}
            >
              {/* Badge info trigger */}
              <button
                onClick={() => setEngineDropdownOpen(!engineDropdownOpen)}
                className="flex items-center gap-2 cursor-pointer select-none hover:opacity-90"
                title="Click to view Causal Engine runtime diagnostics & switch modes"
              >
                <span className="relative flex h-2 w-2">
                  {backendStatus === 'LIVE' && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  )}
                  <span
                    className={`relative inline-flex rounded-full h-2 w-2 ${backendStatus === 'LIVE'
                        ? 'bg-emerald-400'
                        : backendStatus === 'STARTING'
                          ? 'bg-amber-400 animate-pulse'
                          : 'bg-rose-500'
                      }`}
                  />
                </span>
                <span className="hidden lg:inline text-[11px] font-semibold tracking-tight">
                  {backendStatus === 'LIVE'
                    ? 'Causal Engine: Online'
                    : backendStatus === 'STARTING'
                      ? 'Causal Engine: Starting...'
                      : 'Causal Engine: Offline'}
                </span>
                <ChevronDown className={`w-3 h-3 transition-transform ${engineDropdownOpen ? 'rotate-180 text-white' : 'text-slate-400'}`} />
              </button>

              {/* Direct Online / Offline Switch */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleToggleEngine}
                    className={`relative inline-flex h-4 w-8 flex-shrink-0 cursor-pointer rounded-full border border-slate-700 transition-colors duration-200 ease-in-out focus:outline-none ${backendStatus === 'LIVE' ? 'bg-emerald-500' : 'bg-slate-800'
                      }`}
                    aria-label="Toggle Causal Engine Online/Offline"
                  >
                    <span
                      aria-hidden="true"
                      className={`pointer-events-none inline-block h-3 w-3 mt-[1px] transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${backendStatus === 'LIVE' ? 'translate-x-4' : 'translate-x-0.5'
                        }`}
                    />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
                  <p>
                    {backendStatus === 'LIVE'
                      ? 'Click to switch Causal Engine to Offline (Demo Mode)'
                      : 'Click to switch Causal Engine to Online (Live FastAPI)'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>

            {/* Dropdown Control Panel */}
            {engineDropdownOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl bg-slate-900/95 border border-slate-800 shadow-2xl backdrop-blur-xl p-4 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-indigo-400" />
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Causal Engine Runtime</h4>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${backendStatus === 'LIVE'
                        ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-400'
                        : backendStatus === 'STARTING'
                          ? 'bg-amber-950/80 border border-amber-500/40 text-amber-400'
                          : 'bg-rose-950/80 border border-rose-500/40 text-rose-400'
                      }`}
                  >
                    {backendStatus === 'LIVE' ? 'Online' : backendStatus === 'STARTING' ? 'Starting' : 'Offline'}
                  </span>
                </div>

                {/* Mode Controller Card */}
                <div className="mt-3 p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-slate-200">Execution Mode</p>
                      <p className="text-[11px] text-slate-400">
                        {backendStatus === 'LIVE'
                          ? 'Connected to FastAPI (:8000)'
                          : 'Resilient client-side simulation'}
                      </p>
                    </div>
                    <button
                      onClick={handleToggleEngine}
                      className={`relative inline-flex h-5 w-10 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${backendStatus === 'LIVE' ? 'bg-emerald-500' : 'bg-slate-700'
                        }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${backendStatus === 'LIVE' ? 'translate-x-5' : 'translate-x-0'
                          }`}
                      />
                    </button>
                  </div>

                  <div className="pt-2 flex gap-2">
                    <Button
                      variant={backendStatus === 'LIVE' ? 'primary' : 'outline'}
                      size="sm"
                      onClick={() => {
                        apiClient.setForceOffline(false);
                        useDemoStore.setState({ activeNotification: '🟢 Connecting Causal Engine to Live FastAPI Backend...' });
                      }}
                      className="flex-1 text-[11px] py-1 h-7"
                    >
                      Online Mode
                    </Button>
                    <Button
                      variant={backendStatus === 'OFFLINE' ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => {
                        apiClient.setForceOffline(true);
                        useDemoStore.setState({ activeNotification: '🔴 Causal Engine set to Offline Demo Mode.' });
                      }}
                      className="flex-1 text-[11px] py-1 h-7"
                    >
                      Offline Mode
                    </Button>
                  </div>
                </div>

                {/* Diagnostics Details */}
                <div className="mt-3 space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between text-slate-400 py-1 border-b border-slate-800/40">
                    <span className="flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 text-indigo-400" /> Causal Models
                    </span>
                    <span className="font-mono text-slate-300">
                      {backendStatus === 'LIVE' ? 'T-Learner, X-Learner, SHAP' : 'Client Causal Simulator'}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400 py-1 border-b border-slate-800/40">
                    <span className="flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" /> TEE Enclave
                    </span>
                    <span className="font-mono text-[10px] text-emerald-400">
                      {healthInfo?.tee_boundary?.enclave_measurement_pcr0?.slice(0, 12) || '2d54fff6b7e9'}...
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-slate-400 py-1">
                    <span className="flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5 text-amber-400" /> Endpoint
                    </span>
                    <span className="font-mono text-slate-300">http://127.0.0.1:8000</span>
                  </div>
                </div>

                {/* Footer Controls */}
                <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between">
                  <button
                    onClick={handleManualProbe}
                    disabled={isProbing}
                    className="flex items-center gap-1.5 text-[11px] font-semibold text-indigo-400 hover:text-indigo-300 transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isProbing ? 'animate-spin' : ''}`} />
                    <span>Re-probe Health</span>
                  </button>
                  <button
                    onClick={() => setEngineDropdownOpen(false)}
                    className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Help Trigger */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setHelpModalOpen(true)}
                className="p-2 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300 hover:text-white hover:border-slate-600 transition-colors"
              >
                <HelpCircle className="w-4 h-4 text-indigo-400" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Help & Causal Model Docs</p>
            </TooltipContent>
          </Tooltip>

          {/* Theme Toggle (Dark / Light) */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggleTheme}
                className="p-2 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300 hover:text-white hover:border-slate-600 transition-colors cursor-pointer"
              >
                {theme === 'dark' ? (
                  <Sun className="w-4 h-4 text-amber-400 hover:rotate-45 transition-transform" />
                ) : (
                  <Moon className="w-4 h-4 text-indigo-400 hover:-rotate-12 transition-transform" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Switch to {theme === 'dark' ? 'Light' : 'Dark'} theme</p>
            </TooltipContent>
          </Tooltip>

          {/* AI Copilot Quick Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={toggleCopilot}
            className="gap-1.5 border-indigo-500/30 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Ask AI</span>
          </Button>

          {/* Notifications */}
          <div className="relative">
            <button
              onClick={() => setShowNotificationMenu(!showNotificationMenu)}
              className="relative p-2 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300 hover:text-white hover:border-slate-600 transition-colors"
            >
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-[#0B0F19]" />
            </button>

            {showNotificationMenu && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl bg-[#0F172A] border border-slate-700 shadow-2xl p-4 z-50 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <span className="text-xs font-bold text-white">Notifications</span>
                  <span className="text-[10px] text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">
                    2 New
                  </span>
                </div>
                <div className="mt-3 space-y-2 text-xs">
                  {activeNotification && (
                    <div className="p-2.5 rounded-lg bg-indigo-950/40 border border-indigo-500/30 text-indigo-200">
                      <p className="font-semibold text-white">Demo State Update</p>
                      <p className="text-[11px] text-slate-300 mt-0.5">{activeNotification}</p>
                    </div>
                  )}
                  <div className="p-2 rounded bg-slate-900 border border-slate-800 text-slate-300">
                    <p className="font-medium text-white">Recovery Engine Spike</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      HDFC recovery rate reached 72% (+14% uplift) in the 24h window.
                    </p>
                    <span className="text-[9px] text-slate-500 mt-1 block">10 mins ago</span>
                  </div>
                  <div className="p-2 rounded bg-slate-900 border border-slate-800 text-slate-300">
                    <p className="font-medium text-white">Policy Compliance Verification</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      100% of 128 autonomous actions passed NPCI and TRAI bounds.
                    </p>
                    <span className="text-[9px] text-slate-500 mt-1 block">1 hour ago</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Interactive User Avatar (Top Header Rightmost Corner) */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setUserProfileModalOpen(true)}
                className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-purple-600 border border-indigo-400/40 flex items-center justify-center font-bold text-xs text-white shadow-md hover:scale-105 transition-transform"
              >
                {userProfile.avatar}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="bg-slate-900 border border-slate-700 text-xs">
              <p>Operator Profile ({userProfile.name})</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </header>
  );
};
