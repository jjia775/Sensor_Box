import {type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApiBase } from '../../hooks/useApiBase'
import formatTimestamp from '../../utils/formatTimestamp'

type SensorSnapshot = {
  id: string
  name: string
  type: string
  location?: string | null
  house_id?: string | null
  latest_value: number | null
  latest_ts: string | null
}

type AdviceResponse = {
  advice: string
  sensors: SensorSnapshot[]
}

const parseErrorMessage = async (response: Response): Promise<string> => {
  try {
    const data = await response.json()
    if (typeof data === 'object' && data !== null) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      if (typeof detail === 'object' && detail && 'message' in (detail as Record<string, unknown>)) {
        const message = (detail as { message?: unknown }).message
        if (typeof message === 'string') return message
      }
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  } catch (error) {
    console.error('Failed to parse error response', error)
  }
  return response.statusText || 'Request failed'
}

const getStoredHouseId = () => (typeof window !== 'undefined' ? localStorage.getItem('house_id') || '' : '')

export default function HealthAdvisorPage() {
  const API_BASE = useApiBase()

  const [houseIdInput, setHouseIdInput] = useState<string>(getStoredHouseId)
  const [houseId, setHouseId] = useState<string>(getStoredHouseId)

  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [advice, setAdvice] = useState<string>('')
  const [snapshots, setSnapshots] = useState<SensorSnapshot[]>([])

  const handleSelectHouseId = (value: string) => {
    setHouseId(value)
    setHouseIdInput(value)
    if (value) {
      localStorage.setItem('house_id', value)
    } else {
      localStorage.removeItem('house_id')
    }
  }

  const handleApplyHouseId = (event: FormEvent) => {
    event.preventDefault()
    const value = houseIdInput.trim()
    handleSelectHouseId(value)
  }

  const fetchAdvice = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload: Record<string, string> = {}
      if (houseId) {
        payload.house_id = houseId
      }
      const res = await fetch(`${API_BASE}/api/ai/health-advice`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        throw new Error(await parseErrorMessage(res))
      }
      const data = (await res.json()) as AdviceResponse
      setAdvice(data.advice ?? '')
      setSnapshots(Array.isArray(data.sensors) ? data.sensors : [])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch health advice'
      setError(message)
      setAdvice('')
      setSnapshots([])
    } finally {
      setLoading(false)
    }
  }, [API_BASE, houseId])

  useEffect(() => {
    fetchAdvice()
  }, [fetchAdvice])

  type AdviceBlock =
    | { kind: 'heading'; level: number; content: string }
    | { kind: 'paragraph'; content: string }
    | { kind: 'list'; ordered: boolean; items: string[] }

  const stripInlineFormatting = (text: string) =>
    text
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/_(.*?)_/g, '$1')

  const formattedAdvice = useMemo<AdviceBlock[][]>(() => {
    if (!advice) return []

    return advice
      .split(/\n{2,}/)
      .map(section => section.trim())
      .filter(section => section.length > 0)
      .map(section => {
        const lines = section.split('\n')
        const blocks: AdviceBlock[] = []

        lines.forEach(rawLine => {
          const line = rawLine.trim()
          if (!line) return

          if (/^#{1,6}\s+/.test(line)) {
            const level = line.match(/^#+/)?.[0].length ?? 1
            blocks.push({
              kind: 'heading',
              level,
              content: stripInlineFormatting(line.replace(/^#{1,6}\s+/, '')),
            })
            return
          }

          if (/^[-*]\s+/.test(line)) {
            const content = stripInlineFormatting(line.replace(/^[-*]\s+/, ''))
            const lastBlock = blocks[blocks.length - 1]
            if (lastBlock && lastBlock.kind === 'list' && !lastBlock.ordered) {
              lastBlock.items.push(content)
            } else {
              blocks.push({ kind: 'list', ordered: false, items: [content] })
            }
            return
          }

          if (/^\d+\.\s+/.test(line)) {
            const content = stripInlineFormatting(line.replace(/^\d+\.\s+/, ''))
            const lastBlock = blocks[blocks.length - 1]
            if (lastBlock && lastBlock.kind === 'list' && lastBlock.ordered) {
              lastBlock.items.push(content)
            } else {
              blocks.push({ kind: 'list', ordered: true, items: [content] })
            }
            return
          }

          blocks.push({ kind: 'paragraph', content: stripInlineFormatting(line) })
        })

        return blocks
      })
  }, [advice])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Health Advisor</h1>
            <p className="text-sm text-gray-500">
              Generate personalised wellness insights powered by Gemini AI using your latest sensor readings.
            </p>
          </div>
          <div className="flex gap-2">
            {houseId && (
              <Link
                to={`/dashboard/${encodeURIComponent(houseId)}`}
                className="rounded-xl border px-4 py-2 hover:bg-gray-100"
              >
                Back to Dashboard
              </Link>
            )}
            <Link to="/data-viewer" className="rounded-xl border px-4 py-2 hover:bg-gray-100">
              Data Viewer
            </Link>
          </div>
        </header>

        <section className="rounded-2xl bg-white border shadow p-4">
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleApplyHouseId}>
            <div className="flex-1">
              <label htmlFor="house-id" className="block text-sm font-medium text-gray-700">
                House ID (optional)
              </label>
              <input
                id="house-id"
                value={houseIdInput}
                onChange={event => setHouseIdInput(event.target.value)}
                placeholder="Leave empty to analyse all sensors"
                className="mt-1 w-full rounded-xl border px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <button
              type="submit"
              className="min-w-[130px] rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-blue-700 sm:self-stretch"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={fetchAdvice}
              disabled={loading}
              className="min-w-[130px] rounded-xl border px-4 py-2 text-sm font-medium shadow-sm transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 sm:self-stretch"
            >
              {loading ? 'Generating…' : 'Generate Advice'}
            </button>
          </form>
          <div className="mt-3 text-xs text-gray-500">API base: {API_BASE}</div>
        </section>

        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <div className="font-semibold">Unable to generate advice</div>
            <div className="mt-1 whitespace-pre-wrap">{error}</div>
          </div>
        )}

        {!error && (
          <section className="rounded-2xl border bg-white p-5 shadow">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-gray-900">Gemini AI Recommendations</h2>
              {loading && <span className="text-sm text-gray-500">Contacting Gemini…</span>}
            </div>
            {formattedAdvice.length === 0 && !loading && (
              <p className="mt-4 text-sm text-gray-500">No advice is available yet. Try generating again once sensor data is ingested.</p>
            )}
            <div className="mt-4 space-y-4 text-sm text-gray-800">
              {formattedAdvice.map((section, index) => (
                <div key={index} className="rounded-xl bg-gray-50 p-4 leading-relaxed">
                  {section.map((block, idx) => {
                    if (block.kind === 'heading') {
                      const headingClass =
                        block.level <= 2
                          ? 'text-base font-semibold text-gray-900'
                          : 'text-sm font-semibold text-gray-700'
                      return (
                        <p key={idx} className={`${headingClass} mb-3 last:mb-0`}>
                          {block.content}
                        </p>
                      )
                    }

                    if (block.kind === 'list') {
                      const ListTag: 'ol' | 'ul' = block.ordered ? 'ol' : 'ul'
                      return (
                        <ListTag
                          key={idx}
                          className={`mb-3 list-inside space-y-1 last:mb-0 ${block.ordered ? 'list-decimal' : 'list-disc'}`}
                        >
                          {block.items.map((item, itemIdx) => (
                            <li key={itemIdx} className="marker:text-gray-400">
                              {item}
                            </li>
                          ))}
                        </ListTag>
                      )
                    }

                    return (
                      <p key={idx} className="mb-3 last:mb-0 text-gray-700">
                        {block.content}
                      </p>
                    )
                  })}
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-2xl border bg-white p-5 shadow">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900">Sensor Snapshot</h2>
            {!loading && snapshots.length > 0 && (
              <span className="text-xs text-gray-500">{snapshots.length} sensors analysed</span>
            )}
          </div>
          {loading && snapshots.length === 0 && (
            <div className="mt-4 text-sm text-gray-500">Loading latest readings…</div>
          )}
          {!loading && snapshots.length === 0 && (
            <div className="mt-4 text-sm text-gray-500">
              No sensor data found. Add sensors or ingest readings to receive tailored advice.
            </div>
          )}
          {snapshots.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
                <thead>
                  <tr className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-3 py-2">Sensor</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Location</th>
                    <th className="px-3 py-2">House</th>
                    <th className="px-3 py-2">Latest Value</th>
                    <th className="px-3 py-2">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {snapshots.map(snapshot => {
                    const formattedTs = formatTimestamp(snapshot.latest_ts ?? null)
                    return (
                      <tr key={snapshot.id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 font-medium text-gray-900">{snapshot.name}</td>
                        <td className="px-3 py-2 text-gray-600">{snapshot.type}</td>
                        <td className="px-3 py-2 text-gray-600">{snapshot.location || '—'}</td>
                        <td className="px-3 py-2 text-gray-600">{snapshot.house_id || '—'}</td>
                        <td className="px-3 py-2 text-gray-600">
                          {snapshot.latest_value !== null && snapshot.latest_value !== undefined
                            ? snapshot.latest_value
                            : '—'}
                        </td>
                        <td className="px-3 py-2 text-gray-500">{formattedTs || '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

