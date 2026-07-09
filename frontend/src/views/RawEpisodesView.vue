<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { RawEpisodeListItem } from '../api/types'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const episodes = ref<RawEpisodeListItem[]>([])
const loading = ref(true)
const error = ref('')

function seconds(value: number | null) {
  return value == null ? 'N/A' : `${value.toFixed(2)}s`
}

onMounted(async () => {
  try {
    episodes.value = await api.rawEpisodes(dataset.value)
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
        <p class="eyebrow">Raw Episodes</p>
        <h1>{{ dataset }}</h1>
      </div>
      <RouterLink class="button" to="/">Datasets</RouterLink>
    </header>

    <PageState :loading="loading" :error="error" :empty="!episodes.length && !loading ? 'No raw episodes found.' : ''" />

    <section v-if="episodes.length" class="panel">
      <table>
        <thead>
          <tr>
            <th>Episode</th>
            <th>Frames</th>
            <th>Seconds</th>
            <th>Cameras</th>
            <th>Stop Trigger</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="episode in episodes" :key="episode.name">
            <td>{{ episode.name }}</td>
            <td>{{ episode.frame_count }}</td>
            <td>{{ seconds(episode.duration_seconds) }}</td>
            <td>
              <span v-for="camera in episode.cameras" :key="camera.key" class="status-pill">
                {{ camera.key }}: {{ camera.frame_count }}
              </span>
            </td>
            <td>
              <span class="status-pill" :class="{ muted: !episode.has_gripper_trigger_stop }">
                {{ episode.has_gripper_trigger_stop ? 'gripper double click' : 'none' }}
              </span>
            </td>
            <td class="table-actions">
              <RouterLink :to="`/datasets/raw/${dataset}/episodes/${episode.name}`">Player</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>
