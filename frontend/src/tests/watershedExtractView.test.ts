// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { watershedApi } from '@/api/watershed'
import WatershedExtractView from '@/views/WatershedExtractView.vue'

describe('WatershedExtractView', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses local absolute-path mode for both DEM and boundary inputs', () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    expect(wrapper.text()).toContain('请直接填写 DEM 文件的本机绝对路径。')
    expect(wrapper.text()).toContain('请直接填写流域边界文件的本机绝对路径。')
    expect(wrapper.text()).not.toContain('拖入或上传 DEM，可选')
    expect(wrapper.text()).not.toContain('拖入或上传边界')
    expect(wrapper.text()).toContain('DEM 路径 dem_path')
    expect(wrapper.text()).toContain('流域边界 shapefile_path')
    expect(wrapper.text()).toContain('选择 DEM 文件')
    expect(wrapper.text()).toContain('选择边界文件')
  })

  it('keeps pasted break-point coordinates without mangling them during editing', async () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    await wrapper.findAll('.step-item')[2]?.trigger('click')
    const addButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('添加控制点'))
    await addButton?.trigger('click')

    const breakInputs = wrapper.findAll('.break-table__row input')
    await breakInputs[0].setValue('105.179399')
    await breakInputs[1].setValue('27.072576')

    expect((breakInputs[0].element as HTMLInputElement).value).toBe('105.179399')
    expect((breakInputs[1].element as HTMLInputElement).value).toBe('27.072576')
  })

  it('starts manually added control-point ids after the implicit outlet point', async () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    vm.activeStep = 3
    await nextTick()
    vm.addBreakPoint()
    await nextTick()

    expect(vm.state.breakPoints[0][2]).toBe(2)
  })

  it('does not render an editable id input for manual break points', async () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    vm.activeStep = 3
    vm.addBreakPoint()
    await nextTick()

    const rowInputs = wrapper.findAll('.break-table__row input')
    expect(rowInputs).toHaveLength(2)
    expect(wrapper.find('.break-table__id').text()).toBe('2')
  })

  it('prefers desktop file path metadata when auto-filling local paths', () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    const input = { value: 'C:\\fakepath\\dem.tif' } as HTMLInputElement
    const file = Object.assign(new File(['x'], 'dem.tif'), { path: 'D:\\work\\data\\data\\dem\\dem.tif' })

    expect(vm.resolveSelectedLocalPath(input, file)).toBe('D:\\work\\data\\data\\dem\\dem.tif')
  })

  it('rejects browser fakepath values when no desktop file path is available', () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    const input = { value: 'C:\\fakepath\\watershed-boundary.geojson' } as HTMLInputElement
    const file = new File(['x'], 'watershed-boundary.geojson')

    expect(vm.resolveSelectedLocalPath(input, file)).toBe('')
  })

  it('keeps the current DEM path when the browser only returns fakepath for the same file', async () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    vm.state.demPath = 'D:\\work\\data\\data\\dem\\dem.tif'
    vm.errorMessage = '当前环境未返回文件绝对路径，请继续手动粘贴本机路径。'

    const input = {
      value: 'C:\\fakepath\\dem.tif',
      files: [new File(['x'], 'dem.tif')]
    } as unknown as HTMLInputElement

    await vm.handleLocalPathSelection('dem', { target: input } as unknown as Event)

    expect(vm.state.demPath).toBe('D:\\work\\data\\data\\dem\\dem.tif')
    expect(vm.errorMessage).toBe('')
    expect(vm.successMessage).toContain('已沿用当前 DEM 路径')
  })

  it('fills the exact path returned by the local backend file picker', async () => {
    vi.spyOn(watershedApi, 'selectLocalFile').mockResolvedValue({
      data: {
        success: true,
        cancelled: false,
        path: 'E:\\custom\\terrain\\selected-dem.tif'
      }
    } as any)

    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    await vm.openLocalFilePicker('dem')

    expect(vm.state.demPath).toBe('E:\\custom\\terrain\\selected-dem.tif')
    expect(vm.errorMessage).toBe('')
    expect(vm.successMessage).toContain('DEM 路径已从本机文件选择器回填')
  })

  it('treats empty merge/delete selection as a skip and keeps step-three outputs', async () => {
    const wrapper = mount(WatershedExtractView, {
      global: {
        stubs: {
          'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
          SiteNav: { template: '<nav class="site-nav-stub">nav</nav>' },
          WatershedPreviewMap: { template: '<section class="watershed-preview-map-stub">map</section>' }
        }
      }
    })

    const vm = wrapper.vm as any
    vm.activeStep = 4
    await nextTick()
    vm.state.randomFolderName = 'program'
    await vm.runStep2()
    await nextTick()

    expect(vm.successMessage).toContain('沿用步骤三')
  })
})
