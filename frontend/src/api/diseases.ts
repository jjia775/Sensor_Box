// src/api/diseases.ts
export type Disease = {
  key: string
  name: string
  metrics: string[]
}

export type DiseasePayload = {
  key: string
  name: string
  metrics: string[]
}

export type DiseaseUpdatePayload = {
  name?: string
  metrics?: string[]
}

export async function fetchDiseases(apiBase: string): Promise<Disease[]> {
  const r = await fetch(`${apiBase}/api/diseases/`)
  if (!r.ok) throw new Error(await r.text())
  const data = await r.json()
  return data?.diseases ?? []
}

export async function fetchDisease(apiBase: string, key: string): Promise<Disease> {
  const r = await fetch(`${apiBase}/api/diseases/${encodeURIComponent(key)}`)
  if (!r.ok) throw new Error(await r.text())
  return await r.json()
}

export async function createDisease(apiBase: string, payload: DiseasePayload): Promise<Disease> {
  const r = await fetch(`${apiBase}/api/diseases/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(await r.text())
  return await r.json()
}

export async function updateDisease(apiBase: string, key: string, payload: DiseaseUpdatePayload): Promise<Disease> {
  const r = await fetch(`${apiBase}/api/diseases/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(await r.text())
  return await r.json()
}

export async function deleteDisease(apiBase: string, key: string): Promise<void> {
  const r = await fetch(`${apiBase}/api/diseases/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error(await r.text())
}
