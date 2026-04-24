import { describe, expect, it } from 'vitest'
import { routes } from '@/router/routes'

describe('router', () => {
  it('exposes the homepage, output workspace, reserved feature pages, and legacy redirect', () => {
    const byPath = new Map(routes.map((route) => [route.path, route]))

    expect(byPath.get('/')?.name).toBe('home')
    expect(byPath.get('/map-output')?.name).toBe('map-output')
    expect(byPath.get('/watershed-extract')?.name).toBe('watershed-extract')
    expect(byPath.get('/guide')?.name).toBe('guide')
    expect(byPath.get('/workspace')?.redirect).toBe('/map-output')
  })
})
