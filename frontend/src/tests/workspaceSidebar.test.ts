// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

import WorkspaceSidebar from '@/components/WorkspaceSidebar.vue'
import { useWorkspaceStore } from '@/stores/workspace'

describe('WorkspaceSidebar', () => {
  it('shows the redesigned workflow labels and dataset summary', () => {
    setActivePinia(createPinia())
    const store = useWorkspaceStore()
    store.uploads.template_project.result = fakeUpload('template.aprx', 'template_project')
    store.form.inputs.basin_boundaries.push({
      id: 'basin-1',
      name: 'Basin 1',
      path: 'D:/uploads/basin.shp',
      style: {
        boundary_color: '#222222',
        boundary_width_pt: 1.2,
        fill_color: '#e6f0d4',
        fill_opacity: 0.45
      }
    })
    store.form.inputs.river_networks.push({
      id: 'river-1',
      name: 'River 1',
      path: 'D:/uploads/river.shp',
      style: {
        color: '#2f80ed',
        width_pt: 2.5
      }
    })
    store.form.inputs.station_layers[0].upload = fakeUpload('stations.xlsx', 'station_excel')

    const wrapper = mount(WorkspaceSidebar)
    const text = wrapper.text()

    expect(text).toContain('数据准备')
    expect(text).toContain('图层配置')
    expect(text).toContain('出图参数')
    expect(text).toContain('导出结果')
    expect(text).toContain('流域边界')
    expect(text).toContain('河流网络')
    expect(text).toContain('站点数据')
  })
})

function fakeUpload(
  name: string,
  kind: 'template_project' | 'basin_boundary' | 'river_network' | 'station_excel'
) {
  return {
    file_id: name,
    kind,
    original_name: name,
    path: `D:/uploads/${name}`,
    suffix: name.slice(name.lastIndexOf('.')),
    size_bytes: 1
  }
}
