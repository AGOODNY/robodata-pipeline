<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeListItem } from '../api/types'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const episodes = ref<EpisodeListItem[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    episodes.value = await api.episodes(dataset.value)
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
        <p class="eyebrow">Episode Index</p>
        <h1>{{ dataset }}</h1>
      </div>
    </header>

    <PageState :loading="loading" :error="error" />

    <section v-if="episodes.length" class="panel">
      <table>
        <thead>
          <tr>
            <th>Episode</th>
            <th>Task</th>
            <th>Length</th>
            <th>Dataset Range</th>
            <th>Videos</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="episode in episodes" :key="episode.episode_index">
            <td>#{{ episode.episode_index }}</td>
            <td>{{ episode.tasks.join(', ') }}</td>
            <td>{{ episode.length }}</td>
            <td>{{ episode.dataset_from_index }} - {{ episode.dataset_to_index }}</td>
            <td>
              <span
                v-for="video in episode.videos"
                :key="video.relative_path"
                class="status-pill"
                :class="{ muted: !video.exists }"
              >
                {{ video.key }}: {{ video.exists ? 'ready' : 'missing' }}
              </span>
            </td>
            <td class="table-actions">
              <RouterLink :to="`/datasets/${dataset}/episodes/${episode.episode_index}`">Player</RouterLink>
              <RouterLink :to="`/datasets/${dataset}/episodes/${episode.episode_index}/series`">Series</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>
