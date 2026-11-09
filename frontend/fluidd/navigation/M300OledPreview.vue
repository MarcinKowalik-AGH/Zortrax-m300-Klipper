<template>
  <section
    v-if="preview"
    class="m300-oled-preview"
    :data-navigation="navigationActive ? 'event' : 'fallback'"
    data-preview-revision="NAV-PIPELINE-2"
    :data-pixel-scale="pixelLayout.scale"
    aria-label="Zortrax M300 OLED screen preview"
  >
    <v-divider />
    <div class="d-flex align-center justify-space-between px-3 py-2">
      <span class="text-caption font-weight-medium">OLED M300</span>
      <v-btn
        text
        x-small
        :aria-label="collapsed ? 'Show OLED preview' : 'Hide OLED preview'"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? 'Show' : 'Hide' }}
      </v-btn>
    </div>
    <div
      v-if="!collapsed"
      ref="pixelViewport"
      class="m300-oled-viewport pb-3"
      tabindex="0"
      aria-label="Pixel-exact OLED preview. Scroll horizontally in narrow windows."
    >
      <canvas
        v-if="preview.image"
        ref="oledCanvas"
        class="m300-oled-frame"
        :width="pixelLayout.canvasWidth"
        :height="pixelLayout.canvasHeight"
        :style="pixelStyle"
        role="img"
        aria-label="Live host-rendered 256 by 64 M300 OLED screen"
      />
      <div
        v-else
        class="m300-oled-unavailable text-caption text-center"
        :style="pixelStyle"
      >
        OLED offline — local MCU screen cannot be mirrored
      </div>
    </div>
  </section>
</template>

<script lang="ts">
import { Component, Mixins, Watch } from 'vue-property-decorator'
import StateMixin from '@/mixins/state'
import { SocketActions } from '@/api/socketActions'
import { M300NavigationEvents } from '@/util/m300-oled-navigation'
import { M300LatestPainter } from '@/util/m300-oled-paint'
import { oledPixelLayout, oledPixelStyle, alignOledPixels, drawOledPixels } from '@/util/m300-oled-pixels'
import { readM300OledPreview, selectM300OledPreview, type M300OledPreviewStatus } from '@/util/m300-oled-preview'

// Preserve the existing animation/fallback cadence. Menu navigation uses
// its own event wait below, outside objects/query and the status cache.
const POLL_DELAY_MS = 85
const RETRY_DELAY_MS = 350

@Component({})
export default class M300OledPreview extends Mixins(StateMixin) {
  collapsed = false
  polledPreview: M300OledPreviewStatus | null = null
  navigationPreview: M300OledPreviewStatus | null = null
  navigationActive = false
  private navigation: M300NavigationEvents | null = null
  pixelLayout = oledPixelLayout(window.devicePixelRatio)
  private painter: M300LatestPainter | null = null
  private pixelObserver: ResizeObserver | null = null
  private pixelMedia: MediaQueryList | null = null
  private pixelTick: number | null = null
  private pollTimer: number | null = null
  private pollEpoch = 0
  private disposed = false

  get preview (): M300OledPreviewStatus | null {
    const subscribed = readM300OledPreview(this.$typedState.printer.printer)
    const connected = this.socketReady && this.klippyReady
    const periodic = selectM300OledPreview(subscribed, this.polledPreview, connected)
    return selectM300OledPreview(periodic, this.navigationPreview, connected)
  }

  get navigationSupported (): boolean {
    return readM300OledPreview(this.$typedState.printer.printer)?.navigationApi === 'NAV-EVENT-1'
  }

  get pixelStyle () {
    return oledPixelStyle(this.pixelLayout)
  }

  mounted () {
    this.painter = new M300LatestPainter(image => {
      const canvas = this.$refs.oledCanvas as HTMLCanvasElement | undefined
      if (!this.disposed && !this.collapsed && !document.hidden && canvas) {
        drawOledPixels(canvas, image, this.pixelLayout)
      }
    })
    window.addEventListener('resize', this.queuePixelLayout)
    window.addEventListener('scroll', this.queuePixelLayout, true)
    this.watchPixelRatio()
    this.observePixelViewport()
    this.queuePixelLayout()
    this.navigation = new M300NavigationEvents(async frame => {
      if (this.disposed) return
      this.navigationPreview = frame
      await this.$nextTick()
      this.paintFrame()
    }, active => { this.navigationActive = active })
    this.syncNavigation()
    document.addEventListener('visibilitychange', this.onVisibilityChange)
    this.schedulePoll(0)
    this.$nextTick(() => this.paintFrame())
  }

  beforeDestroy () {
    this.disposed = true
    this.navigation?.stop()
    this.pollEpoch++
    this.painter?.dispose()
    this.pixelObserver?.disconnect()
    this.unwatchPixelRatio()
    window.removeEventListener('resize', this.queuePixelLayout)
    window.removeEventListener('scroll', this.queuePixelLayout, true)
    if (this.pixelTick !== null) window.cancelAnimationFrame(this.pixelTick)
    this.pixelTick = null
    document.removeEventListener('visibilitychange', this.onVisibilityChange)
    this.clearPoll()
  }

  private clearPoll () {
    if (this.pollTimer !== null) {
      window.clearTimeout(this.pollTimer)
      this.pollTimer = null
    }
  }

  private schedulePoll (delay: number) {
    if (this.disposed || this.collapsed || document.hidden) return
    this.clearPoll()
    this.pollTimer = window.setTimeout(() => {
      this.poll().catch(() => undefined)
    }, delay)
  }

  private async poll () {
    this.pollTimer = null
    if (this.disposed || this.collapsed || document.hidden) return
    if (!this.socketReady || !this.klippyReady || !this.preview) {
      this.schedulePoll(RETRY_DELAY_MS)
      return
    }
    const epoch = this.pollEpoch
    try {
      const result = await SocketActions.printerObjectsQuery(
        { m300_oled: ['oled_preview'] }, { suppressError: true }
      )
      if (epoch !== this.pollEpoch || this.disposed) return
      const frame = readM300OledPreview(result.status)
      if (frame) this.polledPreview = frame
    } catch {
      // A failed query cannot change the printer's state. Socket reconnect
      // will reset local observation; no retries are sent concurrently.
    } finally {
      if (epoch === this.pollEpoch && !this.disposed) this.schedulePoll(POLL_DELAY_MS)
    }
  }

  private onVisibilityChange () {
    if (!document.hidden) this.restartPolling()
    else {
      this.clearPoll()
      this.syncNavigation()
    }
  }

  @Watch('navigationSupported')
  syncNavigation () {
    if (!this.disposed && !this.collapsed && !document.hidden &&
      this.socketReady && this.klippyReady && this.navigationSupported) {
      this.navigation?.start()
    } else {
      this.navigation?.stop()
      this.navigationPreview = null
    }
  }

  @Watch('socketReady')
  @Watch('klippyReady')
  @Watch('collapsed')
  onAvailabilityChanged () {
    this.restartPolling()
  }

  private restartPolling () {
    this.pollEpoch++
    this.clearPoll()
    this.polledPreview = null
    this.navigation?.stop()
    this.navigationPreview = null
    this.syncNavigation()
    this.painter?.clear()
    this.observePixelViewport()
    this.queuePixelLayout()
    this.schedulePoll(0)
    this.$nextTick(() => this.paintFrame())
  }

  @Watch('preview.image')
  onPreviewImageChanged () {
    this.$nextTick(() => this.paintFrame())
  }

  private paintFrame () {
    const uri = this.preview?.image
    const canvas = this.$refs.oledCanvas as HTMLCanvasElement | undefined
    if (!uri || !canvas || this.collapsed || document.hidden) {
      this.painter?.clear()
      return
    }
    this.painter?.submit(uri)
  }

  private observePixelViewport () {
    this.pixelObserver?.disconnect()
    this.$nextTick(() => {
      if (this.disposed || typeof ResizeObserver === 'undefined') return
      this.pixelObserver?.disconnect()
      const viewport = this.$refs.pixelViewport as HTMLElement | undefined
      if (viewport) {
        this.pixelObserver = new ResizeObserver(this.queuePixelLayout)
        this.pixelObserver.observe(viewport)
      }
    })
  }

  private unwatchPixelRatio () {
    const media = this.pixelMedia
    if (!media) return
    if (media.removeEventListener) media.removeEventListener('change', this.onPixelRatioChange)
    else media.removeListener(this.onPixelRatioChange)
    this.pixelMedia = null
  }

  private watchPixelRatio () {
    this.unwatchPixelRatio()
    if (!window.matchMedia) return
    const media = this.pixelMedia = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`)
    if (media.addEventListener) media.addEventListener('change', this.onPixelRatioChange)
    else media.addListener(this.onPixelRatioChange)
  }

  private onPixelRatioChange () {
    this.watchPixelRatio()
    this.queuePixelLayout()
  }

  private queuePixelLayout () {
    if (this.disposed || this.pixelTick !== null) return
    this.pixelTick = window.requestAnimationFrame(() => {
      this.pixelTick = null
      if (this.disposed) return
      this.pixelLayout = oledPixelLayout(window.devicePixelRatio)
      this.$nextTick(() => {
        if (this.disposed) return
        const canvas = this.$refs.oledCanvas as HTMLCanvasElement | undefined
        if (canvas) alignOledPixels(canvas, this.pixelLayout.dpr)
        this.painter?.redraw()
      })
    })
  }
}
</script>

<style scoped lang="scss">
.m300-oled-viewport {
  width: 100%;
  overflow-x: auto;
}
.m300-oled-frame,
.m300-oled-unavailable {
  display: block;
  margin: 0 auto;
  box-sizing: border-box;
  background: #020610;
}
.m300-oled-frame {
  image-rendering: pixelated;
}
.m300-oled-unavailable {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
