import { 
  mockModelHealth, 
  mockRecoveryPulse, 
  mockDomainShares, 
  mockFailureReasons, 
  mockFunnelSteps, 
  mockOpportunityActions 
} from '../../mock/mockData';
import { useDemoStore } from '../../store/demoStore';

export const decisionsService = {
  getOverview: async () => {
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
    return mockModelHealth;
  }
};
