<template>
  <span
    hidden
    aria-hidden="true"
  />
</template>

<script lang="ts">
import { Component, Mixins, Watch } from 'vue-property-decorator'
import StateMixin from '@/mixins/state'
import { readM300PadMesh } from '@/util/m300-pad-mesh'
import { padMeshError } from '@/util/m300-feedback'

@Component
export default class M300PadMeshObserver extends Mixins(StateMixin) {
  seenRun: string | null = null
  seenError: string | null = null

  get printActive () {
    const printer = this.$typedState.printer.printer
    return printer.print_stats?.state === 'printing' || printer.print_stats?.state === 'paused' ||
      printer.virtual_sdcard?.is_active === true
  }

  get errorId () {
    const printer = this.$typedState.printer.printer
    const error = this.klippyReady ? padMeshError(printer, readM300PadMesh(printer.m300_pad_mesh)) : undefined
    return error ? `${error.id}:${error.view_revision ?? 1}` : undefined
  }

  @Watch('errorId', { immediate: true })
  onError (id: string | undefined) {
    if (!id || id === this.seenError) return
    this.seenError = id
    this.showPanel()
  }

  get running () {
    const status = readM300PadMesh(this.$typedState.printer.printer.m300_pad_mesh)
    return this.klippyReady && status?.busy && status.state === 'PROBING' ? status.run_id : null
  }

  @Watch('running', { immediate: true })
  onRunning (run: string | null) {
    if (!run || run === this.seenRun) return
    this.seenRun = run
    this.showPanel()
  }

  showPanel () {
    // A mesh command inside a print file must not take over the job view.
    // Remember that run above so ending/pausing the file cannot replay it.
    if (!this.printActive && this.$route.name !== 'tune') {
      this.$router.push({ name: 'tune', query: this.$route.query }).catch(() => {})
    }
  }
}
</script>
