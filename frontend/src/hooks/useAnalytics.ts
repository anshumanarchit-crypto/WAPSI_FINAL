import { useQuery } from '@tanstack/react-query';
import { analyticsService } from '../services/analyticsService';
import { useDemoStore } from '../store/demoStore';

export function useAnalytics() {
  const metrics = useDemoStore((state) => state.overviewMetrics);
  const contacts = useDemoStore((state) => state.simulatorContacts);
  const retries = useDemoStore((state) => state.simulatorRetryBudget);
  
  return useQuery({
    queryKey: ['analyticsData', metrics, contacts, retries],
    queryFn: () => analyticsService.getAnalyticsSummary(),
  });
}
