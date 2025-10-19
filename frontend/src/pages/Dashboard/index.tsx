import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApiBase } from '../../hooks/useApiBase'
import SensorGrid from '../../components/SensorGrid'
import ChartsPanel from '../../components/Chart/ChartsPanel'
import ScatterPanel from '../../components/Chart/ScatterPanel'
import RiskHeatmapPanel from '../../components/Chart/RiskHeatmapPanel'
import type { ChartsPanelHandle } from '../../components/Chart/ChartsPanel'
import type { ScatterPanelHandle } from '../../components/Chart/ScatterPanel'
import type { RiskHeatmapPanelHandle } from '../../components/Chart/RiskHeatmapPanel'
import type { Sensor } from '../../types/sensors'
import type { ReportSection } from '../../types/report'
import { downloadChartsReport } from '../../components/Chart/reportUtils'

type Disease = {
  key: string
  name: string
  metrics: string[]
}

export default function Dashboard() {
  const { houseId } = useParams()
  const API_BASE = useApiBase()

  const [tab, setTab] = useState<'sensors' | 'charts'>('sensors')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<Sensor[]>([])
  const [reportDownloading, setReportDownloading] = useState(false)

  // Disease list and current selection
  const [diseases, setDiseases] = useState<Disease[]>([])
  const [selectedDiseaseKey, setSelectedDiseaseKey] = useState<string>('')

  const chartsPanelRef = useRef<ChartsPanelHandle | null>(null)
  const scatterPanelRef = useRef<ScatterPanelHandle | null>(null)
  const heatmapPanelRef = useRef<RiskHeatmapPanelHandle | null>(null)

  const hid = houseId || localStorage.getItem('house_id') || ''

  // Fetch sensors for the current household
  useEffect(() => {
    if (!hid) {
      setError('Missing house_id')
      setLoading(false)
      return
    }
    localStorage.setItem('house_id', hid)
    const url = `${API_BASE}/sensors/?house_id=${encodeURIComponent(hid)}`
    fetch(url)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((data: Sensor[]) => setItems(data))
      .catch(e => setError(e?.message || 'Failed to load sensors'))
      .finally(() => setLoading(false))
  }, [hid, API_BASE])

  // Fetch disease list (needed before showing charts)
  useEffect(() => {
    let alive = true
    fetch(`${API_BASE}/api/diseases/`)
      .then(async r => {
        if (!r.ok) throw new Error(await r.text())
        return r.json()
      })
      .then((data) => {
        if (!alive) return
        const list: Disease[] = data?.diseases ?? []
        setDiseases(list)
        // Restore the previous selection or default to the first disease
        const saved = localStorage.getItem('disease_key') || ''
        const initKey = list.find(d => d.key === saved)?.key || list[0]?.key || ''
        setSelectedDiseaseKey(initKey)
      })
      .catch(() => setDiseases([]))
    return () => { alive = false }
  }, [API_BASE])

  const selectedDisease = useMemo(
    () => diseases.find(d => d.key === selectedDiseaseKey),
    [diseases, selectedDiseaseKey]
  )

  const handleDownloadReport = async () => {
    if (reportDownloading) return
    setReportDownloading(true)
    try {
      const sections: ReportSection[] = []
      const lineSection = await chartsPanelRef.current?.getReportSection()
      if (lineSection) sections.push(lineSection)
      const scatterSection = await scatterPanelRef.current?.getReportSection()
      if (scatterSection) sections.push(scatterSection)
      const heatmapSection = await heatmapPanelRef.current?.getReportSection()
      if (heatmapSection) sections.push(heatmapSection)

      if (sections.length === 0) {
        window.alert('Load at least one chart before exporting the report.')
        return
      }

      downloadChartsReport({
        generatedAt: new Date().toISOString(),
        houseId: hid,
        disease: selectedDisease
          ? { key: selectedDisease.key, name: selectedDisease.name, metrics: selectedDisease.metrics }
          : undefined,
        sections,
      })
    } catch (e) {
      console.error(e)
      window.alert('Failed to export the report. Please try again later.')
    } finally {
      setReportDownloading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <div className="flex gap-2">
            <button
              onClick={() => setTab('sensors')}
              className={`rounded-xl px-4 py-2 border ${tab === 'sensors' ? 'bg-black text-white' : 'hover:bg-gray-100'}`}
            >
              Sensors
            </button>
            <button
              onClick={() => setTab('charts')}
              className={`rounded-xl px-4 py-2 border ${tab === 'charts' ? 'bg-black text-white' : 'hover:bg-gray-100'}`}
            >
              Charts
            </button>
            <Link to="/data-viewer" className="rounded-xl border px-4 py-2 hover:bg-gray-100">Data Viewer</Link>
            <Link to="/diseases" className="rounded-xl border px-4 py-2 hover:bg-gray-100">Disease Config</Link>
            <Link to="/health-advisor" className="rounded-xl border px-4 py-2 hover:bg-gray-100">
              Health Advisor
            </Link>
            <Link
              to="/register"
              className="rounded-xl bg-blue-600 text-white px-4 py-2 font-medium hover:bg-blue-700 shadow-sm"
            >
              New Register
            </Link>
          </div>
        </div>

        <div className="mb-4 text-sm text-gray-600">API: {API_BASE}</div>

        {tab === 'sensors' && (
          <>
            {loading && <div className="text-gray-600">Loading...</div>}
            {error && (
              <div className="rounded-xl border bg-red-50 p-4 text-red-800 mb-4">
                <div className="font-semibold">Error</div>
                <div className="text-sm whitespace-pre-wrap">{error}</div>
              </div>
            )}
            {!loading && !error && (
              <SensorGrid
                items={items}
                apiBase={API_BASE}
                onSensorUpdated={(updated) =>
                  setItems(prev => prev.map(item => (item.id === updated.id ? updated : item)))
                }
              />
            )}
          </>
        )}

        {tab === 'charts' && (
          <>
            {!hid && (
              <div className="rounded-xl border bg-yellow-50 p-4 text-yellow-800">
                Missing house_id. Please login again.
              </div>
            )}

            {hid && (
              <div className="space-y-4">
                {/* Disease selector */}
                <div className="rounded-2xl bg-white border shadow p-4">
                  <div className="mb-2 text-gray-800 font-semibold">Choose a disease</div>
                  <div className="flex flex-wrap gap-3">
                    {diseases.map(d => (
                      <button
                        key={d.key}
                        onClick={() => {
                          setSelectedDiseaseKey(d.key)
                          localStorage.setItem('disease_key', d.key)
                        }}
                        className={`px-3 py-1 rounded-full border text-sm ${
                          selectedDiseaseKey === d.key
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'hover:bg-gray-100'
                        }`}
                      >
                        {d.name}
                      </button>
                    ))}
                    {(!diseases || diseases.length === 0) && (
                      <span className="text-gray-500 text-sm">No disease configuration</span>
                    )}
                  </div>
                </div>

                {/* Chart panels (restricted by disease metrics) */}
                {selectedDisease ? (
                  <div className="space-y-6">
                    <ChartsPanel
                      ref={chartsPanelRef}
                      apiBase={API_BASE}
                      houseId={hid}
                      allowedMetrics={selectedDisease.metrics}
                    />
                    <ScatterPanel
                      ref={scatterPanelRef}
                      apiBase={API_BASE}
                      houseId={hid}
                      allowedMetrics={selectedDisease.metrics}
                    />
                    <RiskHeatmapPanel
                      ref={heatmapPanelRef}
                      apiBase={API_BASE}
                      houseId={hid}
                      diseaseKey={selectedDisease.key}
                      diseaseName={selectedDisease.name}
                      allowedMetrics={selectedDisease.metrics}
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={handleDownloadReport}
                        disabled={reportDownloading}
                        className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
                      >
                        {reportDownloading ? 'Generating report…' : 'Download Report'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border bg-amber-50 p-4 text-amber-800">
                    Please select a disease above before viewing charts.
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
