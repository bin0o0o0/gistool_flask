export function formatLonLatDisplay([lon, lat]: [number, number]) {
  const lonDirection = lon >= 0 ? 'E' : 'W'
  const latDirection = lat >= 0 ? 'N' : 'S'
  return `经度 ${Math.abs(lon).toFixed(6)}° ${lonDirection}  纬度 ${Math.abs(lat).toFixed(6)}° ${latDirection}`
}
