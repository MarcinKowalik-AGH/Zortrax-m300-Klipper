import { describe, expect, it } from 'vitest'
import { readM300OledPreview, selectM300OledPreview } from './m300-oled-preview'

const frame = {
  online: true,
  sequence: 14,
  width: 256,
  height: 64,
  format: 'indexed4-png',
  source: 'host-rendered',
  image_base64: 'iVBORw0KGgo='
}

describe('M300 OLED preview status', () => {
  it('does not render a widget on printers without the M300 OLED status', () => {
    expect(readM300OledPreview(null)).toBeNull()
    expect(readM300OledPreview({})).toBeNull()
    expect(readM300OledPreview({ m300_oled: { connected: true } })).toBeNull()
  })

  it('keeps a safe PNG data URI and sequence for a connected printer', () => {
    expect(readM300OledPreview({ m300_oled: { oled_preview: frame } })).toEqual({
      online: true,
      sequence: 14,
      image: 'data:image/png;base64,' + frame.image_base64
    })
  })

  it('does not show a stale MCU-local screen after disconnection', () => {
    expect(readM300OledPreview({
      m300_oled: { oled_preview: { ...frame, online: false } }
    })).toEqual({ online: false, sequence: 14, image: null })
  })

  it('prefers a newer direct query to the periodic 250ms subscription', () => {
    const subscribed = readM300OledPreview({ m300_oled: { oled_preview: frame } })!
    const latest = readM300OledPreview({
      m300_oled: { oled_preview: { ...frame, sequence: 16, image_base64: 'dGVzdA==' } }
    })!
    expect(selectM300OledPreview(subscribed, latest, true)).toEqual(latest)
    expect(selectM300OledPreview(latest, subscribed, true)).toEqual(latest)
    expect(selectM300OledPreview(null, latest, true)).toBeNull()
  })

  it('never exposes the old image from a disconnected Klipper socket', () => {
    const subscribed = readM300OledPreview({ m300_oled: { oled_preview: frame } })!
    const result = selectM300OledPreview(subscribed, subscribed, false)
    expect(result).toEqual({ ...subscribed, online: false, image: null })
  })

  it('refuses oversized, malformed, wrong-dimension or wrong-format frames', () => {
    const invalid = [
      { ...frame, source: 'unsupported' },
      { ...frame, image_base64: 'data:image/svg+xml;base64,AAAA' },
      { ...frame, image_base64: 'a'.repeat(32769) },
      { ...frame, width: 128 },
      { ...frame, format: 'image/svg+xml' },
      { ...frame, image_base64: '' }
    ]
    invalid.forEach(item => {
      expect(readM300OledPreview({ m300_oled: { oled_preview: item } })?.image).toBeNull()
    })
  })
})
