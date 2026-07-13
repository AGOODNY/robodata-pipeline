<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { api } from './api/client'
import type { CatalogDataset } from './api/types'

const route = useRoute()
const datasets = ref<CatalogDataset[]>([])
const routeDataset = computed(() => route.params.dataset as string | undefined)
const routeFormat = computed(() => (route.params.format as string | undefined)
  ?? (route.path.startsWith('/datasets/raw/') ? 'raw' : route.path.startsWith('/datasets/hdf5/') ? 'hdf5' : undefined))
const activeDataset = computed(() =>
  datasets.value.find((dataset) => dataset.name === routeDataset.value && dataset.format === routeFormat.value),
)
const datasetRouteRoot = computed(() => routeDataset.value && routeFormat.value
  ? `/datasets/${routeFormat.value}/${routeDataset.value}`
  : '')
const overviewActive = computed(() => Boolean(datasetRouteRoot.value) && route.path === `${datasetRouteRoot.value}/overview`)
const episodesActive = computed(() => Boolean(datasetRouteRoot.value) && (
  route.path === `${datasetRouteRoot.value}/episodes`
  || route.path.startsWith(`${datasetRouteRoot.value}/episodes/`)
))

onMounted(async () => {
  try {
    datasets.value = await api.catalog()
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
        <div class="visualization-nav">
          <RouterLink to="/">Visualization</RouterLink>
          <details v-if="routeDataset && routeFormat" class="dataset-menu" open>
            <summary>
              <span>{{ activeDataset?.format_label ?? routeFormat }}</span>
              <strong>{{ routeDataset }}</strong>
            </summary>
            <RouterLink :to="`/datasets/${routeFormat}/${routeDataset}/overview`" :class="{ 'router-link-active': overviewActive }">Overview</RouterLink>
            <RouterLink :to="`/datasets/${routeFormat}/${routeDataset}/episodes`" :class="{ 'router-link-active': episodesActive }">Episodes</RouterLink>
          </details>
          <span v-else class="nav-placeholder">Select a dataset to unlock views</span>
        </div>
        <RouterLink to="/converter">Converter</RouterLink>
      </nav>

    </aside>

    <main class="main-panel">
      <RouterView />
    </main>
  </div>
</template>
