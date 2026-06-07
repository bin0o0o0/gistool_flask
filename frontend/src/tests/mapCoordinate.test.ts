import { describe, expect, it } from 'vitest'

import { formatLonLatDisplay } from '@/utils/mapCoordinate'

describe('formatLonLatDisplay', () => {
  it('formats longitude and latitude with direction labels and six decimals', () => {
    expect(formatLonLatDisplay([106.1234567, 27.1234562])).toBe('经度 106.123457° E  纬度 27.123456° N')
    expect(formatLonLatDisplay([-106.1, -27.2])).toBe('经度 106.100000° W  纬度 27.200000° S')
  })
})
