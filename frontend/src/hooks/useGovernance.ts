import { useQuery } from '@tanstack/react-query';
import { governanceService } from '../services/governanceService';
import { useDemoStore } from '../store/demoStore';

export function useGovernance() {
  const auditTrail = useDemoStore((state) => state.auditTrail);
  const policyControls = useDemoStore((state) => state.policyControls);
  
  return useQuery({
    queryKey: ['governanceData', auditTrail, policyControls],
    queryFn: () => governanceService.getGovernanceData(),
  });
}
