import { useEffect, useMemo, useState } from 'react'
import type { Sensor } from '../types/sensors'
import formatTimestamp from '../utils/formatTimestamp'

type SensorCardProps = {
  x: Sensor
  apiBase: string
  onSensorUpdated?: (sensor: Sensor) => void
}

type Reading = {
  value: string | null
  ts: string | null
}

const getEnabled = (sensor: Sensor): boolean => {
  const meta = sensor.meta ?? {}
  if (typeof meta === 'object' && meta !== null && 'enabled' in meta) {
    const enabled = (meta as { enabled?: unknown }).enabled
    if (typeof enabled === 'boolean') {
      return enabled
    }
  }
  return true
}

const formatErrorMessage = async (response: Response) => {
  try {
    const data = await response.json()
    if (typeof data === 'object' && data !== null) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  } catch (error) {
    console.error('Failed to parse error response', error)
  }
  return response.statusText || 'Request failed'
}

export default function SensorCard({ x, apiBase, onSensorUpdated }: SensorCardProps) {
  const [isEnabled, setIsEnabled] = useState<boolean>(getEnabled(x))
  const [reading, setReading] = useState<Reading>({ value: null, ts: null })
  const [readingError, setReadingError] = useState<string | null>(null)
  const [isUpdating, setIsUpdating] = useState<boolean>(false)
  const [toggleError, setToggleError] = useState<string | null>(null)

  useEffect(() => {
    setIsEnabled(getEnabled(x))
  }, [x])

  useEffect(() => {
    let alive = true

    const fetchLatestReading = async () => {
      try {
        setReadingError(null)
        const res = await fetch(`${apiBase}/api/readings/query`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ sensor_id: x.id, limit: 1 }),
        })
        if (!res.ok) {
          throw new Error(await formatErrorMessage(res))
        }
        const data = await res.json()
        if (!alive) return
        if (Array.isArray(data) && data.length > 0) {
          const latest = data[data.length - 1] as { value?: unknown; ts?: unknown }
          const value = latest?.value
          setReading({
            value: value === null || value === undefined ? null : String(value),
            ts: typeof latest?.ts === 'string' ? latest.ts : null,
          })
        } else {
          setReading({ value: null, ts: null })
        }
      } catch (error) {
        if (!alive) return
        const message = error instanceof Error ? error.message : 'Failed to load reading'
        setReadingError(message)
        setReading({ value: null, ts: null })
      }
    }

    fetchLatestReading()
    const timer = setInterval(fetchLatestReading, 60_000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [apiBase, x.id])

  const formattedTs = useMemo(() => formatTimestamp(reading.ts), [reading.ts])

  const statusBadgeClass = isEnabled
    ? 'bg-green-100 text-green-800 border-green-200'
    : 'bg-gray-100 text-gray-600 border-gray-200'

  const handleToggle = async () => {
    setToggleError(null)
    setIsUpdating(true)
    const next = !isEnabled
    try {
      const res = await fetch(`${apiBase}/sensors/${x.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled: next }),
      })
      if (!res.ok) {
        throw new Error(await formatErrorMessage(res))
      }
      const updated = (await res.json()) as Sensor
      setIsEnabled(getEnabled(updated))
      onSensorUpdated?.(updated)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update sensor'
      setToggleError(message)
    } finally {
      setIsUpdating(false)
    }
  }

  return (
    <div className="rounded-2xl bg-white shadow p-4 border">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-gray-900">{x.name}</div>
          <div className="mt-1 text-sm text-gray-600">Location: {x.location || '-'}</div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className={`text-xs rounded-full border px-2 py-1 ${statusBadgeClass}`}>
            {isEnabled ? 'Enabled' : 'Disabled'}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-gray-500">{x.type}</span>
        </div>
      </div>

      <div className="mt-4 space-y-4 text-sm">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Current Reading</span>
            {!readingError && formattedTs && (
              <span className="text-[11px] text-gray-400">Updated {formattedTs}</span>
            )}
          </div>
          <div
            className={`rounded-2xl px-5 py-4 shadow-inner transition-colors ${
              readingError
                ? 'bg-red-100 text-red-800'
                : 'bg-white text-gray-900 border border-gray-200'
            }`}
          >
            <div className="flex items-baseline gap-3">
              <span className="text-5xl font-extrabold leading-none tracking-tight text-black">
                {reading.value ?? '--'}
              </span>
              <span className={`text-sm uppercase tracking-wide ${readingError ? 'text-red-700' : 'text-gray-500'}`}>
                {x.type}
              </span>
            </div>
          </div>
          <div className="text-xs">
            {readingError && <span className="text-red-600">{readingError}</span>}
            {!readingError && !formattedTs && <span className="text-gray-500">No recent data</span>}
          </div>
        </div>

        <div>
          <button
            type="button"
            onClick={handleToggle}
            disabled={isUpdating}
            className={`w-full rounded-xl border px-3 py-2 font-medium transition ${
              isEnabled
                ? 'border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-60'
                : 'border-green-300 text-green-600 hover:bg-green-50 disabled:opacity-60'
            }`}
          >
            {isEnabled ? 'Disable sensor' : 'Enable sensor'}
          </button>
          {toggleError && <div className="mt-1 text-xs text-red-600">{toggleError}</div>}
        </div>

        <div>
          <div className="text-sm font-medium mb-1 text-gray-800">Meta</div>
          {x.meta && Object.keys(x.meta).length > 0 ? (
            <dl className="divide-y divide-gray-100 overflow-hidden rounded-xl border">
              {Object.entries(x.meta).map(([key, value]) => {
                const formattedValue = (() => {
                  if (value === null || value === undefined) return '—'
                  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
                  if (typeof value === 'number') return value.toString()
                  if (typeof value === 'string') return value
                  try {
                    return JSON.stringify(value, null, 2)
                  } catch (error) {
                    console.error('Failed to render meta value', error)
                    return String(value)
                  }
                })()

                const isStructuredValue = typeof value === 'object' && value !== null

                return (
                  <div key={key} className="bg-white px-3 py-2 text-xs text-gray-700">
                    <dt className="font-semibold text-gray-900">{key}</dt>
                    <dd className="mt-1 whitespace-pre-wrap break-words text-gray-600">
                      {isStructuredValue ? (
                        <code className="block whitespace-pre-wrap break-words text-left text-[11px]">
                          {formattedValue}
                        </code>
                      ) : (
                        formattedValue
                      )}
                    </dd>
                  </div>
                )
              })}
            </dl>
          ) : (
            <div className="text-xs text-gray-500">No metadata available</div>
          )}
        </div>
      </div>
    </div>
  )
}
