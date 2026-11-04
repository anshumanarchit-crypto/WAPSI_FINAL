import { useQuery } from '@tanstack/react-query';
import { decisionsService } from '../services/decisionsService';
import { useDemoStore } from '../store/demoStore';

export function useDecisionsOverview() {
  return useQuery({
    queryKey: ['decisionsOverview'],
    queryFn: () => decisionsService.getOverview(),
    staleTime: 10000,
  });
}

export function useModelHealth() {
  return useQuery({
    queryKey: ['modelHealth'],
    queryFn: () => decisionsService.getModelHealth(),
  });
}
