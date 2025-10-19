import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

type RegisterBody = {
  serial_number: string
  first_name: string
  last_name: string
  phone: string
  email: string
  address: string
  zone: 'N' | 'S' | 'W' | 'E' | 'C'
}

type RegisterResp = { house_id: string }

export default function Register() {
  const API_BASE = useMemo(() => import.meta.env.VITE_API_BASE || 'http://localhost:8000', [])
  const [form, setForm] = useState<RegisterBody>({
    serial_number: '',
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    address: '',
    zone: 'C',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const onChange = (k: keyof RegisterBody, v: string) => {
    setForm(prev => ({ ...prev, [k]: k === 'zone' ? (v as RegisterBody['zone']) : v }))
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!r.ok) {
        let msg = 'Registration failed'
        try {
          const t = await r.json()
          msg = t?.detail ? String(t.detail) : msg
        } catch {}
        throw new Error(msg)
      }
      const data = (await r.json()) as RegisterResp
      localStorage.setItem('house_id', data.house_id)
      navigate(`/dashboard/${encodeURIComponent(data.house_id)}`)
    } catch (err: any) {
      setError(err?.message || 'Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto w-full max-w-xl bg-white rounded-2xl shadow p-6">
        <h1 className="text-2xl font-bold mb-4">Register Household</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Serial Number</label>
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={form.serial_number}
              onChange={e => onChange('serial_number', e.target.value)}
              required
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">First Name</label>
              <input
                className="w-full rounded-xl border px-3 py-2"
                value={form.first_name}
                onChange={e => onChange('first_name', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Last Name</label>
              <input
                className="w-full rounded-xl border px-3 py-2"
                value={form.last_name}
                onChange={e => onChange('last_name', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Zone</label>
              <select
                className="w-full rounded-xl border px-3 py-2"
                value={form.zone}
                onChange={e => onChange('zone', e.target.value)}
              >
                <option value="N">North of Auckland</option>
                <option value="S">South of Auckland</option>
                <option value="W">West of Auckland</option>
                <option value="E">East of Auckland</option>
                <option value="C">Auckland City</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Phone</label>
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={form.phone}
              onChange={e => onChange('phone', e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input
              type="email"
              className="w-full rounded-xl border px-3 py-2"
              value={form.email}
              onChange={e => onChange('email', e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Address</label>
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={form.address}
              onChange={e => onChange('address', e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-black text-white py-2 font-semibold disabled:opacity-60"
          >
            {loading ? 'Submitting...' : 'Register'}
          </button>
        </form>

        {error && (
          <div className="mt-4 rounded-xl border bg-red-50 p-4 text-red-800">
            <div className="font-semibold">Error</div>
            <div className="text-sm">{error}</div>
          </div>
        )}

        <div className="mt-6 text-sm text-gray-500">API: {import.meta.env.VITE_API_BASE || 'http://localhost:8000'}</div>
      </div>
    </div>
  )
}
