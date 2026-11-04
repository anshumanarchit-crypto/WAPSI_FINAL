# Non-Negotiable Engineering Rules for WAPSI Frontend

1. React + Vite + TypeScript.
2. React Router for SPA routing.
3. Tailwind CSS with custom dark theme tokens matching Stitch.
4. shadcn/ui and Radix primitives where appropriate.
5. Recharts for data visualization matching Stitch charts.
6. Framer Motion for subtle, purposeful micro-interactions.
7. TanStack Query for server state abstraction.
8. Zustand for lightweight global UI and cross-screen reactive demo state.
9. Google Stitch is the PRIMARY visual source of truth (`https://stitch.withgoogle.com/projects/11931954862282798683`).
10. Never redesign Stitch unnecessarily.
11. Never invent a replacement design.
12. Never use screenshots as the actual application.
13. Rebuild Stitch using real, high-fidelity React components.
14. Reuse shared components across screens (PageHeader, MetricCard, StatusBadge, DataTable, CaseDrawer).
15. No duplicate Case Drawer implementations.
16. No duplicate global layouts.
17. No new top-level routes without explicit approval (only the 7 approved routes: `/overview`, `/recovery-center`, `/ai-decisions`, `/recovery-cases`, `/analytics`, `/governance`, `/settings`).
18. Mock services must be strictly separated from UI components (`Page -> Hook -> Service -> Mock Data`).
19. Frontend contracts must be future Causal ML-compatible.
20. No real backend / Python implementation in this phase.
21. No real ML / EconML training execution in this phase.
22. No production TEE claims (clearly label as "TEE Simulation" / "Prototype Security Boundary").
23. No production Razorpay integration claims.
24. No invented performance metrics.
25. No hardcoded business logic inside presentation components.
26. Every major page must be visually compared against Stitch.
27. Do not mark a page complete after first implementation.
28. Fix TypeScript errors immediately.
29. Fix console errors immediately.
30. Do not modify unrelated files.
31. Do not add random or distracting visual effects.
32. Prefer fidelity over creativity.
33. Preserve the original Stitch information hierarchy.
34. If Stitch access fails, STOP visual implementation.
