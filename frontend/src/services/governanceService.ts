import { mockFairnessMetrics } from '../mock/mockData';
import { useDemoStore } from '../store/demoStore';
import { apiClient } from './api/apiClient';

export const governanceService = {
  getGovernanceData: async () => {
    const state = useDemoStore.getState();

    try {
      const [trailRes, policiesRes, teeRes, fairnessRes] = await Promise.allSettled([
        apiClient.get<{ integrity: boolean; total: number; events: any[] }>('/governance/audit-trail?limit=50'),
        apiClient.get<any[]>('/governance/policies'),
        apiClient.get<any>('/governance/tee-status'),
        apiClient.get<any>('/governance/fairness'),
      ]);

      const auditTrail = trailRes.status === 'fulfilled' && trailRes.value.events ? trailRes.value.events : state.auditTrail;
      const policyControls = policiesRes.status === 'fulfilled' && Array.isArray(policiesRes.value) ? policiesRes.value : state.policyControls;
      const fairness = fairnessRes.status === 'fulfilled' ? fairnessRes.value : mockFairnessMetrics;
      const teeStatus = teeRes.status === 'fulfilled' ? teeRes.value : null;

      // Sync audit trail into demo store for cross-screen reactivity
      if (trailRes.status === 'fulfilled' && trailRes.value.events) {
        useDemoStore.setState({ auditTrail });
      }

      return {
        policyControls,
        auditTrail,
        fairness,
        teeStatus,
      };
    } catch {
      // Fallback
    }

    return {
      policyControls: state.policyControls,
      auditTrail: state.auditTrail,
      fairness: mockFairnessMetrics,
      teeStatus: null,
    };
  },

  getAuditLedger: async (limit: number = 50) => {
    try {
      return await apiClient.get<any>('/audit/ledger', { limit });
    } catch {
      return null;
    }
  },

  getTEEStatus: async () => {
    try {
      return await apiClient.get<any>('/governance/tee-status');
    } catch {
      return null;
    }
  },
};
