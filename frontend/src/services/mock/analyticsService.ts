import { mockDomainShares, mockFunnelSteps } from '../../mock/mockData';
import { useDemoStore } from '../../store/demoStore';

export const analyticsService = {
  getAnalyticsSummary: async () => {
    const metrics = useDemoStore.getState().overviewMetrics;
    const { simulatorContacts, simulatorRetryBudget } = useDemoStore.getState();
    
    // Dynamic simulation calculation
    // Base: 742 contacts, 1842 retries -> 7.82L recovered
    const contactFactor = simulatorContacts / 742;
    const retryFactor = simulatorRetryBudget / 1842;
    
    // Diminishing returns formula
    const simulatedRecovery = Math.round(
      782000 * (1 + 0.15 * Math.log(contactFactor) + 0.12 * Math.log(retryFactor))
    );

    return {
      metrics,
      domains: mockDomainShares,
      funnel: mockFunnelSteps,
      simulatedRecovery,
      simulatorContacts,
      simulatorRetryBudget,
    };
  }
};
