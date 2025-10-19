import { useMemo } from 'react'

export function useApiBase() {
  return useMemo(() => import.meta.env.VITE_API_BASE || 'http://localhost:8000', [])
}
