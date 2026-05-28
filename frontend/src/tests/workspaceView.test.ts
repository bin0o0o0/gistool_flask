// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

import WorkspaceView from '@/views/WorkspaceView.vue'

vi.mock('@/components/SiteNav.vue', () => ({
  default: { template: '<nav class="site-nav-stub">nav</nav>' }
}))
vi.mock('@/components/WorkspaceSidebar.vue', () => ({
  default: { template: '<aside class="workspace-sidebar-stub">sidebar</aside>' }
}))
vi.mock('@/components/FileUploadCard.vue', () => ({
  default: { template: '<section class="file-upload-stub">data panel</section>' }
}))
vi.mock('@/components/LayerStylePanel.vue', () => ({
  default: { template: '<section class="style-panel-stub">style panel</section>' }
}))
vi.mock('@/components/OutputSettings.vue', () => ({
  default: { template: '<section class="output-panel-stub">output panel</section>' }
}))
vi.mock('@/components/StationLayerEditor.vue', () => ({
  default: { template: '<section class="station-panel-stub">station panel</section>' }
}))
vi.mock('@/components/RequestPreview.vue', () => ({
  default: { template: '<section class="request-preview-stub">request preview</section>' }
}))
vi.mock('@/components/MapOutputControlPanel.vue', () => ({
  default: { template: '<section class="control-panel-stub">control panel</section>' }
}))
vi.mock('@/components/WorkspacePreviewMap.vue', () => ({
  default: { template: '<section class="preview-map-stub">地图预览</section>' }
}))

describe('WorkspaceView', () => {
  it('renders the redesigned three-column workbench scaffold', () => {
    setActivePinia(createPinia())

    const wrapper = mount(WorkspaceView)

    expect(wrapper.find('.workspace-grid').exists()).toBe(true)
    expect(wrapper.find('.workspace-stage').exists()).toBe(true)
    expect(wrapper.find('.workspace-map-column').exists()).toBe(true)
    expect(wrapper.find('.workspace-control-column').exists()).toBe(true)
    expect(wrapper.text()).toContain('流域出图')
    expect(wrapper.text()).toContain('地图预览')
  })
})
