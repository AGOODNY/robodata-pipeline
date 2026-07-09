<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeDetail, VideoAsset } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const format = computed(() => route.params.format as string)
const episodeIndex = computed(() => Number(route.params.episode))
const episode = ref<EpisodeDetail | null>(null)
const loading = ref(true)
const error = ref('')
const selectedVideo = ref<VideoAsset | null>(null)

onMounted(async () => {
  try {
    episode.value = await api.episode(dataset.value, episodeIndex.value)
    selectedVideo.value = episode.value.videos.find((video) => video.exists) ?? episode.value.videos[0] ?? null
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
        <p class="eyebrow">Episode Player</p>
        <h1>{{ dataset }} / #{{ episodeIndex }}</h1>
      </div>
      <RouterLink class="button" :to="`/datasets/${format}/${dataset}/episodes/${episodeIndex}/series`">Open Curves</RouterLink>
    </header>

    <PageState :loading="loading" :error="error" />

    <template v-if="episode">
      <div class="metric-row">
        <MetricCard label="Length" :value="episode.length" />
        <MetricCard label="Task" :value="episode.tasks.join(', ')" />
        <MetricCard label="Dataset From" :value="episode.dataset_from_index" />
        <MetricCard label="Dataset To" :value="episode.dataset_to_index" />
      </div>

      <section class="panel player-panel">
        <div class="video-tabs">
          <button
            v-for="video in episode.videos"
            :key="video.relative_path"
            :class="{ active: selectedVideo?.relative_path === video.relative_path }"
            @click="selectedVideo = video"
          >
            {{ video.key }}
          </button>
        </div>

        <video v-if="selectedVideo?.exists" controls :src="selectedVideo.url"></video>
        <div v-else class="page-state">Video unavailable for this camera.</div>
      </section>
    </template>
  </section>
</template>
