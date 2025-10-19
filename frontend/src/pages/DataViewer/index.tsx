import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useApiBase } from '../../hooks/useApiBase'
import type { Sensor } from '../../types/sensors'
import formatTimestamp from '../../utils/formatTimestamp'

type Reading = {
  id: number
  sensor_id: string
  ts: string
  value: number
  attributes?: Record<string, unknown> | null
}

const LIMIT_MAX = 10000

type Household = {
  id: number
  house_id: string
  householder: string
  phone: string
  email: string
  address: string
  zone: string
}

function formatAttributes(attributes?: Record<string, unknown> | null) {
  if (!attributes || Object.keys(attributes).length === 0) {
    return '—'
  }
  try {
    return JSON.stringify(attributes, null, 2)
  } catch (err) {
    return String(attributes)
  }
}

export default function DataViewerPage() {
  const API_BASE = useApiBase()
  const getStoredHouseId = () => (typeof window !== 'undefined' ? localStorage.getItem('house_id') || '' : '')
  const [houseIdInput, setHouseIdInput] = useState(getStoredHouseId)
  const [houseId, setHouseId] = useState(getStoredHouseId)

  const [households, setHouseholds] = useState<Household[]>([])
  const [householdsLoading, setHouseholdsLoading] = useState(false)
  const [householdsError, setHouseholdsError] = useState<string | null>(null)

  const [sensors, setSensors] = useState<Sensor[]>([])
  const [sensorsLoading, setSensorsLoading] = useState(false)
  const [sensorsError, setSensorsError] = useState<string | null>(null)

  const [selectedSensorId, setSelectedSensorId] = useState('')
  const [startTs, setStartTs] = useState('')
  const [endTs, setEndTs] = useState('')
  const [limit, setLimit] = useState('500')

  const [readings, setReadings] = useState<Reading[]>([])
  const [readingsLoading, setReadingsLoading] = useState(false)
  const [readingsError, setReadingsError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setHouseholdsLoading(true)
    setHouseholdsError(null)

    fetch(`${API_BASE}/api/households?limit=500`, { signal: controller.signal })
      .then(async res => {
        if (!res.ok) {
          throw new Error(await res.text())
        }
        return res.json() as Promise<Household[]>
      })
      .then(data => {
        setHouseholds(data)
      })
      .catch(err => {
        if (err.name === 'AbortError') return
        setHouseholdsError(err?.message || 'Failed to load households')
      })
      .finally(() => setHouseholdsLoading(false))

    return () => controller.abort()
  }, [API_BASE])

  useEffect(() => {
    const controller = new AbortController()
    setSensorsLoading(true)
    setSensorsError(null)
    setReadingsError(null)

    const params = new URLSearchParams({ limit: '500' })
    if (houseId) {
      params.set('house_id', houseId)
    }

    fetch(`${API_BASE}/sensors/?${params.toString()}`, { signal: controller.signal })
      .then(async res => {
        if (!res.ok) {
          throw new Error(await res.text())
        }
        return res.json() as Promise<Sensor[]>
      })
      .then(data => {
        setSensors(data)
        setSelectedSensorId(prev => {
          if (prev && data.some(sensor => sensor.id === prev)) {
            return prev
          }
          return data[0]?.id ?? ''
        })
        if (data.length === 0) {
          setReadings([])
        }
      })
      .catch(err => {
        if (err.name === 'AbortError') return
        setSensorsError(err?.message || 'Failed to load sensors')
      })
      .finally(() => setSensorsLoading(false))

    return () => controller.abort()
  }, [houseId, API_BASE])

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

  const handleLoadReadings = async () => {
    if (!selectedSensorId) {
      setReadings([])
      return
    }

    const parsedLimit = Number(limit) || 0
    if (parsedLimit <= 0 || parsedLimit > LIMIT_MAX) {
      setReadingsError(`Limit must be between 1 and ${LIMIT_MAX}`)
      return
    }

    setReadingsLoading(true)
    setReadingsError(null)
    try {
      const payload: Record<string, unknown> = {
        sensor_id: selectedSensorId,
        limit: parsedLimit,
      }
      if (startTs) payload.start_ts = startTs
      if (endTs) payload.end_ts = endTs

      const res = await fetch(`${API_BASE}/api/readings/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        throw new Error(await res.text())
      }
      const data = (await res.json()) as Reading[]
      setReadings(data)
    } catch (err) {
      setReadings([])
      setReadingsError(err instanceof Error ? err.message : 'Failed to load readings')
    } finally {
      setReadingsLoading(false)
    }
  }

  const downloadUrl = useMemo(() => {
    if (!selectedSensorId) return ''
    const params = new URLSearchParams({ sensor_id: selectedSensorId })
    const parsedLimit = Number(limit) || 0
    if (parsedLimit <= 0 || parsedLimit > LIMIT_MAX) {
      return ''
    }
    params.set('limit', String(parsedLimit))
    if (startTs) params.set('start_ts', startTs)
    if (endTs) params.set('end_ts', endTs)
    return `${API_BASE}/api/readings/export?${params.toString()}`
  }, [API_BASE, selectedSensorId, startTs, endTs, limit])

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Data Viewer</h1>
            <p className="text-sm text-gray-500">Inspect sensor readings and download them as CSV.</p>
          </div>
          <div className="flex gap-2">
            <Link to={houseId ? `/dashboard/${houseId}` : '/'} className="rounded-xl border px-4 py-2 hover:bg-gray-100">
              Back to Dashboard
            </Link>
            <Link to="/diseases" className="rounded-xl border px-4 py-2 hover:bg-gray-100">
              Disease Config
            </Link>
          </div>
        </div>

        <div className="rounded-2xl bg-white border shadow p-4">
          <form onSubmit={handleApplyHouseId} className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">House ID</label>
              <input
                value={houseIdInput}
                onChange={event => setHouseIdInput(event.target.value)}
                className="mt-1 w-64 rounded-lg border px-3 py-2 focus:outline-none focus:ring"
                placeholder="Enter house id"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Householder</label>
              <select
                className="mt-1 w-64 rounded-lg border px-3 py-2 focus:outline-none focus:ring"
                value={houseId}
                onChange={event => handleSelectHouseId(event.target.value)}
                disabled={householdsLoading}
              >
                <option value="">All households</option>
                {households.map(household => (
                  <option key={household.id} value={household.house_id}>
                    {household.householder} ({household.house_id})
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" className="rounded-xl border bg-black text-white px-4 py-2 hover:opacity-90">
              Apply
            </button>
            <div className="text-sm text-gray-500">API base: {API_BASE}</div>
          </form>
          {householdsLoading && <div className="mt-3 text-sm text-gray-500">Loading households…</div>}
          {householdsError && (
            <div className="mt-3 rounded-lg border bg-yellow-50 p-3 text-sm text-yellow-700">{householdsError}</div>
          )}
          {sensorsError && (
            <div className="mt-3 rounded-lg border bg-red-50 p-3 text-sm text-red-700">{sensorsError}</div>
          )}
        </div>

        <div className="rounded-2xl bg-white border shadow p-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700">Sensor</label>
              <select
                className="mt-1 w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring"
                value={selectedSensorId}
                onChange={event => setSelectedSensorId(event.target.value)}
                disabled={sensorsLoading || sensors.length === 0}
              >
                {sensors.map(sensor => (
                  <option key={sensor.id} value={sensor.id}>
                    {sensor.name} ({sensor.type}) — {sensor.householder ?? 'Unknown'}
                    {sensor.house_id ? ` [${sensor.house_id}]` : ''}
                  </option>
                ))}
                {sensors.length === 0 && <option value="">No sensors available</option>}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Start (ISO 8601)</label>
              <input
                type="datetime-local"
                value={startTs}
                onChange={event => setStartTs(event.target.value)}
                className="mt-1 w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">End (ISO 8601)</label>
              <input
                type="datetime-local"
                value={endTs}
                onChange={event => setEndTs(event.target.value)}
                className="mt-1 w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Limit</label>
              <input
                type="number"
                min={1}
                max={LIMIT_MAX}
                value={limit}
                onChange={event => setLimit(event.target.value)}
                className="mt-1 w-full rounded-lg border px-3 py-2 focus:outline-none focus:ring"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleLoadReadings}
              className="rounded-xl bg-black px-4 py-2 text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={sensorsLoading || !selectedSensorId}
              type="button"
            >
              {readingsLoading ? 'Loading…' : 'Load Readings'}
            </button>
            <button
              onClick={() => downloadUrl && window.open(downloadUrl, '_blank')}
              className="rounded-xl border px-4 py-2 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!downloadUrl}
              type="button"
            >
              Download CSV
            </button>
            {sensorsLoading && <span className="text-sm text-gray-500">Loading sensors…</span>}
          </div>

          {readingsError && (
            <div className="rounded-lg border bg-red-50 p-3 text-sm text-red-700">{readingsError}</div>
          )}

          <div className="overflow-auto rounded-xl border">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Timestamp</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Value</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Attributes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {readings.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-center text-gray-500">
                      {readingsLoading ? 'Loading readings…' : 'No readings loaded yet.'}
                    </td>
                  </tr>
                )}
                {readings.map(reading => (
                  <tr key={reading.id}>
                    <td className="px-3 py-2 whitespace-nowrap text-gray-700">
                      {formatTimestamp(reading.ts)}
                    </td>
                    <td className="px-3 py-2 text-gray-700">{reading.value}</td>
                    <td className="px-3 py-2">
                      <pre className="max-w-xl whitespace-pre-wrap break-words text-xs text-gray-600">
                        {formatAttributes(reading.attributes as Record<string, unknown> | null)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
