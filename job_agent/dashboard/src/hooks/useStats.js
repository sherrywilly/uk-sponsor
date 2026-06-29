import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../lib/api'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => apiGet('/api/stats'),
    refetchInterval: 8000,
  })
}

export function useJobs(status) {
  return useQuery({
    queryKey: ['jobs', status],
    queryFn: () => apiGet(status ? `/api/jobs?status=${status}` : '/api/jobs'),
    refetchInterval: 8000,
  })
}

export function useRecordings() {
  return useQuery({
    queryKey: ['recordings'],
    queryFn: () => apiGet('/api/recordings'),
    refetchInterval: 10000,
  })
}

export function useTokens() {
  return useQuery({
    queryKey: ['tokens'],
    queryFn: () => apiGet('/api/tokens'),
    refetchInterval: 10000,
  })
}

export function useCost() {
  return useQuery({
    queryKey: ['cost'],
    queryFn: () => apiGet('/api/cost'),
    refetchInterval: 10000,
  })
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ['agent-status'],
    queryFn: () => apiGet('/api/agent/status'),
    refetchInterval: 3000,
  })
}
