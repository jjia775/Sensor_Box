import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { MetricInfo, MetricsResp, ScatterResp } from '../../types/charts'
import type { Sensor } from '../../types/sensors'
import { METRIC_LABELS } from './config'
import { formatISO, getSerial } from './utils'
import ScatterPlotSVG from './ScatterPlotSVG'
import type { ScatterSection } from '../../types/report'

export type ScatterPanelHandle = {
  getReportSection: () => Promise<ScatterSection | null>
}

type RangeOpt = '6h' | '12h' | '24h'

type LoadState = 'idle' | 'loading' | 'error' | 'success'

type Props = {
  apiBase: string
  houseId: string
  allowedMetrics?: string[]
}

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

const ScatterPanel = forwardRef<ScatterPanelHandle, Props>(({ apiBase, houseId, allowedMetrics }, ref) => {
  const [metrics, setMetrics] = useState<MetricInfo[]>([])
  const [serials, setSerials] = useState<string[]>([])

  const [serial, setSerial] = useState('')
  const [xMetric, setXMetric] = useState('')
  const [yMetric, setYMetric] = useState('')
  const [range, setRange] = useState<RangeOpt>('24h')
  const [interval, setInterval] = useState('5m')

  const [state, setState] = useState<LoadState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ScatterResp | null>(null)
  const chartContainerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`${apiBase}/api/charts/metrics`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((d: MetricsResp) => {
        if (!alive) return
        setMetrics(d.metrics || [])
      })
      .catch(() => setMetrics([]))
    return () => {
      alive = false
    }
  }, [apiBase])

  const filteredMetrics = useMemo(() => {
    if (!metrics.length) return []
    if (!allowedMetrics || !allowedMetrics.length) return metrics
    const allow = new Set(allowedMetrics.map(m => m.toLowerCase()))
    return metrics.filter(m => allow.has(m.metric.toLowerCase()))
  }, [metrics, allowedMetrics])

  useEffect(() => {
    if (!filteredMetrics.length) {
      setXMetric('')
      setYMetric('')
      return
    }
    if (!xMetric || !filteredMetrics.find(m => m.metric === xMetric)) {
      setXMetric(filteredMetrics[0].metric)
    }
    if (!yMetric || !filteredMetrics.find(m => m.metric === yMetric)) {
      const fallback = filteredMetrics[1]?.metric || filteredMetrics[0].metric
      setYMetric(fallback)
    }
  }, [filteredMetrics]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!houseId) {
      setSerials([])
      setSerial('')
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
        const key = `scatter_sensor_serial:${houseId}`
        const prev = localStorage.getItem(key)
        const initial = prev && uniq.includes(prev) ? prev : uniq[0] || ''
        setSerial(initial)
      })
      .catch(() => {
        setSerials([])
        setSerial('')
      })
  }, [apiBase, houseId])

  const noMetricReason = useMemo(() => {
    if ((metrics?.length || 0) === 0) return 'Failed to load available metrics'
    if (allowedMetrics && allowedMetrics.length > 0 && filteredMetrics.length === 0) return 'The selected disease is not associated with any metrics'
    return ''
  }, [metrics, allowedMetrics, filteredMetrics])

  const loadScatter = async () => {
    if (!serial) {
      setError('No sensor serial available')
      setState('error')
      return
    }
    if (!xMetric || !yMetric) {
      setError('No metrics available (check disease settings)')
      setState('error')
      return
    }

    setState('loading')
    setError(null)
    setData(null)

    const now = new Date()
    const end = now
    const start = new Date(
      range === '24h'
        ? now.getTime() - 24 * 3600_000
        : range === '12h'
        ? now.getTime() - 12 * 3600_000
        : now.getTime() - 6 * 3600_000,
    )

    try {
      const payload = {
        serial_number: serial,
        x_metric: xMetric,
        y_metric: yMetric,
        start_ts: formatISO(start),
        end_ts: formatISO(end),
        interval,
        agg: 'avg',
        title: `${METRIC_LABELS[yMetric] ?? yMetric.toUpperCase()} vs ${METRIC_LABELS[xMetric] ?? xMetric.toUpperCase()}`,
      }
      const r = await fetch(`${apiBase}/api/charts/metric_scatter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())
      const d: ScatterResp = await r.json()
      setData(d)
      setState('success')
      localStorage.setItem(`scatter_sensor_serial:${houseId}`, serial)
    } catch (e: any) {
      setState('error')
      setError(e?.message || 'Failed to load scatter data')
    }
  }

  useImperativeHandle(
    ref,
    () => ({
      async getReportSection() {
        if (!data || !chartContainerRef.current) return null
        const svg = chartContainerRef.current.querySelector('svg')
        const dataUrl = svgToDataUrl(svg)
        if (!dataUrl) return null
        return {
          kind: 'scatter',
          title: data.title,
          imageDataUrl: dataUrl,
          filters: {
            serial,
            xMetric,
            yMetric,
            interval,
            range,
          },
          data,
        }
      },
    }),
    [data, interval, range, serial, xMetric, yMetric],
  )

  return (
    <div className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm space-y-6">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div>
            <label className="block text-sm font-medium mb-1">Sensor Serial</label>
            <select className="w-full rounded-xl border px-3 py-2" value={serial} onChange={e => setSerial(e.target.value)}>
              {serials.length === 0 && <option value="">No serials</option>}
              {serials.map(s => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">X Metric</label>
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={xMetric}
              onChange={e => setXMetric(e.target.value)}
              disabled={filteredMetrics.length === 0}
            >
              {filteredMetrics.length === 0 && <option value="">No metrics</option>}
              {filteredMetrics.map(m => (
                <option key={m.metric} value={m.metric}>
                  {METRIC_LABELS[m.metric] ?? m.metric.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Y Metric</label>
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={yMetric}
              onChange={e => setYMetric(e.target.value)}
              disabled={filteredMetrics.length === 0}
            >
              {filteredMetrics.length === 0 && <option value="">No metrics</option>}
              {filteredMetrics.map(m => (
                <option key={m.metric} value={m.metric}>
                  {METRIC_LABELS[m.metric] ?? m.metric.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Range</label>
            <select className="w-full rounded-xl border px-3 py-2" value={range} onChange={e => setRange(e.target.value as RangeOpt)}>
              <option value="6h">Last 6h</option>
              <option value="12h">Last 12h</option>
              <option value="24h">Last 24h</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Interval</label>
            <select className="w-full rounded-xl border px-3 py-2" value={interval} onChange={e => setInterval(e.target.value)}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="30m">30m</option>
              <option value="1h">1h</option>
            </select>
          </div>
        </div>
        {noMetricReason && <div className="text-xs text-amber-700">{noMetricReason}</div>}
        <div className="flex items-center gap-3">
          <button
            onClick={loadScatter}
            className="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
            disabled={state === 'loading' || filteredMetrics.length === 0}
          >
            {state === 'loading' ? 'Loading…' : 'Generate Scatter Plot'}
          </button>
          {state === 'error' && error && <span className="text-sm text-red-600">{error}</span>}
        </div>
      </div>
      {state === 'success' && data && (
        <div ref={chartContainerRef} className="rounded-2xl border border-gray-200 bg-white/90 p-6 shadow-sm">
          <ScatterPlotSVG
            title={data.title}
            unitX={data.unit_x}
            unitY={data.unit_y}
            points={data.points}
            bestFit={data.best_fit}
            xThresholds={data.x_thresholds}
            yThresholds={data.y_thresholds}
          />
        </div>
      )}
      {state === 'idle' && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white/60 p-6 text-sm text-gray-500">
          Choose parameters and click the button above to generate the scatter chart.
        </div>
      )}
    </div>
  )
})

export default ScatterPanel
