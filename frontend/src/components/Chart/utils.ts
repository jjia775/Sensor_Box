import type { Sensor } from '../../types/sensors'

export function formatISO(d: Date) {
  const base = d.toISOString()
  return `${base.slice(0, 19)}Z`
}

// Local fallback for locating the serial number: serial_number > meta.serial_number > meta.serial > meta.sn
export function getSerial(s: Sensor): string {
  const direct = (s as any).serial_number
  if (typeof direct === 'string' && direct) return direct
  const m = (s.meta || {}) as any
  if (typeof m.serial_number === 'string' && m.serial_number) return m.serial_number
  if (typeof m.serial === 'string' && m.serial) return m.serial
  if (typeof m.sn === 'string' && m.sn) return m.sn
  return ''
}
