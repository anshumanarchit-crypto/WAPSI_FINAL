import { RecoveryCase, DecisionOutput } from '../../types';
import { useDemoStore } from '../../store/demoStore';

export const recoveryService = {
  getCases: async (domain?: string, status?: string, search?: string): Promise<RecoveryCase[]> => {
    let cases = useDemoStore.getState().cases;
    
    if (domain && domain !== 'All') {
      cases = cases.filter((c) => c.domain.toLowerCase().includes(domain.toLowerCase()) || (domain === 'Subscriptions' && c.domain === 'SUBSCRIPTIONS') || (domain === 'Checkout' && c.domain === 'CHECKOUT') || (domain === 'B2B' && c.domain === 'RECEIVABLES_B2B'));
    }
    
    if (status && status !== 'All') {
      if (status === 'Needs Review') {
        cases = cases.filter((c) => c.status === 'REVIEW');
      } else if (status === 'High Impact') {
        cases = cases.filter((c) => c.amount > 5000 || c.incrementalUplift > 0.20);
      } else if (status === 'Promise-to-Pay') {
        cases = cases.filter((c) => c.recommendedAction === 'WHATSAPP' || c.recommendedAction === 'VOICE');
      } else {
        cases = cases.filter((c) => c.status.toLowerCase() === status.toLowerCase());
      }
    }
    
    if (search) {
      const q = search.toLowerCase();
      cases = cases.filter((c) => 
        c.caseId.toLowerCase().includes(q) ||
        c.customerName.toLowerCase().includes(q) ||
        c.customerHandle.toLowerCase().includes(q) ||
        c.failureReason.toLowerCase().includes(q)
      );
    }
    
    return cases;
  },

  getCaseDetail: async (caseId: string): Promise<DecisionOutput | null> => {
    const details = useDemoStore.getState().caseDetails;
    return details[caseId] || details['RX-48291'] || null;
  }
};
