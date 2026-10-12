import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StatusTag from '../components/StatusTag.vue'

describe('StatusTag', () => {
  it('renders the translated status label', () => {
    const wrapper = mount(StatusTag, {
      props: { status: 'InProgress' },
      global: {
        stubs: { 'el-tag': { template: '<span><slot /></span>' } },
      },
    })
    expect(wrapper.text()).toContain('进行中')
  })
})
