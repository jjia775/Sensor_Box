export type SensorMeta = {
  enabled?: boolean
  [key: string]: unknown
}

export type Sensor = {
  id: string
  name: string
  type: string
  location?: string | null
  meta?: SensorMeta | null
  serial_number?: string | null   // newly added field
  house_id?: string | null
  householder?: string | null
}
