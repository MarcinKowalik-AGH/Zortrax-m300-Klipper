// SPDX-License-Identifier: GPL-3.0-only
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Vue from 'vue'
import { shallowMount, type Wrapper } from '@vue/test-utils'
import M300OledPreview from '@/components/widgets/thermals/M300OledPreview.vue'
import { readM300OledPreview, type M300OledPreviewStatus } from './m300-oled-preview'

const control = vi.hoisted(() => ({
  starts: 0,
  stops: 0,
  show: null as ((frame: M300OledPreviewStatus) => Promise<void>) | null,
  live: null as ((active: boolean) => void) | null
}))
vi.mock('@/mixins/state', async () => ({ default: (await import('vue')).default }))
vi.mock('@/api/socketActions', () => ({ SocketActions: { printerObjectsQuery: vi.fn(() => new Promise(() => {})) } }))
vi.mock('@/util/m300-oled-navigation', () => ({
  M300NavigationEvents: class {
    constructor (show: (frame: M300OledPreviewStatus) => Promise<void>, live: (active: boolean) => void) {
      control.show = show; control.live = live
    }

    start () { control.starts++; control.live?.(true) }
    stop () { control.stops++; control.live?.(false) }
  }
}))

const raw = {
  online: true,
  sequence: 1,
  width: 256,
  height: 64,
  format: 'indexed4-png',
  source: 'host-rendered',
  image_base64: 'iVBORw0KGgo=',
  epoch: 'a'.repeat(32),
  navigation_revision: 1,
  navigation_api: 'NAV-EVENT-1'
}
const frame = (sequence: number, image_base64: string) => readM300OledPreview({
  m300_oled: { oled_preview: { ...raw, sequence, navigation_revision: sequence, image_base64 } }
})!
const images: TestImage[] = []
class TestImage {
  src = ''
  naturalWidth = 256
  naturalHeight = 64
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor () { images.push(this) }
}
const draw = vi.fn()
let wrapper: Wrapper<Vue> | undefined
async function mountPreview () {
  wrapper = shallowMount(M300OledPreview, {
    mocks: {
      socketReady: true,
      klippyReady: true,
      $typedState: Vue.observable({ printer: { printer: { m300_oled: { oled_preview: raw } } } })
    },
    stubs: { 'v-divider': true, 'v-btn': true }
  })
  await Vue.nextTick(); await Vue.nextTick()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  control.starts = control.stops = 0
  images.length = 0
  draw.mockClear()
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw, fillRect: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.stubGlobal('Image', TestImage)
})
afterEach(() => {
  wrapper?.destroy(); wrapper = undefined
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
})

describe('M300 navigation canvas', () => {
  it('uses integer device pixels and never stretches with column width', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    const view = await mountPreview()
    expect(view.find('canvas').attributes('width')).toBe('260')
    expect(view.find('canvas').attributes('height')).toBe('68')
    expect(view.find('canvas').attributes('style')).toContain('width: 260px;')
    expect(view.find('section').attributes('data-preview-revision')).toBe('NAV-PIPELINE-2')
    expect(control.starts).toBeGreaterThan(0)
  })

  it('adapts backing pixels to a fractional DPR rather than stretching them', async () => {
    vi.stubGlobal('devicePixelRatio', 1.25)
    const view = await mountPreview()
    expect(view.find('canvas').attributes('width')).toBe('516')
    expect(view.find('canvas').attributes('height')).toBe('132')
    expect(view.find('canvas').attributes('style')).toContain('width: 412.8px;')
    expect(view.find('section').attributes('data-pixel-scale')).toBe('2')
  })

  it('coalesces navigation while decoding and never paints the superseded selection', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    await mountPreview()
    const old = images.at(-1)!
    await control.show!(frame(8, 'YWJj'))
    await control.show!(frame(16, 'dGVzdA=='))
    await Vue.nextTick(); await Vue.nextTick()
    expect(images).toHaveLength(1)
    old.onload?.()
    expect(draw).not.toHaveBeenCalled()
    const newest = images.at(-1)!
    expect(newest).not.toBe(old)
    expect(newest.src).toBe('data:image/png;base64,dGVzdA==')
    newest.onload?.()
    expect(draw).toHaveBeenCalledTimes(1)
    expect(draw).toHaveBeenLastCalledWith(newest, 2, 2, 256, 64)
  })

  it('repaints an already decoded frame after zoom without another PNG decode', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    const view = await mountPreview()
    images.at(-1)!.onload?.()
    vi.stubGlobal('devicePixelRatio', 2)
    window.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(20)
    await Vue.nextTick(); await Vue.nextTick()
    expect(images).toHaveLength(1)
    expect(view.find('canvas').attributes('width')).toBe('772')
    expect(view.find('canvas').attributes('height')).toBe('196')
    expect(draw).toHaveBeenLastCalledWith(images[0], 2, 2, 768, 192)
  })

  it('cancels navigation when collapsed and re-arms when opened', async () => {
    const view = await mountPreview()
    const before = control.stops
    await view.setData({ collapsed: true })
    expect(control.stops).toBeGreaterThan(before)
    expect(view.find('canvas').exists()).toBe(false)
    const starts = control.starts
    await view.setData({ collapsed: false })
    expect(control.starts).toBeGreaterThan(starts)
  })

  it('never paints onto a removed widget after an outstanding decode', async () => {
    await mountPreview()
    const shown = control.show!(frame(2, 'dGVzdA=='))
    await Vue.nextTick(); await Vue.nextTick()
    const pending = images.at(-1)!
    wrapper!.destroy(); wrapper = undefined
    pending.onload?.(); await shown
    expect(draw).not.toHaveBeenCalled()
  })
})
