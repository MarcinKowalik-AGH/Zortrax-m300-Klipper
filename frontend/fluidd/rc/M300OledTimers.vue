<!-- Marcin Kowalik <mkowalik@agh.edu.pl> -->
<!-- M300OledTimers.vue - Wyświetla suwaki DIM i SLEEP oraz wysyła wybraną parę minut po zatwierdzeniu. -->
<template>
  <div class="m300-timers">
    <div>
      <m300-segmented-slider
        v-if="field !== 'sleep'"
        :value="Math.min(preferred, sleep)"
        label="DIM"
        :max="60"
        unit="min"
        @input="preferred = $event"
      />
      <m300-segmented-slider
        v-if="field !== 'dim'"
        v-model="sleep"
        label="SLEEP"
        :max="60"
        unit="min"
      />
      <small v-if="preferred > sleep">DIM {{ sleep }} min · preferred {{ preferred }} min</small>
      <v-btn
        small
        color="primary"
        :disabled="!changes.length"
        @click="$emit('save', 'M300_OLED_TIMERS ' + changes.join(' '))"
      >
        Save
      </v-btn>
    </div>
    <span
      class="m300-moon"
      aria-hidden="true"
    >☾</span>
  </div>
</template>
<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import M300SegmentedSlider from './M300SegmentedSlider.vue'

@Component({ components: { M300SegmentedSlider } })
export default class M300OledTimers extends Vue {
  @Prop({ type: String, required: true }) readonly values!: string

  @Prop({ type: String, default: 'both' }) readonly field!: 'dim' | 'sleep' | 'both'

  savedDim = 1
  savedSleep = 1
  preferred = 1
  sleep = 1

  @Watch('values', { immediate: true })
  loadTimers (values: string) {
    const [, dim, sleep, preferred] = values.split(' ')
    this.preferred = this.savedDim = Number(preferred ?? dim)
    this.sleep = this.savedSleep = Number(sleep)
  }

  get changes () {
    const args: string[] = []
    if (this.field !== 'sleep' && this.savedDim !== this.preferred) args.push('DIM=' + this.preferred)
    if (this.field !== 'dim' && this.savedSleep !== this.sleep) args.push('SLEEP=' + this.sleep)
    return args
  }
}
</script>
<style scoped>
.m300-timers { display: flex; align-items: center; gap: 1.25rem; }
.m300-timers > div { flex: 1; min-width: 0; }
.m300-timers label { margin-bottom: .5rem; }
.m300-timers small { display: block; }
.m300-moon { font-size: 2rem; animation: moon-fade 3s ease-in-out infinite alternate; }
@keyframes moon-fade { to { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .m300-moon { animation: none; } }
</style>
