import { describe, expect, it } from 'vitest'
import { routes } from '@/router/routes'
import ComingSoonView from '@/views/ComingSoonView.vue'
import WatershedBoundaryGeneratorView from '@/views/WatershedBoundaryGeneratorView.vue'
import WatershedExtractView from '@/views/WatershedExtractView.vue'

describe('router', () => {
  it('exposes the homepage, output workspace, reserved feature pages, and legacy redirect', () => {
    const byPath = new Map(routes.map((route) => [route.path, route]))

    expect(byPath.get('/')?.name).toBe('home')
    expect(byPath.get('/map-output')?.name).toBe('map-output')
    expect(byPath.get('/watershed-extract')?.name).toBe('watershed-extract')
    expect(byPath.get('/watershed-boundary-generator')?.name).toBe('watershed-boundary-generator')
    expect(byPath.get('/guide')?.name).toBe('guide')
    expect(byPath.get('/workspace')?.redirect).toBe('/map-output')
    expect(byPath.get('/watershed-extract')?.component).toBe(WatershedExtractView)
    expect(byPath.get('/watershed-extract')?.component).not.toBe(ComingSoonView)
    expect(byPath.get('/watershed-boundary-generator')?.component).toBe(WatershedBoundaryGeneratorView)
  })
})
