// Marcin Kowalik <mkowalik@agh.edu.pl>
// m300-oled-timers.spec.ts - Sprawdza zakres i kolejność progów OLED oraz zapis obu suwaków jednym poleceniem.
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import M300OledTimers from '@/components/common/M300OledTimers.vue'
import ActionCommandPromptDialog from '@/components/common/ActionCommandPromptDialog.vue'

vi.mock('@/mixins/state', async () => ({ default: (await import('vue')).default }))

describe('paired OLED timer controls', () => {
  it.each(['OLED dim time', 'OLED sleep time'])('opens the two controls in the %s macro prompt', async title => {
    const slot = { template: '<div><slot /><slot name="actions" /></div>' }
    const button = { template: '<button v-on="$listeners"><slot /></button>' }
    const sendGcode = vi.fn()
    const wrapper = mount(ActionCommandPromptDialog, {
      mocks: {
        sendGcode,
        $typedState: {
          console: {
            promptDialog: {
              title: 'ZORTRAX M300 - ' + title,
              open: true,
              footerButtons: [],
              items: [{ id: 1, type: 'text', text: 'M300_OLED_TIMERS 5 15' }]
            }
          }
        }
      },
      stubs: { AppDialog: slot, VCardText: slot, VRow: slot, VCol: slot, VBtn: button, VSpacer: slot }
    })
    expect(wrapper.findAll('.m300-slider-bar').length).toBe(2)
    expect(wrapper.text()).not.toContain('M300_OLED_TIMERS')
    await wrapper.find('input[aria-label="SLEEP"]').setValue('25')
    await wrapper.find('button').trigger('click')
    expect(sendGcode).toHaveBeenCalledTimes(1)
    expect(sendGcode).toHaveBeenCalledWith('ZORTRAX_OLED_TIMERS DIM=5 SLEEP=25')
    wrapper.destroy()
  })

  it('loads both values, validates their order and sends one explicit save', async () => {
    const control = mount(M300OledTimers, {
      propsData: { values: 'M300_OLED_TIMERS 4 12' },
      stubs: { 'v-btn': { template: '<button v-bind="$attrs" v-on="$listeners"><slot /></button>' } }
    })
    const inputs = control.findAll('input')
    expect(inputs.length).toBe(2)
    expect((inputs.at(1).element as HTMLInputElement).value).toBe('12')
    const bars = control.findAll('.m300-slider-bar')
    expect(bars.length).toBe(2)
    for (const bar of bars.wrappers) expect(bar.findAll('[aria-hidden="true"]').length).toBe(16)
    expect(bars.at(0).findAll('.filled').length).toBe(2)
    expect(bars.at(1).findAll('.filled').length).toBe(4)
    expect(inputs.at(0).attributes('aria-label')).toBe('DIM')
    expect(inputs.at(1).attributes('aria-label')).toBe('SLEEP')
    await inputs.at(0).setValue('1')
    expect(bars.at(0).findAll('.filled').length).toBe(1)
    expect(inputs.at(0).attributes('aria-valuetext')).toBe('1 min')
    await inputs.at(0).setValue('20')
    expect(control.find('button').attributes('disabled')).toBeDefined()
    await inputs.at(1).setValue('60')
    expect(bars.at(0).findAll('.filled').length).toBe(6)
    expect(bars.at(1).findAll('.filled').length).toBe(16)
    expect(control.emitted('save')).toBeUndefined()
    await control.find('button').trigger('click')
    expect(control.emitted('save')).toEqual([['ZORTRAX_OLED_TIMERS DIM=20 SLEEP=60']])
    control.destroy()
  })
})
