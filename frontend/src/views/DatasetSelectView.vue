<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import type { DatasetListItem } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const datasets = ref<DatasetListItem[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    datasets.value = await api.datasets()
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

    <PageState :loading="loading" :error="error" :empty="!datasets.length && !loading ? 'No LeRobot datasets found.' : ''" />

    <div class="dataset-grid">
      <RouterLink
        v-for="dataset in datasets"
        :key="dataset.name"
        class="dataset-card"
        :to="`/datasets/${dataset.name}/overview`"
      >
        <div>
          <p class="eyebrow">{{ dataset.codebase_version ?? 'unknown format' }}</p>
          <h2>{{ dataset.name }}</h2>
          <span>{{ dataset.robot_type ?? 'unknown robot' }}</span>
        </div>
        <div class="metric-row">
          <MetricCard label="Episodes" :value="dataset.total_episodes" />
          <MetricCard label="Frames" :value="dataset.total_frames" />
          <MetricCard label="FPS" :value="dataset.fps" />
        </div>
      </RouterLink>
    </div>
  </section>
</template>
