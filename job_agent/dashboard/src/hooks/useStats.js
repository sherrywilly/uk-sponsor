import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../lib/api'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => apiGet('/api/stats'),
  })
}

export function useJobs(filters = {}) {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  return useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => apiGet(`/api/jobs${params.toString() ? `?${params.toString()}` : ''}`),
  })
}

export function useRecordings() {
  return useQuery({
    queryKey: ['recordings'],
    queryFn: () => apiGet('/api/recordings'),
  })
}

export function useTokens() {
  return useQuery({
    queryKey: ['tokens'],
    queryFn: () => apiGet('/api/tokens'),
  })
}

export function useCost() {
  return useQuery({
    queryKey: ['cost'],
    queryFn: () => apiGet('/api/cost'),
  })
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ['agent-status'],
    queryFn: () => apiGet('/api/agent/status'),
  })
}
