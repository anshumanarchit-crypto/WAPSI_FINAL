# 03 — Design System & Visual Tokens

This design system is derived directly from the Google Stitch project and enforces dark enterprise fintech aesthetics.

## 1. Color Palette Tokens

```css
:root {
  /* Canvas & Backgrounds */
  --bg-app: #080B11;
  --bg-card: #0F172A;
  --bg-card-subtle: #131D33;
  --bg-card-hover: #18243E;
  --bg-sidebar: #0B0F19;
  --bg-topbar: #0B0F19;
  
  /* Borders & Dividers */
  --border-subtle: #1E293B;
  --border-strong: #334155;
  --border-focus: #6366F1;
  
  /* Primary & Accent Colors */
  --color-primary: #6366F1; /* Indigo / Purple */
  --color-primary-light: #818CF8;
  --color-primary-dark: #4F46E5;
  --color-primary-glow: rgba(99, 102, 241, 0.25);
  
  /* Status Colors */
  --color-success: #10B981; /* Emerald */
  --color-success-bg: rgba(16, 185, 129, 0.12);
  --color-success-border: rgba(16, 185, 129, 0.3);
  
  --color-warning: #F59E0B; /* Amber */
  --color-warning-bg: rgba(245, 158, 11, 0.12);
  --color-warning-border: rgba(245, 158, 11, 0.3);
  
  --color-danger: #EF4444; /* Rose / Red */
  --color-danger-bg: rgba(239, 68, 68, 0.12);
  --color-danger-border: rgba(239, 68, 68, 0.3);
  
  --color-info: #06B6D4; /* Cyan / Sky */
  --color-info-bg: rgba(6, 182, 212, 0.12);
  --color-info-border: rgba(6, 182, 212, 0.3);
  
  /* Typography Colors */
  --text-primary: #FFFFFF;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  --text-disabled: #475569;
}
```

## 2. Typography Hierarchy
- **Font Family**: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif.
- **Numbers / Metrics**: `font-variant-numeric: tabular-nums;` for precise financial alignment.
- **Scale**:
  - Hero Display: `24px` / `text-2xl`, font-bold, tracking-tight
  - Section Header: `18px` / `text-lg`, font-semibold
  - Card Title: `13px` / `text-xs` or `14px` / `text-sm`, font-medium, uppercase/tracking-wider or slate-400
  - KPI Big Value: `22px` - `26px`, font-bold, text-white
  - Body Text: `13px` - `14px`, text-slate-300
  - Captions / Meta: `11px` - `12px`, text-slate-400

## 3. Elevation, Radius & Borders
- **Card Border Radius**: `rounded-xl` (`12px`) or `rounded-2xl` (`16px`)
- **Badge Radius**: `rounded-full` (`9999px`) or `rounded-md` (`6px`)
- **Card Shadow**: `box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.04);`
- **Backdrop Blur**: `backdrop-blur-md` on topbar, sticky headers, and drawer overlays.

## 4. Reusable Component Language
- **MetricCard**: Container with 1px border, icon container with subtle glow, big value, delta pill (`+37.2% vs baseline`), and optional sparkline.
- **StatusBadge**: Consistent color mapping across all tables (READY = Emerald, REVIEW = Amber, MONITORING = Cyan, FAILED = Red, OOD = Purple).
- **RadialScoreGauge**: SVG-based animated arc gauge showing score (e.g. 95/100, 100% Healthy).
- **CaseDrawer**: Right sliding sheet (width ~`480px`) with tabs, action comparisons, SHAP waterfall bars, timing hazard graphs, and interactive approval workflow.
- **Table Density**: Compact enterprise rows (`py-3` / `h-14`), border-b `border-slate-800/60`, hover `bg-slate-800/30`.
