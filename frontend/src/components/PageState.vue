<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string
  empty?: string
}>()
</script>

<template>
  <div v-if="loading" class="page-state">Loading data...</div>
  <div v-else-if="error" class="page-state page-state-error">{{ error }}</div>
  <div v-else-if="empty" class="page-state">{{ empty }}</div>
</template>
