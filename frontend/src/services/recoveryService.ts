import { RecoveryCase, DecisionOutput } from '../types';
import { apiClient } from './api/apiClient';
import { useDemoStore } from '../store/demoStore';

export const recoveryService = {
  getCases: async (domain?: string, status?: string, search?: string): Promise<RecoveryCase[]> => {
    try {
      const data = await apiClient.get<{ cases: RecoveryCase[]; total: number }>('/recovery/cases', {
        domain: domain !== 'All' ? domain : undefined,
        status: status !== 'All' ? status : undefined,
        search: search || undefined,
        limit: 100,
      });
      if (data && Array.isArray(data.cases) && data.cases.length > 0) {
        // Sync into Zustand for optimistic cross-screen reactivity
        useDemoStore.setState({ cases: data.cases });
        return data.cases;
      }
    } catch {
      // Fallback to demo store if backend unreachable
    }

    let cases = useDemoStore.getState().cases;
    if (domain && domain !== 'All') {
      cases = cases.filter(
        (c) =>
          c.domain.toLowerCase().includes(domain.toLowerCase()) ||
          (domain === 'Subscriptions' && c.domain === 'SUBSCRIPTIONS') ||
          (domain === 'Checkout' && c.domain === 'CHECKOUT') ||
          (domain === 'B2B' && c.domain === 'RECEIVABLES_B2B')
      );
    }
    if (status && status !== 'All') {
      if (status === 'Needs Review') {
        cases = cases.filter((c) => c.status === 'REVIEW');
      } else if (status === 'High Impact') {
        cases = cases.filter((c) => c.amount > 5000 || c.incrementalUplift > 0.2);
      } else if (status === 'Promise-to-Pay') {
        cases = cases.filter((c) => c.recommendedAction === 'WHATSAPP' || c.recommendedAction === 'VOICE');
      } else {
        cases = cases.filter((c) => c.status.toLowerCase() === status.toLowerCase());
      }
    }
    if (search) {
      const q = search.toLowerCase();
      cases = cases.filter(
        (c) =>
          c.caseId.toLowerCase().includes(q) ||
          c.customerName.toLowerCase().includes(q) ||
          c.customerHandle.toLowerCase().includes(q) ||
          c.failureReason.toLowerCase().includes(q)
      );
    }
    return cases;
  },

  getCaseDetail: async (caseId: string): Promise<DecisionOutput | null> => {
    try {
      const detail = await apiClient.get<DecisionOutput>(`/recovery/cases/${caseId}`);
      if (detail && detail.caseId) {
        // Sync into Zustand
        const cur = useDemoStore.getState().caseDetails;
        useDemoStore.setState({ caseDetails: { ...cur, [caseId]: detail } });
        return detail;
      }
    } catch {
      // Fallback
    }

    const details = useDemoStore.getState().caseDetails;
    return details[caseId] || details['RX-48291'] || null;
  },

  approveCase: async (caseId: string, action?: string) => {
    try {
      return await apiClient.post<{ status: string; dispatch_id: string; audit_hash: string }>(
        `/recovery/cases/${caseId}/approve`,
        { action }
      );
    } catch {
      return null;
    }
  },

  rejectCase: async (caseId: string, reason?: string) => {
    try {
      return await apiClient.post<{ status: string; audit_hash: string }>(
        `/recovery/cases/${caseId}/reject`,
        { reason }
      );
    } catch {
      return null;
    }
  },

  simulateRecovery: async (caseId: string) => {
    try {
      return await apiClient.post<{ status: string; recoveredAmount: number; audit_hash: string }>(
        `/recovery/cases/${caseId}/simulate-recovery`
      );
    } catch {
      return null;
    }
  },

  createPaymentLink: async (caseId: string) => {
    try {
      const data = await apiClient.post<{
        case_id: string;
        payment_id: string;
        payment_link_id: string;
        payment_link_url: string;
        amount_paise: number;
        amount_inr: number;
        status: string;
        is_reused: boolean;
      }>(`/recovery/cases/${caseId}/payment-link`);
      if (data) {
        const cases = useDemoStore.getState().cases;
        const updated = cases.map((c) =>
          c.caseId === caseId
            ? {
                ...c,
                paymentLinkId: data.payment_link_id,
                paymentLinkUrl: data.payment_link_url,
              }
            : c
        );
        useDemoStore.setState({ cases: updated });
      }
      return data;
    } catch {
      return null;
    }
  },

  dispatchWhatsApp: async (caseId: string, templateName?: string) => {
    try {
      const data = await apiClient.post<{
        case_id: string;
        whatsapp_message_id: string;
        recipient_phone: string;
        payment_link_url: string;
        status: string;
        attempts_made: number;
      }>(`/recovery/cases/${caseId}/dispatch-whatsapp`, {
        template_name: templateName,
      });
      if (data) {
        const cases = useDemoStore.getState().cases;
        const updated = cases.map((c) =>
          c.caseId === caseId
            ? {
                ...c,
                whatsappMessageId: data.whatsapp_message_id,
                status: (data.status as any) || c.status,
                paymentLinkUrl: data.payment_link_url || c.paymentLinkUrl,
              }
            : c
        );
        useDemoStore.setState({ cases: updated });
      }
      return data;
    } catch {
      return null;
    }
  },

  decide: async (eventData: Record<string, any>) => {
    return await apiClient.post<Record<string, any>>('/decide', eventData);
  },

  generateBatch: async (nSamples: number = 10) => {
    return await apiClient.post<{ batch_count: number; events: any[] }>(`/simulation/generate?n_samples=${nSamples}`);
  },
};
