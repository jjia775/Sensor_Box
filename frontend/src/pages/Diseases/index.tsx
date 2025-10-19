import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createDisease,
  deleteDisease,
  fetchDiseases,
  type Disease,
  type DiseasePayload,
  type DiseaseUpdatePayload,
  updateDisease,
} from '../../api/diseases'
import { useApiBase } from '../../hooks/useApiBase'

type MetricOption = {
  metric: string
  unit?: string
}

type MetricResponse = {
  metric?: string
  unit?: string
}

type FormState = {
  key: string
  name: string
  metrics: string[]
}

const EMPTY_FORM: FormState = { key: '', name: '', metrics: [] }

export default function DiseasesConfigPage() {
  const API_BASE = useApiBase()
  const [diseases, setDiseases] = useState<Disease[]>([])
  const [metricOptions, setMetricOptions] = useState<MetricOption[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(() => ({ ...EMPTY_FORM }))
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [lastHouseId, setLastHouseId] = useState('')

  useEffect(() => {
    if (typeof window === 'undefined') return
    setLastHouseId(window.localStorage.getItem('house_id') || '')
  }, [])

  const loadDiseases = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await fetchDiseases(API_BASE)
      setDiseases(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load diseases')
    } finally {
      setLoading(false)
    }
  }, [API_BASE])

  useEffect(() => {
    loadDiseases()
  }, [loadDiseases])

  useEffect(() => {
    let alive = true
    fetch(`${API_BASE}/api/charts/metrics`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then(data => {
        if (!alive) return
        const seen = new Set<string>()
        const options: MetricOption[] = []
        const rawMetrics: MetricResponse[] = Array.isArray(data?.metrics) ? data.metrics : []
        for (const item of rawMetrics) {
          const metric = String(item?.metric || '').trim().toLowerCase()
          if (!metric || seen.has(metric)) continue
          seen.add(metric)
          options.push({
            metric,
            unit: item?.unit ? String(item.unit) : undefined,
          })
        }
        options.sort((a, b) => a.metric.localeCompare(b.metric, 'zh-CN', { sensitivity: 'base' }))
        setMetricOptions(options)
      })
      .catch(() => {
        if (!alive) return
        setMetricOptions([])
      })
    return () => {
      alive = false
    }
  }, [API_BASE])

  useEffect(() => {
    if (!success) return
    const timer = window.setTimeout(() => setSuccess(null), 4000)
    return () => window.clearTimeout(timer)
  }, [success])

  const selectedMetrics = useMemo(() => new Set(form.metrics.map(m => m.toLowerCase())), [form.metrics])
  const isEditing = editingKey !== null
  const canSubmit = form.name.trim() && selectedMetrics.size > 0 && (isEditing || form.key.trim())

  const startCreate = () => {
    setEditingKey(null)
    setForm({ ...EMPTY_FORM })
    setError(null)
    setSuccess(null)
  }

  const startEdit = (disease: Disease) => {
    setEditingKey(disease.key)
    setForm({
      key: disease.key,
      name: disease.name,
      metrics: Array.from(new Set(disease.metrics.map(metric => metric.toLowerCase()))),
    })
    setError(null)
    setSuccess(null)
  }

  const toggleMetric = (metric: string) => {
    setForm(prev => {
      const normalized = metric.toLowerCase()
      const has = prev.metrics.some(m => m.toLowerCase() === normalized)
      const metrics = has
        ? prev.metrics.filter(m => m.toLowerCase() !== normalized)
        : [...prev.metrics, metric]
      return { ...prev, metrics }
    })
  }

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return

    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const metrics = Array.from(new Set(form.metrics.map(metric => metric.toLowerCase())))
      if (metrics.length !== form.metrics.length) {
        setForm(prev => ({ ...prev, metrics }))
      }
      if (isEditing && editingKey) {
        const payload: DiseaseUpdatePayload = {
          name: form.name,
          metrics,
        }
        await updateDisease(API_BASE, editingKey, payload)
        setSuccess('Disease updated')
      } else {
        const payload: DiseasePayload = {
          key: form.key,
          name: form.name,
          metrics,
        }
        await createDisease(API_BASE, payload)
        setSuccess('Disease created')
        setForm({ ...EMPTY_FORM })
      }
      await loadDiseases()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Operation failed, please try again later')
    } finally {
      setSaving(false)
    }
  }

  const removeDisease = async (key: string) => {
    if (!window.confirm('Are you sure you want to delete this disease configuration? This action cannot be undone.')) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await deleteDisease(API_BASE, key)
      if (editingKey === key) {
        startCreate()
      }
      await loadDiseases()
      setSuccess('Disease deleted')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete, please try again later')
    } finally {
      setSaving(false)
    }
  }

  const sortedDiseases = useMemo(
    () =>
      [...diseases].sort((a, b) => a.name.localeCompare(b.name, 'en-US', { sensitivity: 'base' })),
    [diseases]
  )

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold text-gray-900">Disease Configuration</h1>
          <div className="flex gap-2">
            {lastHouseId ? (
              <Link
                to={`/dashboard/${encodeURIComponent(lastHouseId)}`}
                className="rounded-xl border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                Back to Dashboard
              </Link>
            ) : (
              <Link
                to="/login"
                className="rounded-xl border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              >
                Back to Login
              </Link>
            )}
            <button
              onClick={startCreate}
              className="rounded-xl border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
              type="button"
            >
              Create Disease
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700">
            <div className="font-semibold">Error</div>
            <div className="text-sm whitespace-pre-wrap">{error}</div>
          </div>
        )}

        {success && (
          <div className="rounded-2xl border border-green-200 bg-green-50 p-4 text-green-700">
            {success}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr]">
          <section className="rounded-2xl border bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Disease List</h2>
                <p className="text-sm text-gray-500">Manage all diseases and their associated environmental metrics.</p>
              </div>
              <span className="text-sm text-gray-400">{sortedDiseases.length} diseases</span>
            </div>

            {loading ? (
              <div className="text-sm text-gray-500">Loading disease list…</div>
            ) : sortedDiseases.length === 0 ? (
              <div className="rounded-xl border border-dashed p-6 text-center text-sm text-gray-500">
                No diseases configured yet. Click "Create Disease" above to get started.
              </div>
            ) : (
              <div className="space-y-4">
                {sortedDiseases.map(disease => (
                  <div
                    key={disease.key}
                    className={`rounded-xl border p-4 transition-shadow ${
                      editingKey === disease.key ? 'border-blue-400 shadow' : 'border-gray-200 hover:shadow'
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-gray-900">{disease.name}</div>
                        <div className="text-xs uppercase tracking-wide text-gray-500">{disease.key}</div>
                      </div>
                      <div className="flex gap-2 text-sm">
                        <button
                          onClick={() => startEdit(disease)}
                          className="rounded-lg border px-3 py-1 text-gray-700 hover:bg-gray-100"
                          type="button"
                          disabled={saving}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => removeDisease(disease.key)}
                          className="rounded-lg border border-red-200 px-3 py-1 text-red-600 hover:bg-red-50"
                          type="button"
                          disabled={saving}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {disease.metrics.map(metric => (
                        <span
                          key={metric}
                          className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700"
                        >
                          {metric.toUpperCase()}
                        </span>
                      ))}
                      {disease.metrics.length === 0 && (
                        <span className="text-xs text-gray-500">No metrics selected</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-2xl border bg-white p-6 shadow-sm">
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">{isEditing ? 'Edit Disease' : 'Create Disease'}</h2>
                <p className="text-sm text-gray-500">
                  {isEditing
                    ? 'Update the disease name or the associated sensor metrics.'
                    : 'Provide a unique key, name, and metrics of interest for the new disease.'}
                </p>
              </div>

              {!isEditing && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Disease Key</label>
                  <input
                    className="w-full rounded-xl border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                    placeholder="e.g. asthma"
                    value={form.key}
                    onChange={e => setForm(prev => ({ ...prev, key: e.target.value }))}
                    disabled={saving}
                    required={!isEditing}
                  />
                  <p className="mt-1 text-xs text-gray-400">Key must be unique and is used internally.</p>
                </div>
              )}

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Disease Name</label>
                <input
                  className="w-full rounded-xl border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  placeholder="Enter a display name"
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                  disabled={saving}
                  required
                />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <label className="text-sm font-medium text-gray-700">Associated Sensor Metrics</label>
                  <span className="text-xs text-gray-400">Selected {selectedMetrics.size} items</span>
                </div>
                {metricOptions.length === 0 ? (
                  <div className="rounded-xl border border-dashed p-4 text-center text-xs text-gray-500">
                    No metrics available yet. Configure sensor thresholds first.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {metricOptions.map(option => {
                      const checked = selectedMetrics.has(option.metric)
                      return (
                        <label
                          key={option.metric}
                          className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm transition ${
                            checked ? 'border-blue-400 bg-blue-50 text-blue-700' : 'border-gray-200 hover:border-gray-400'
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-gray-300 text-blue-600"
                            checked={checked}
                            onChange={() => toggleMetric(option.metric)}
                            disabled={saving}
                          />
                          <span className="font-medium">{option.metric.toUpperCase()}</span>
                          {option.unit && <span className="text-xs text-gray-500">({option.unit})</span>}
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>

              <button
                type="submit"
                className="w-full rounded-xl bg-black py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-gray-400"
                disabled={!canSubmit || saving}
              >
                {saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Create Disease'}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  )
}
