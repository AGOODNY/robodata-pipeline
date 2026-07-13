<script setup lang="ts">
defineProps<{ disabled?: boolean }>()
const playbackRate = defineModel<number>({ required: true })

const rates = [
  { value: 0.5, label: '0.5×' },
  { value: 1, label: '1×' },
  { value: 1.5, label: '1.5×' },
  { value: 2, label: '2.0×' },
]
</script>

<template>
  <label class="playback-rate-control">
    <span>Speed</span>
    <select v-model.number="playbackRate" :disabled="disabled" aria-label="Playback speed">
      <option v-for="rate in rates" :key="rate.value" :value="rate.value">{{ rate.label }}</option>
    </select>
  </label>
</template>
