import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { MetricInfo, MetricsResp, TimeseriesResp } from '../../types/charts'
import type { Sensor } from '../../types/sensors'
import ChartSVG from './ChartSVG'
import { METRIC_LABELS } from './config'
import { formatISO, getSerial } from './utils'
import type { TimeseriesSection } from '../../types/report'

export type ChartsPanelHandle = {
  getReportSection: () => Promise<TimeseriesSection | null>
}

type Agg = 'avg' | 'min' | 'max' | 'last' | 'sum'
type RangeOpt = '6h' | '12h' | '24h'

// type Props = {
//   apiBase,
//   houseId,
//   allowedMetrics, // Allowed metrics associated with the disease (e.g. ['temp','co2'])
// }

type Props = {
  apiBase: string;
  houseId: string;
  allowedMetrics: string[]; // Allowed metrics associated with the disease
};


function svgToDataUrl(svg: SVGSVGElement | null): string | null {
  if (!svg) return null
  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(svg)
  const encoded = window.btoa(
    encodeURIComponent(source).replace(/%([0-9A-F]{2})/g, (_, p1) =>
      String.fromCharCode(Number.parseInt(p1, 16)),
    ),
  )
  return `data:image/svg+xml;base64,${encoded}`
}

const ChartsPanel = forwardRef<ChartsPanelHandle, Props>(({ apiBase, houseId, allowedMetrics }, ref) => {
  // All available metrics returned from the server
  const [allMetrics, setAllMetrics] = useState<MetricInfo[]>([])
  // Currently selected metric
  const [metric, setMetric] = useState<string>('')

  // Serial selection
  const [serials, setSerials] = useState<string[]>([])
  const [serial, setSerial] = useState<string>('')

  // Other query parameters
  const [interval, setInterval] = useState<string>('5m')
  const [agg, setAgg] = useState<Agg>('avg')
  const [range, setRange] = useState<RangeOpt>('24h')

  // Timeseries data and status
  const [tsLoading, setTsLoading] = useState(false)
  const [tsError, setTsError] = useState<string | null>(null)
  const [tsData, setTsData] = useState<TimeseriesResp | null>(null)
  const chartContainerRef = useRef<HTMLDivElement | null>(null)

  // Fetch all metrics
  useEffect(() => {
    let alive = true
    fetch(`${apiBase}/api/charts/metrics`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((d: MetricsResp) => {
        if (!alive) return
        setAllMetrics(d.metrics || [])
      })
      .catch(() => {
        setAllMetrics([]) // Fallback to empty on failure (UI below handles the empty state)
      })
    return () => { alive = false }
  }, [apiBase])

  // Filter available metrics according to allowedMetrics
  const filteredMetrics = useMemo<MetricInfo[]>(() => {
    if (!allMetrics?.length) return []
    if (!allowedMetrics || allowedMetrics.length === 0) return allMetrics
    const allow = new Set(allowedMetrics.map(m => m.toLowerCase()))
    return allMetrics.filter(m => allow.has(m.metric.toLowerCase()))
  }, [allMetrics, allowedMetrics])

  // When the available metrics change, switch to the first one if the current selection becomes invalid
  useEffect(() => {
    if (!filteredMetrics.length) {
      setMetric('')
      return
    }
    if (!metric || !filteredMetrics.find(m => m.metric === metric)) {
      setMetric(filteredMetrics[0].metric)
    }
  }, [filteredMetrics]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch all sensors for the household and extract unique serials
  useEffect(() => {
    if (!houseId) {
      setSerials([]); setSerial('')
      return
    }
    fetch(`${apiBase}/sensors/?house_id=${encodeURIComponent(houseId)}`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((arr: Sensor[]) => {
        const uniq: string[] = []
        const seen = new Set<string>()
        for (const s of arr) {
          const sn = getSerial(s)
          if (sn && !seen.has(sn)) {
            seen.add(sn)
            uniq.push(sn)
          }
        }
        setSerials(uniq)
        const key = `sensor_serial:${houseId}`
        const prev = localStorage.getItem(key)
        const initial = prev && uniq.includes(prev) ? prev : uniq[0] || ''
        setSerial(initial)
      })
      .catch(() => {
        setSerials([]); setSerial('')
      })
  }, [apiBase, houseId])

  // Request timeseries data
  const loadTimeseries = async () => {
    setTsLoading(true); setTsError(null); setTsData(null)
    try {
      if (!serial) throw new Error('No sensor serial available')
      if (!metric) throw new Error('No metric available (check disease settings)')

      const now = new Date()
      const end = now
      const start = new Date(
        range === '24h' ? now.getTime() - 24 * 3600_000
        : range === '12h' ? now.getTime() - 12 * 3600_000
        : now.getTime() - 6 * 3600_000
      )

        const payload = {
          serial_number: serial, // Search by serial ID
          metric,
          start_ts: formatISO(start),
          end_ts: formatISO(end),
          interval,
          agg,
          title: `${(METRIC_LABELS[metric] ?? metric.toUpperCase())} (${interval}, ${agg})`,
        }

      const r = await fetch(`${apiBase}/api/charts/metric_timeseries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())
      const d: TimeseriesResp = await r.json()
      setTsData(d)
      localStorage.setItem(`sensor_serial:${houseId}`, serial)
    } catch (e: any) {
      setTsError(e?.message || 'Failed to load timeseries')
    } finally {
      setTsLoading(false)
    }
  }

  // UI: handle cases where no metrics are available (e.g. disease config too narrow)
  const noMetricReason = useMemo(() => {
    if ((allMetrics?.length || 0) === 0) return 'Failed to load available metrics'
    if (allowedMetrics && allowedMetrics.length > 0 && filteredMetrics.length === 0) return 'The selected disease is not associated with any metrics'
    return ''
  }, [allMetrics, allowedMetrics, filteredMetrics])

  useImperativeHandle(
    ref,
    () => ({
      async getReportSection() {
        if (!tsData || !chartContainerRef.current) return null
        const svg = chartContainerRef.current.querySelector('svg')
        const dataUrl = svgToDataUrl(svg)
        if (!dataUrl) return null
        return {
          kind: 'timeseries',
          title: tsData.title,
          imageDataUrl: dataUrl,
          filters: {
            serial,
            metric,
            interval,
            aggregate: agg,
            range,
          },
          data: tsData,
        }
      },
    }),
    [agg, interval, metric, range, serial, tsData],
  )

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          {/* Serial selector */}
          <div>
            <label className="block text-sm font-medium mb-1">Sensor Serial</label>
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={serial}
              onChange={e => setSerial(e.target.value)}
            >
              {serials.length === 0 && <option value="">No serials</option>}
              {serials.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Metric selector (already filtered by allowedMetrics) */}
          <div>
            <label className="block text-sm font-medium mb-1">Metric</label>
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={metric}
              onChange={e => setMetric(e.target.value)}
              disabled={filteredMetrics.length === 0}
            >
              {filteredMetrics.length === 0 && <option value="">No metrics</option>}
              {filteredMetrics.map(m => (
                <option key={m.metric} value={m.metric}>
                  {METRIC_LABELS[m.metric] ?? m.metric.toUpperCase()}
                </option>
              ))}
            </select>
            {noMetricReason && (
              <div className="mt-1 text-xs text-amber-700">{noMetricReason}</div>
            )}
          </div>

          {/* Interval */}
          <div>
            <label className="block text-sm font-medium mb-1">Interval</label>
            <select className="w-full rounded-xl border px-3 py-2" value={interval} onChange={e => setInterval(e.target.value)}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
            </select>
          </div>

          {/* Aggregate */}
          <div>
            <label className="block text-sm font-medium mb-1">Aggregate</label>
            <select className="w-full rounded-xl border px-3 py-2" value={agg} onChange={e => setAgg(e.target.value as Agg)}>
              <option value="avg">avg</option>
              <option value="min">min</option>
              <option value="max">max</option>
              <option value="last">last</option>
              <option value="sum">sum</option>
            </select>
          </div>

          {/* Range */}
          <div>
            <label className="block text-sm font-medium mb-1">Range</label>
            <select className="w-full rounded-xl border px-3 py-2" value={range} onChange={e => setRange(e.target.value as RangeOpt)}>
              <option value="6h">Last 6h</option>
              <option value="12h">Last 12h</option>
              <option value="24h">Last 24h</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={loadTimeseries}
            disabled={!serial || !metric || tsLoading || filteredMetrics.length === 0}
            className="rounded-xl bg-black text-white px-4 py-2 disabled:opacity-60"
          >
            {tsLoading ? 'Loading...' : 'Load Chart'}
          </button>
        </div>

        {tsError && <div className="mt-3 rounded-xl border bg-red-50 p-3 text-sm text-red-800">{tsError}</div>}
      </div>

      {tsData && (
        <div ref={chartContainerRef} className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm">
          <ChartSVG
            labels={tsData.labels}
            data={tsData.series?.[0]?.data || []}
            thresholds={tsData.thresholds || []}
            unit={tsData.unit}
            title={tsData.title}
          />
        </div>
      )}
    </div>
  )
})

export default ChartsPanel
