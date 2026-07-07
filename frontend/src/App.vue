<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { api } from './api/client'
import type { DatasetListItem } from './api/types'

const route = useRoute()
const datasets = ref<DatasetListItem[]>([])
const routeDataset = computed(() => route.params.dataset as string | undefined)
const activeDataset = computed(() => routeDataset.value ?? datasets.value[0]?.name)

const navItems = computed(() => {
  if (!activeDataset.value) return []
  return [
    { label: 'Overview', to: `/datasets/${activeDataset.value}/overview` },
    { label: 'Episodes', to: `/datasets/${activeDataset.value}/episodes` },
    { label: 'Validation', to: `/datasets/${activeDataset.value}/validation` },
  ]
})

onMounted(async () => {
  try {
    datasets.value = await api.datasets()
  } catch {
    datasets.value = []
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark">R</span>
        <span>
          <strong>RoboData</strong>
          <small>Pipeline</small>
        </span>
      </RouterLink>

      <nav class="nav-section">
        <RouterLink to="/">Datasets</RouterLink>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
        <span v-if="!navItems.length" class="nav-placeholder">Select a dataset to unlock views</span>
      </nav>

      <div class="future-section">
        <span>Later Pipeline</span>
        <button disabled>Raw Viewer</button>
        <button disabled>Converter</button>
        <button disabled>Subtask Labels</button>
        <button disabled>Training Export</button>
      </div>
    </aside>

    <main class="main-panel">
      <RouterView />
    </main>
  </div>
</template>
