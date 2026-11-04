import { mockDomainShares, mockFunnelSteps } from '../mock/mockData';
import { useDemoStore } from '../store/demoStore';
import { apiClient } from './api/apiClient';

export const analyticsService = {
  getAnalyticsSummary: async () => {
    const metrics = useDemoStore.getState().overviewMetrics;
    const { simulatorContacts, simulatorRetryBudget } = useDemoStore.getState();

    try {
      const liveSummary = await apiClient.get<any>('/analytics/summary');
      if (liveSummary && liveSummary.overview) {
        return {
          metrics: {
            ...metrics,
            ...liveSummary.overview,
          },
          domains: liveSummary.domainShare || mockDomainShares,
          funnel: liveSummary.funnelSteps || mockFunnelSteps,
          pulse: liveSummary.recoveryPulse,
          failureReasons: liveSummary.failureReasons,
          simulatedRecovery: Math.round(
            782000 * (1 + 0.15 * Math.log(Math.max(0.1, simulatorContacts / 742)) + 0.12 * Math.log(Math.max(0.1, simulatorRetryBudget / 1842)))
          ),
          simulatorContacts,
          simulatorRetryBudget,
        };
      }
    } catch {
      // Fallback
    }

    const contactFactor = simulatorContacts / 742;
    const retryFactor = simulatorRetryBudget / 1842;
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
  },

  simulateCounterfactual: async (contacts: number, retries: number) => {
    try {
      return await apiClient.post<any>('/analytics/simulate', {
        expectedContacts: contacts,
        retryBudget: retries,
      });
    } catch {
      const contactFactor = Math.max(0.1, contacts / 742.0);
      const retryFactor = Math.max(0.1, retries / 1842.0);
      const estimatedL = 7.82 * (1.0 + 0.15 * Math.log(contactFactor) + 0.12 * Math.log(retryFactor));
      return {
        contacts,
        retryBudget: retries,
        estimatedRecoveryLakhs: round(estimatedL, 2),
        increase20Lakhs: round(estimatedL * 1.063, 2),
        decrease20Lakhs: round(estimatedL * 0.889, 2),
        incrementalImpactPercent: 6.3,
      };
    }
  },
};

function round(n: number, decimals: number = 2): number {
  return Number(n.toFixed(decimals));
}
