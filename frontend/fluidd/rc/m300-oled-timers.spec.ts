// Marcin Kowalik <mkowalik@agh.edu.pl>
// m300-oled-timers.spec.ts - Sprawdza zakres i kolejność progów OLED oraz zapis obu suwaków jednym poleceniem.
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import M300OledTimers from '@/components/common/M300OledTimers.vue'

describe('paired OLED timer controls', () => {
  it('loads both values, validates their order and sends one explicit save', async () => {
    const control = mount(M300OledTimers, {
      propsData: { values: 'M300_OLED_TIMERS 4 12' },
      stubs: { 'v-btn': { template: '<button v-bind="$attrs" v-on="$listeners"><slot /></button>' } }
    })
    const inputs = control.findAll('input')
    expect(inputs.length).toBe(2)
    expect((inputs.at(1).element as HTMLInputElement).value).toBe('12')
    await inputs.at(0).setValue('20')
    expect(control.find('button').attributes('disabled')).toBeDefined()
    await inputs.at(1).setValue('60')
    expect(control.emitted('save')).toBeUndefined()
    await control.find('button').trigger('click')
    expect(control.emitted('save')).toEqual([['ZORTRAX_OLED_TIMERS DIM=20 SLEEP=60']])
    control.destroy()
  })
})
