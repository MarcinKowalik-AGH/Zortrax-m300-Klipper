<!-- Marcin Kowalik <mkowalik@agh.edu.pl> -->
<!-- M300OledTimers.vue - Wyświetla suwaki DIM i SLEEP oraz wysyła wybraną parę minut po zatwierdzeniu. -->
<template>
  <div class="m300-timers">
    <div>
      <label>
        Dim after {{ dim }} min
        <input
          v-model.number="dim"
          type="range"
          min="1"
          max="60"
          step="1"
        >
      </label>
      <label>
        Sleep after {{ sleep }} min
        <input
          v-model.number="sleep"
          type="range"
          min="1"
          max="60"
          step="1"
        >
      </label>
      <small v-if="dim > sleep">Sleep must be at or after dimming.</small>
      <v-btn
        small
        color="primary"
        :disabled="dim > sleep"
        @click="$emit('save', 'ZORTRAX_OLED_TIMERS DIM=' + dim + ' SLEEP=' + sleep)"
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

@Component
export default class M300OledTimers extends Vue {
  @Prop({ type: String, required: true }) readonly values!: string

  dim = 1
  sleep = 1

  @Watch('values', { immediate: true })
  loadTimers (values: string) {
    const [, dim, sleep] = values.split(' ')
    this.dim = Number(dim)
    this.sleep = Number(sleep)
  }
}
</script>
<style scoped>
.m300-timers { display: flex; align-items: center; gap: 1.25rem; }
.m300-timers > div { flex: 1; }
.m300-timers label, .m300-timers input { display: block; width: 100%; margin-bottom: .5rem; }
.m300-timers small { display: block; }
.m300-moon { font-size: 2rem; animation: moon-fade 3s ease-in-out infinite alternate; }
@keyframes moon-fade { to { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { .m300-moon { animation: none; } }
</style>
