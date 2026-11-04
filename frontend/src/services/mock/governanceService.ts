import { mockFairnessMetrics } from '../../mock/mockData';
import { useDemoStore } from '../../store/demoStore';

export const governanceService = {
  getGovernanceData: async () => {
    const state = useDemoStore.getState();
    return {
      policyControls: state.policyControls,
      auditTrail: state.auditTrail,
      fairness: mockFairnessMetrics,
    };
  }
};
