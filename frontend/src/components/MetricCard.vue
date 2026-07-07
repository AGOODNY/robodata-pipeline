<script setup lang="ts">
defineProps<{
  label: string
  value: string | number | null | undefined
  hint?: string
}>()
</script>

<template>
  <article class="metric-card">
    <span>{{ label }}</span>
    <strong>{{ value ?? 'N/A' }}</strong>
    <small v-if="hint">{{ hint }}</small>
  </article>
</template>
