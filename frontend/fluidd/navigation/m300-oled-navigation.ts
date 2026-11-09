// SPDX-License-Identifier: GPL-3.0-only
import Vue from 'vue'
import { readM300OledPreview, type M300OledPreviewStatus } from './m300-oled-preview'

export interface NavigationCursor {
  client: string
  epoch: string
  navigation_revision: number
}

export interface NavigationReply {
  changed: boolean
  frame?: unknown
}

declare global {
  namespace Moonraker {
    interface Methods {
      'printer.m300.oled_preview.wait': { params: NavigationCursor; result: NavigationReply }
      'printer.m300.oled_preview.cancel_wait': { params: { client: string }; result: { cancelled: boolean } }
    }
  }
}

export interface NavigationTransport {
  wait: (cursor: NavigationCursor) => Promise<NavigationReply>
  cancel: (client: string) => Promise<unknown>
}

const transport: NavigationTransport = {
  wait: params => Vue.$socket.emit('printer.m300.oled_preview.wait', { params, suppressError: true }),
  cancel: client => Vue.$socket.emit('printer.m300.oled_preview.cancel_wait', {
    params: { client }, suppressError: true
  })
}

/** One outstanding event wait; no polling interval or debounce after a detent. */
export class M300NavigationEvents {
  private active = false
  private generation = 0
  private requestClient: string | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null

  constructor (
    private readonly show: (frame: M300OledPreviewStatus) => Promise<void>,
    private readonly setLive: (live: boolean) => void,
    private readonly api: NavigationTransport = transport,
    // Correlation only, not an authentication credential.
    private readonly clientId = 'm300-' + Math.random().toString(36).slice(2)
  ) {}

  start () {
    if (this.active) return
    this.active = true
    const generation = ++this.generation
    const client = this.requestClient = this.clientId + '-' + generation
    void this.run(generation, { client, epoch: '', navigation_revision: -1 })
  }

  stop () {
    this.active = false
    this.generation++
    this.setLive(false)
    if (this.retryTimer !== null) clearTimeout(this.retryTimer)
    this.retryTimer = null
    const client = this.requestClient
    this.requestClient = null
    if (client) void this.api.cancel(client).catch(() => undefined)
  }

  private current (generation: number): boolean {
    return this.active && generation === this.generation
  }

  private async run (generation: number, cursor: NavigationCursor): Promise<void> {
    try {
      while (this.current(generation)) {
        const response = await this.api.wait(cursor)
        if (!this.current(generation)) return
        if (!response || typeof response.changed !== 'boolean') throw new Error('Invalid OLED navigation reply')
        // An unchanged response is the server's bounded 10 s keepalive, not
        // a high-frequency poll. A detent completes the wait immediately.
        if (!response.changed) continue
        const frame = readM300OledPreview({ m300_oled: { oled_preview: response.frame } })
        if (!frame?.epoch || frame.navigationApi !== 'NAV-EVENT-1' || frame.navigationRevision === undefined) {
          throw new Error('Invalid OLED navigation frame')
        }
        cursor = { ...cursor, epoch: frame.epoch, navigation_revision: frame.navigationRevision }
        // Backpressure: while the browser paints, the host retains only its
        // newest state. Next request gets that state, not intermediate frames.
        await this.show(frame)
        if (this.current(generation)) this.setLive(true)
      }
    } catch {
      if (!this.current(generation)) return
      this.setLive(false)
      // Existing status/animation preview remains available during failure.
      this.retryTimer = setTimeout(() => {
        this.retryTimer = null
        if (this.current(generation)) void this.run(generation, cursor)
      }, 3000)
    }
  }
}
