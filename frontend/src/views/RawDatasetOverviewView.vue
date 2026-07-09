<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { RawDatasetSummary } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const summary = ref<RawDatasetSummary | null>(null)
const loading = ref(true)
const error = ref('')

function seconds(value: number | null) {
  return value == null ? 'N/A' : `${value.toFixed(2)}s`
}

onMounted(async () => {
  try {
    summary.value = await api.rawSummary(dataset.value)
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
        <p class="eyebrow">Raw Dataset Overview</p>
        <h1>{{ dataset }}</h1>
      </div>
    </header>

    <PageState :loading="loading" :error="error" />

    <template v-if="summary">
      <div class="metric-row">
        <MetricCard label="Format" :value="summary.format" />
        <MetricCard label="Episodes" :value="summary.total_episodes" />
        <MetricCard label="Frames" :value="summary.total_frames" />
        <MetricCard label="Seconds" :value="seconds(summary.total_seconds)" />
        <MetricCard label="Trigger Stops" :value="summary.trigger_stop_episodes" />
      </div>

      <div class="content-grid two-columns">
        <section class="panel">
          <h2>Cameras</h2>
          <table>
            <thead>
              <tr>
                <th>Camera</th>
                <th>Frames</th>
                <th>FPS</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="camera in summary.cameras" :key="camera.key">
                <td>{{ camera.key }}</td>
                <td>{{ camera.frame_count }}</td>
                <td>{{ camera.fps ?? 'N/A' }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Location</h2>
          <p class="path-text">{{ summary.path }}</p>
        </section>
      </div>
    </template>
  </section>
</template>
