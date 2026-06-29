import { useQuery } from '@tanstack/react-query'

async function getJson(path) {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`Request failed: ${path}`)
  return res.json()
}

export function useStats() {
  return useQuery({ queryKey: ['stats'], queryFn: () => getJson('/api/stats'), refetchInterval: 4000 })
}

export function useJobs() {
  return useQuery({ queryKey: ['jobs'], queryFn: () => getJson('/api/jobs'), refetchInterval: 5000 })
}

export function useRecordings() {
  return useQuery({ queryKey: ['recordings'], queryFn: () => getJson('/api/recordings'), refetchInterval: 7000 })
}

export function useTokens() {
  return useQuery({ queryKey: ['tokens'], queryFn: () => getJson('/api/tokens'), refetchInterval: 6000 })
}

export function useCost() {
  return useQuery({ queryKey: ['cost'], queryFn: () => getJson('/api/cost'), refetchInterval: 6000 })
}
