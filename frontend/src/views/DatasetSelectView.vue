<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { CatalogDataset, DatasetFormat } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const datasets = ref<CatalogDataset[]>([])
const loading = ref(true)
const error = ref('')
const sections: Array<{ format: DatasetFormat; label: string }> = [
  { format: 'lerobot_v21', label: 'LeRobot 2.1' },
  { format: 'lerobot_v30', label: 'LeRobot 3.0' },
  { format: 'raw', label: 'Raw' },
]

const groupedDatasets = computed(() =>
  sections.map((section) => ({
    ...section,
    datasets: datasets.value.filter((dataset) => dataset.format === section.format),
  })),
)

onMounted(async () => {
  try {
    datasets.value = await api.catalog()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Workspace</p>
        <h1>Datasets</h1>
      </div>
    </header>

    <PageState :loading="loading" :error="error" :empty="!datasets.length && !loading ? 'No datasets found.' : ''" />

    <div v-if="datasets.length" class="dataset-sections">
      <section v-for="section in groupedDatasets" :key="section.format" class="dataset-section">
        <header>
          <h2>{{ section.label }}</h2>
          <span>{{ section.datasets.length }} dataset{{ section.datasets.length === 1 ? '' : 's' }}</span>
        </header>
        <div v-if="section.datasets.length" class="dataset-grid">
          <RouterLink
            v-for="dataset in section.datasets"
            :key="`${dataset.format}:${dataset.name}`"
            class="dataset-card"
            :to="`/datasets/${dataset.format}/${dataset.name}/overview`"
          >
            <div>
              <p class="eyebrow">{{ dataset.format_label }}</p>
              <h2>{{ dataset.name }}</h2>
              <span>{{ dataset.robot_type ?? dataset.path }}</span>
            </div>
            <div class="metric-row">
              <MetricCard label="Episodes" :value="dataset.total_episodes" />
              <MetricCard label="Frames" :value="dataset.total_frames" />
              <MetricCard label="FPS" :value="dataset.fps" />
            </div>
          </RouterLink>
        </div>
        <div v-else class="page-state compact-state">No {{ section.label }} datasets found.</div>
      </section>
    </div>
  </section>
</template>
