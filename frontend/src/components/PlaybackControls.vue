<script setup lang="ts">
import PlaybackRateControl from './PlaybackRateControl.vue'

defineProps<{
  playing: boolean
  disabled?: boolean
  atStart: boolean
  atEnd: boolean
  position: number
  max: number
  step: number
  timeLabel: string
}>()

const playbackRate = defineModel<number>('playbackRate', { required: true })
const emit = defineEmits<{
  toggle: []
  previous: []
  next: []
  seek: [value: number]
}>()

function seek(event: Event) {
  emit('seek', Number((event.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="playback-controls">
    <button
      class="play-control"
      :disabled="disabled"
      :aria-label="playing ? 'Pause playback' : 'Play'"
      :title="playing ? 'Pause playback' : 'Play'"
      @click="emit('toggle')"
    >
      <span v-if="playing" aria-hidden="true">&#10074;&#10074;</span>
      <span v-else aria-hidden="true">&#9654;</span>
      {{ playing ? 'Pause' : 'Play' }}
    </button>
    <button class="frame-control" :disabled="disabled || atStart" aria-label="Previous frame" title="Previous frame" @click="emit('previous')">
      <span aria-hidden="true">&#9664;</span> Prev
    </button>
    <button class="frame-control" :disabled="disabled || atEnd" aria-label="Next frame" title="Next frame" @click="emit('next')">
      Next <span aria-hidden="true">&#9654;</span>
    </button>
    <PlaybackRateControl v-model="playbackRate" :disabled="disabled" />
    <input type="range" min="0" :max="max" :step="step" :value="position" :disabled="disabled" @input="seek" />
    <span>{{ timeLabel }}</span>
  </div>
</template>
