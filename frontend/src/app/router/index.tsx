import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DashboardLayout } from '../../components/layout/DashboardLayout';
import { OverviewPage } from '../../pages/OverviewPage';
import { RecoveryCenterPage } from '../../pages/RecoveryCenterPage';
import { AIDecisionsPage } from '../../pages/AIDecisionsPage';
import { RecoveryCasesPage } from '../../pages/RecoveryCasesPage';
import { AnalyticsPage } from '../../pages/AnalyticsPage';
import { GovernancePage } from '../../pages/GovernancePage';
import { SettingsPage } from '../../pages/SettingsPage';
import { ObservationalLearningPage } from '../../pages/ObservationalLearningPage';
import { WorkerOperationsPage } from '../../pages/WorkerOperationsPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/overview" replace />,
      },
      {
        path: 'overview',
        element: <OverviewPage />,
      },
      {
        path: 'recovery-center',
        element: <RecoveryCenterPage />,
      },
      {
        path: 'ai-decisions',
        element: <AIDecisionsPage />,
      },
      {
        path: 'recovery-cases',
        element: <RecoveryCasesPage />,
      },
      {
        path: 'observational-learning',
        element: <ObservationalLearningPage />,
      },
      {
        path: 'worker-operations',
        element: <WorkerOperationsPage />,
      },
      {
        path: 'analytics',
        element: <AnalyticsPage />,
      },
      {
        path: 'governance',
        element: <GovernancePage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
      {
        path: '*',
        element: <Navigate to="/overview" replace />,
      },
    ],
  },
]);
