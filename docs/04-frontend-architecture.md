# 04 — Frontend Architecture Specification

## 1. High-Level Architecture Flow

```
┌────────────────────────────────────────────────────────┐
│                      UI Layer                          │
│   Pages (Overview, Recovery Center, AI Decisions, ...)  │
│   Components (Layout, CaseDrawer, MetricCards, ...)    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Hooks Layer                         │
│  useRecoveryCases, useAIDecisions, useAnalytics, ...   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│              Service Layer & Demo State                │
│  recoveryService, decisionsService, demoStore (Zustand)│
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                  Future API Boundary                   │
│   FastAPI Client / Mock Services (TypeScript Typed)    │
└────────────────────────────────────────────────────────┘
```

## 2. Directory Hierarchy
- `src/app/`: Core application providers (React Query, Router, Global Theme).
- `src/components/layout/`: DashboardLayout, Sidebar, Topbar, PageHeader.
- `src/components/ui/`: Base primitives (Button, Badge, Card, Dialog, Drawer, Dropdown, Input, Tabs, Slider, Progress, Tooltip).
- `src/components/shared/`: MetricCard, RadialScoreGauge, Sparkline, DataTable, ActionPill.
- `src/components/recovery/`: CaseDrawer, ActionComparison, SHAPExplanation, TimingCard, PolicyCheckSequence, NetworkEvidenceCard.
- `src/components/copilot/`: AICopilotDrawer (Interactive sidebar assistant with contextual queries).
- `src/components/simulator/`: RecoverySimulator (Sliders + real-time economic impact projection).
- `src/pages/`: The 7 approved top-level pages.
- `src/services/`: Modular API service abstractions.
- `src/store/`: `demoStore.ts` managing reactive cross-screen operations (approve, reject, simulate recovery, update KPIs).
- `src/types/`: Full TypeScript definitions matching future Causal ML and backend schemas.

## 3. Separation of Concerns
- Page components do **NOT** directly read static mock data files.
- All data retrieval happens through React custom hooks which query the mock services.
- The `demoStore` maintains unified live state so that any case transition immediately cascades to Overview, Recovery Center, Ledger, Analytics, and Audit logs.
