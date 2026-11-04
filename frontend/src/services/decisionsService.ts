import { 
  mockModelHealth, 
  mockRecoveryPulse, 
  mockDomainShares, 
  mockFailureReasons, 
  mockFunnelSteps, 
  mockOpportunityActions 
} from '../mock/mockData';
import { useDemoStore } from '../store/demoStore';
import { apiClient } from './api/apiClient';

export const decisionsService = {
  getOverview: async () => {
    try {
      const [decisionsRes, analyticsRes] = await Promise.allSettled([
        apiClient.get<any>('/decisions/overview'),
        apiClient.get<any>('/analytics/summary'),
      ]);

      const backendOverview = decisionsRes.status === 'fulfilled' ? decisionsRes.value : null;
      const analyticsSummary = analyticsRes.status === 'fulfilled' ? analyticsRes.value : null;

      if (backendOverview || analyticsSummary) {
        return {
          metrics: useDemoStore.getState().overviewMetrics,
          pulse: analyticsSummary?.recoveryPulse || mockRecoveryPulse,
          domains: analyticsSummary?.domainShare || mockDomainShares,
          failureReasons: analyticsSummary?.failureReasons || mockFailureReasons,
          funnel: analyticsSummary?.funnelSteps || mockFunnelSteps,
          opportunities: mockOpportunityActions,
          modelHealth: mockModelHealth,
          backendOverview: backendOverview || undefined,
          analyticsSummary: analyticsSummary || undefined,
        };
      }
    } catch {
      // Fallback
    }

    return {
      metrics: useDemoStore.getState().overviewMetrics,
      pulse: mockRecoveryPulse,
      domains: mockDomainShares,
      failureReasons: mockFailureReasons,
      funnel: mockFunnelSteps,
      opportunities: mockOpportunityActions,
      modelHealth: mockModelHealth,
    };
  },

  getModelHealth: async () => {
    try {
      const health = await apiClient.get<any>('/decisions/model-health');
      if (health && health.overallScore) {
        return {
          ...mockModelHealth,
          ...health,
        };
      }
    } catch {
      // Fallback
    }

    return mockModelHealth;
  },

  getUpliftMetrics: async (action?: string) => {
    try {
      return await apiClient.get<any>('/metrics/uplift', { action });
    } catch {
      return null;
    }
  },
};
