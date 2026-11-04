import { useQuery } from '@tanstack/react-query';
import { recoveryService } from '../services/recoveryService';
import { useDemoStore } from '../store/demoStore';

export function useRecoveryCases(domain?: string, status?: string, search?: string) {
  return useQuery({
    queryKey: ['recoveryCases', domain, status, search],
    queryFn: () => recoveryService.getCases(domain, status, search),
    staleTime: 10000,
  });
}

export function useCaseDetail(caseId: string | null) {
  return useQuery({
    queryKey: ['caseDetail', caseId],
    queryFn: () => (caseId ? recoveryService.getCaseDetail(caseId) : null),
    enabled: !!caseId,
    staleTime: 10000,
  });
}
