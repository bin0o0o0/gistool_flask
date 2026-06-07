// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import WatershedBoundaryGeneratorView from '@/views/WatershedBoundaryGeneratorView.vue'

const { getDefaults, generate } = vi.hoisted(() => ({
  getDefaults: vi.fn(),
  generate: vi.fn()
}))

vi.mock('@/components/SiteNav.vue', () => ({
  default: { template: '<nav class="site-nav-stub">nav</nav>' }
}))

vi.mock('@/components/WatershedBoundaryPreviewMap.vue', () => ({
  default: { template: '<section class="boundary-map-stub">map</section>' }
}))

vi.mock('@/api/watershedBoundary', () => ({
  watershedBoundaryApi: {
    getDefaults,
    generate
  }
}))

describe('WatershedBoundaryGeneratorView', () => {
  it('loads service defaults and keeps DEM path in local absolute-path mode', async () => {
    getDefaults.mockResolvedValueOnce({
      data: {
        success: true,
        data: {
          dem_path: 'D:\\work\\data\\data\\dem\\dem.tif',
          snap_threshold: 2200
        }
      }
    })

    const wrapper = mount(WatershedBoundaryGeneratorView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' }
        }
      }
    })
    await flushPromises()

    expect(wrapper.text()).toContain('D:\\work\\data\\data\\dem\\dem.tif')
    expect(wrapper.text()).toContain('本地化部署推荐直接填写本机绝对路径')
    expect(wrapper.text()).toContain('不再复制文件到 uploads 目录')
    expect(wrapper.text()).not.toContain('上传副本')
    const textInputs = wrapper.findAll('input[type="text"]')
    expect(textInputs[0]?.element).toHaveProperty('value', 'D:\\work\\data\\data\\dem\\dem.tif')
    expect(textInputs[textInputs.length - 1]?.element).toHaveProperty('value', '2200')
  })
})
