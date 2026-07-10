<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { DatasetSummary } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const formatLabel = computed(() => route.params.format === 'lerobot_v21' ? 'LeRobot 2.1' : route.params.format === 'hdf5' ? 'RoboData HDF5' : 'LeRobot 3.0')
const summary = ref<DatasetSummary | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    summary.value = await api.summary(dataset.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

const featureRows = computed(() =>
  Object.entries(summary.value?.features ?? {}).map(([name, feature]) => ({
    name,
    dtype: feature.dtype,
    shape: Array.isArray(feature.shape) ? feature.shape.join(' x ') : 'N/A',
  })),
)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">{{ formatLabel }} Overview</p>
        <h1>{{ dataset }}</h1>
      </div>
    </header>

    <PageState :loading="loading" :error="error" />

    <template v-if="summary">
      <div class="metric-row">
        <MetricCard label="Format" :value="summary.codebase_version" />
        <MetricCard label="Robot" :value="summary.robot_type" />
        <MetricCard label="Episodes" :value="summary.total_episodes" />
        <MetricCard label="Frames" :value="summary.total_frames" />
        <MetricCard label="Tasks" :value="summary.total_tasks" />
        <MetricCard label="FPS" :value="summary.fps" />
      </div>

      <div class="content-grid two-columns">
        <section class="panel">
          <h2>Tasks</h2>
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Index</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="task in summary.tasks" :key="String(task.task)">
                <td>{{ task.task }}</td>
                <td>{{ task.task_index }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Features</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Shape</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feature in featureRows" :key="feature.name">
                <td>{{ feature.name }}</td>
                <td>{{ feature.dtype }}</td>
                <td>{{ feature.shape }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </template>
  </section>
</template>
