import { useQuery } from '@tanstack/react-query';
import { stuartClient } from '@/api/stuartClient';

export function useRegistry() {
  return useQuery({
    queryKey: ['registry'],
    queryFn: () => stuartClient.registry.get(),
    staleTime: 60_000,
  });
}
