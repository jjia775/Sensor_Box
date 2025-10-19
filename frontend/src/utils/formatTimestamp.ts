const pad = (value: number): string => value.toString().padStart(2, '0')

export type TimestampParts = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
  millisecond: number
  offsetMinutes: number | null
}

const ISOishRegex =
  /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?(?:\s*(Z|z|([+-])(\d{2}):?(\d{2})))?$/

export const parseTimestampParts = (raw: string | null | undefined): TimestampParts | null => {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed) return null

  const isoMatch = trimmed.match(ISOishRegex)
  if (isoMatch) {
    const [, yearStr, monthStr, dayStr, hourStr, minuteStr, secondStr, fractionStr, zoneStr, signSymbol, offHourStr, offMinStr] = isoMatch

    const year = Number.parseInt(yearStr, 10)
    const month = Number.parseInt(monthStr, 10)
    const day = Number.parseInt(dayStr, 10)
    const hour = Number.parseInt(hourStr, 10)
    const minute = Number.parseInt(minuteStr, 10)
    const second = Number.parseInt(secondStr ?? '0', 10)
    const fraction = fractionStr ? fractionStr.slice(0, 3) : '0'
    const millisecond = Number.parseInt(fraction.padEnd(3, '0'), 10)

    let offsetMinutes: number | null = null
    if (zoneStr) {
      if (/^z$/i.test(zoneStr)) {
        offsetMinutes = 0
      } else if (signSymbol && offHourStr && offMinStr) {
        const sign = signSymbol === '-' ? -1 : 1
        const offHours = Number.parseInt(offHourStr, 10)
        const offMinutes = Number.parseInt(offMinStr, 10)
        if (Number.isFinite(offHours) && Number.isFinite(offMinutes)) {
          offsetMinutes = sign * (offHours * 60 + offMinutes)
        }
      }
    }

    if ([year, month, day, hour, minute, second].some(value => Number.isNaN(value))) {
      return null
    }

    const utcMillis = Date.UTC(year, month - 1, day, hour, minute, second, millisecond)
    const adjustedMillis = utcMillis - (offsetMinutes ?? 0) * 60_000
    const local = new Date(adjustedMillis)

    return {
      year: local.getFullYear(),
      month: local.getMonth() + 1,
      day: local.getDate(),
      hour: local.getHours(),
      minute: local.getMinutes(),
      second: local.getSeconds(),
      millisecond: local.getMilliseconds(),
      offsetMinutes,
    }
  }

  const fallback = new Date(trimmed)
  if (Number.isNaN(fallback.getTime())) {
    return null
  }

  return {
    year: fallback.getFullYear(),
    month: fallback.getMonth() + 1,
    day: fallback.getDate(),
    hour: fallback.getHours(),
    minute: fallback.getMinutes(),
    second: fallback.getSeconds(),
    millisecond: fallback.getMilliseconds(),
    offsetMinutes: null,
  }
}

export const formatTimestamp = (raw: string | null | undefined): string | null => {
  const parts = parseTimestampParts(raw)
  if (!parts) {
    return raw?.trim() ? raw.trim() : null
  }

  const base = `${parts.year}-${pad(parts.month)}-${pad(parts.day)} ${pad(parts.hour)}:${pad(parts.minute)}:${pad(parts.second)}`

  if (parts.offsetMinutes == null) {
    return base
  }

  const sign = parts.offsetMinutes >= 0 ? '+' : '-'
  const absMinutes = Math.abs(parts.offsetMinutes)
  const offsetHours = pad(Math.floor(absMinutes / 60))
  const offsetRemainingMinutes = pad(absMinutes % 60)

  return `${base} UTC${sign}${offsetHours}:${offsetRemainingMinutes}`
}

export default formatTimestamp
