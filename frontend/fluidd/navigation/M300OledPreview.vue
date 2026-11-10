<template>
  <section
    v-if="preview"
    class="m300-oled-preview"
    :data-navigation="navigationActive ? 'event' : 'fallback'"
    data-preview-revision="NAV-PIPELINE-2"
    data-zoom-controls="OLED-ZOOM-1"
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
    <div v-if="!collapsed" class="m300-oled-display-row px-3 pb-3">
      <div
        ref="pixelViewport"
        class="m300-oled-viewport"
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
      <div
        class="m300-oled-zoom-controls"
        role="group"
        aria-label="OLED preview pixel zoom"
      >
        <button
          v-for="level in zoomLevels"
          :key="level"
          type="button"
          class="m300-oled-zoom-button"
          :class="{ 'm300-oled-zoom-button--selected': zoom === level }"
          :aria-label="`Set OLED zoom to ${level} times`"
          :aria-pressed="zoom === level ? 'true' : 'false'"
          :title="`OLED ×${level} — square pixels`"
          @click="setZoom(level)"
        >
          ×{{ level }}
        </button>
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
import { oledPixelLayout, oledPixelStyle, alignOledPixels, drawOledPixels, parseOledZoom, type OledZoom } from '@/util/m300-oled-pixels'
import { readM300OledPreview, selectM300OledPreview, type M300OledPreviewStatus } from '@/util/m300-oled-preview'

// Preserve the existing animation/fallback cadence. Menu navigation uses
// its own event wait below, outside objects/query and the status cache.
const POLL_DELAY_MS = 85
const RETRY_DELAY_MS = 350
const OLED_ZOOM_STORAGE_KEY = 'm300-oled-preview-zoom'

function restoredOledZoom (): OledZoom {
  // Storage might be disabled in privacy mode. It must never affect rendering.
  try {
    return parseOledZoom(window.localStorage.getItem(OLED_ZOOM_STORAGE_KEY))
  } catch {
    return 1
  }
}

@Component({})
export default class M300OledPreview extends Mixins(StateMixin) {
  collapsed = false
  polledPreview: M300OledPreviewStatus | null = null
  navigationPreview: M300OledPreviewStatus | null = null
  navigationActive = false
  zoom: OledZoom = restoredOledZoom()
  readonly zoomLevels: OledZoom[] = [1, 2, 3]
  private navigation: M300NavigationEvents | null = null
  pixelLayout = oledPixelLayout(window.devicePixelRatio, this.zoom)
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

  setZoom (zoom: OledZoom) {
    if (this.zoom === zoom) return
    this.zoom = zoom
    try {
      window.localStorage.setItem(OLED_ZOOM_STORAGE_KEY, String(zoom))
    } catch {
      // Browsers denying storage still support the live zoom controls.
    }
    // Paint the cached decoded image at the new scale; do not request
    // another frame or interfere with the fast navigation channel.
    this.queuePixelLayout()
  }

  private queuePixelLayout () {
    if (this.disposed || this.pixelTick !== null) return
    this.pixelTick = window.requestAnimationFrame(() => {
      this.pixelTick = null
      if (this.disposed) return
      this.pixelLayout = oledPixelLayout(window.devicePixelRatio, this.zoom)
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
.m300-oled-display-row {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 8px;
  min-width: 0;
}
.m300-oled-viewport {
  flex: 0 1 auto;
  min-width: 0;
  max-width: calc(100% - 52px);
  overflow-x: auto;
}
.m300-oled-zoom-controls {
  display: flex;
  flex: 0 0 40px;
  flex-direction: column;
  gap: 4px;
  padding: 4px;
  background: #020610;
  border: 1px solid #17546d;
  border-radius: 2px;
}
.m300-oled-zoom-button {
  box-sizing: border-box;
  width: 30px;
  height: 26px;
  padding: 0;
  color: #00ccee;
  background: #020610;
  border: 1px solid #17546d;
  border-radius: 0;
  font: 700 12px/1 "Courier New", monospace;
  text-align: center;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.m300-oled-zoom-button:hover,
.m300-oled-zoom-button:focus-visible {
  border-color: #20e7ff;
  outline: 1px solid #20e7ff;
  outline-offset: 1px;
}
.m300-oled-zoom-button--selected {
  color: #c6faff;
  background: #07536b;
  border-color: #20e7ff;
  box-shadow: inset 0 0 0 1px #0f89aa;
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
