<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeDetail, EpisodeSeries, VideoAsset } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const format = computed(() => route.params.format as string)
const episodeIndex = computed(() => Number(route.params.episode))
const episode = ref<EpisodeDetail | null>(null)
const series = ref<EpisodeSeries | null>(null)
const loading = ref(true)
const error = ref('')
const selectedVideo = ref<VideoAsset | null>(null)
const currentTime = ref(0)
const videoPlaying = ref(false)
const videoDuration = ref(0)
const videoEl = ref<HTMLVideoElement | null>(null)
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let playbackFrame = 0
let lastMarkerTime = -1
const PROGRESS_MARKER_SERIES_ID = 'progress-marker-carrier'
const tooltipPosition: echarts.TooltipComponentPositionCallback = (point, _params, _el, _rect, size) => {
  const [viewWidth, viewHeight] = size.viewSize
  const [tooltipWidth, tooltipHeight] = size.contentSize
  const left = point[0] > viewWidth / 2
    ? Math.max(8, point[0] - tooltipWidth - 16)
    : Math.min(viewWidth - tooltipWidth - 8, point[0] + 16)
  const top = Math.max(8, Math.min(point[1] - tooltipHeight / 2, viewHeight - tooltipHeight - 8))
  return [left, top]
}

const hasSeriesData = computed(() => Boolean(series.value?.timestamp.length))
const totalFrames = computed(() => episode.value?.length || series.value?.timestamp.length || 0)
const totalSeconds = computed(() => videoDuration.value || series.value?.timestamp.at(-1) || 0)
const seriesDuration = computed(() => series.value?.timestamp.at(-1) || 0)
const frameStep = computed(() => {
  const timestamps = series.value?.timestamp ?? []
  for (let index = 1; index < timestamps.length; index += 1) {
    const step = timestamps[index] - timestamps[index - 1]
    if (step > 0) return step
  }
  return 1 / 30
})
const videoFrameStep = computed(() => {
  if (totalFrames.value > 1 && totalSeconds.value) return totalSeconds.value / (totalFrames.value - 1)
  return frameStep.value
})
const currentFrame = computed(() => {
  if (!totalFrames.value || !totalSeconds.value) return 0
  return Math.min(totalFrames.value, Math.round((currentTime.value / totalSeconds.value) * (totalFrames.value - 1)) + 1)
})

function seconds(value: number) {
  return `${value.toFixed(2)}s`
}

function progressMarkLine() {
  return {
    symbol: 'none',
    silent: true,
    lineStyle: { color: '#7e8781', type: 'dashed', width: 1.5 },
    label: { show: false },
    data: [{ xAxis: chartCurrentTime() }],
  }
}

function chartTimeMax() {
  return seriesDuration.value
}

function chartCurrentTime() {
  if (!seriesDuration.value || !videoDuration.value) return Math.min(currentTime.value, seriesDuration.value)
  return Math.min(seriesDuration.value, (currentTime.value / videoDuration.value) * seriesDuration.value)
}

function renderChart() {
  if (!chartEl.value || !series.value) return
  chart?.dispose()
  chart = echarts.init(chartEl.value)

  const stateNames = series.value.state_names.length ? series.value.state_names : series.value.action_names
  const actionNames = series.value.action_names.length ? series.value.action_names : stateNames
  const stateLines = stateNames.map((name, index) => ({
    name: `state.${name}`,
    type: 'line',
    symbol: 'none',
    data: series.value!.observation_state.map((row, rowIndex) => [series.value!.timestamp[rowIndex], row[index]]),
  }))
  const actionLines = actionNames.map((name, index) => ({
    name: `action.${name}`,
    type: 'line',
    symbol: 'none',
    lineStyle: { type: 'dashed' },
    data: series.value!.action.map((row, rowIndex) => [series.value!.timestamp[rowIndex], row[index]]),
  }))
  const chartSeries = [...stateLines, ...actionLines]

  chart.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      confine: true,
      enterable: true,
      extraCssText: 'max-height: 520px; overflow-y: auto;',
      position: tooltipPosition,
    },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 52, right: 24, top: 72, bottom: 48 },
    xAxis: { type: 'value', name: 'time (s)', min: 0, max: chartTimeMax() },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }],
    series: chartSeries.map((item, index) =>
      index === 0 ? { ...item, id: PROGRESS_MARKER_SERIES_ID, markLine: progressMarkLine() } : item,
    ),
  })
}

function updateMarker() {
  if (!chart) return
  chart.setOption({
    animation: false,
    xAxis: { max: chartTimeMax() },
    series: [{ id: PROGRESS_MARKER_SERIES_ID, markLine: progressMarkLine() }],
  })
  if (!videoPlaying.value) window.requestAnimationFrame(showCurrentTimeTooltip)
}

function showCurrentTimeTooltip() {
  if (!chart || !chartEl.value || videoPlaying.value || !hasSeriesData.value) return
  const x = chart.convertToPixel({ xAxisIndex: 0 }, chartCurrentTime())
  if (typeof x !== 'number') return
  chart.dispatchAction({
    type: 'showTip',
    x,
    y: Math.max(80, chartEl.value.clientHeight / 2),
  })
}

function hideCurrentTimeTooltip() {
  chart?.dispatchAction({ type: 'hideTip' })
}

function syncVideoTime(event: Event) {
  currentTime.value = (event.currentTarget as HTMLVideoElement).currentTime
  lastMarkerTime = currentTime.value
  updateMarker()
}

function handleVideoPlay(event: Event) {
  videoPlaying.value = true
  hideCurrentTimeTooltip()
  syncVideoTime(event)
  trackVideoProgress()
}

function handleVideoPause(event: Event) {
  videoPlaying.value = false
  window.cancelAnimationFrame(playbackFrame)
  syncVideoTime(event)
}

function handleLoadedMetadata(event: Event) {
  const video = event.currentTarget as HTMLVideoElement
  videoDuration.value = Number.isFinite(video.duration) ? video.duration : 0
  syncVideoTime(event)
}

function trackVideoProgress() {
  const video = videoEl.value
  if (!video || !videoPlaying.value || video.paused) return
  if (Math.abs(video.currentTime - lastMarkerTime) >= videoFrameStep.value * 0.75) {
    currentTime.value = video.currentTime
    lastMarkerTime = currentTime.value
    updateMarker()
  }
  playbackFrame = window.requestAnimationFrame(trackVideoProgress)
}

async function togglePlayback() {
  const video = videoEl.value
  if (!video) return
  if (video.paused) await video.play()
  else video.pause()
}

function seekTo(time: number) {
  const video = videoEl.value
  if (!video) return
  video.pause()
  video.currentTime = Math.min(Math.max(time, 0), totalSeconds.value)
  currentTime.value = video.currentTime
  lastMarkerTime = currentTime.value
  updateMarker()
}

function previousFrame() {
  seekTo(currentTime.value - videoFrameStep.value)
}

function nextFrame() {
  seekTo(currentTime.value + videoFrameStep.value)
}

function seekFromControl(event: Event) {
  seekTo(Number((event.target as HTMLInputElement).value))
}

function resizeChart() {
  chart?.resize()
}

watch(selectedVideo, () => {
  videoEl.value?.pause()
  videoPlaying.value = false
  videoDuration.value = 0
  currentTime.value = 0
  lastMarkerTime = 0
  updateMarker()
})

onMounted(async () => {
  try {
    episode.value = await api.episode(dataset.value, episodeIndex.value)
    selectedVideo.value = episode.value.videos.find((video) => video.exists) ?? episode.value.videos[0] ?? null
    series.value = await api.series(dataset.value, episodeIndex.value)
    await nextTick()
    renderChart()
    updateMarker()
    window.addEventListener('resize', resizeChart)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.cancelAnimationFrame(playbackFrame)
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Episode Player</p>
        <h1>{{ dataset }} / #{{ episodeIndex }}</h1>
      </div>
      <RouterLink class="button" :to="`/datasets/${format}/${dataset}/episodes`">Episodes</RouterLink>
    </header>

    <PageState :loading="loading" :error="error" />

    <template v-if="episode">
      <div class="metric-row">
        <MetricCard label="Frame" :value="totalFrames ? `${currentFrame} / ${totalFrames}` : 'N/A'" />
        <MetricCard label="Seconds" :value="`${seconds(currentTime)} / ${seconds(totalSeconds)}`" />
        <MetricCard label="Task" :value="episode.tasks.join(', ')" />
        <MetricCard label="Dataset Range" :value="`${episode.dataset_from_index} - ${episode.dataset_to_index}`" />
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

        <video
          v-if="selectedVideo?.exists"
          ref="videoEl"
          :src="selectedVideo.url"
          @loadedmetadata="handleLoadedMetadata"
          @play="handleVideoPlay"
          @pause="handleVideoPause"
          @timeupdate="syncVideoTime"
          @seeking="syncVideoTime"
        ></video>
        <div v-else class="page-state">Video unavailable for this camera.</div>

        <div class="raw-controls">
          <button
            class="play-control"
            :aria-label="videoPlaying ? 'Pause playback' : 'Play video'"
            :title="videoPlaying ? 'Pause playback' : 'Play video'"
            :disabled="!selectedVideo?.exists"
            @click="togglePlayback"
          >
            <span v-if="videoPlaying" aria-hidden="true">&#10074;&#10074;</span>
            <span v-else aria-hidden="true">&#9654;</span>
            {{ videoPlaying ? 'Pause' : 'Play' }}
          </button>
          <button
            class="frame-control"
            aria-label="Previous frame"
            title="Previous frame"
            :disabled="!selectedVideo?.exists || currentTime <= 0"
            @click="previousFrame"
          >
            <span aria-hidden="true">&#9664;</span>
            Prev
          </button>
          <button
            class="frame-control"
            aria-label="Next frame"
            title="Next frame"
            :disabled="!selectedVideo?.exists || currentTime >= totalSeconds"
            @click="nextFrame"
          >
            Next
            <span aria-hidden="true">&#9654;</span>
          </button>
          <input
            type="range"
            min="0"
            :max="totalSeconds"
            :step="videoFrameStep"
            :value="currentTime"
            :disabled="!selectedVideo?.exists"
            @input="seekFromControl"
          />
          <span>{{ seconds(currentTime) }}</span>
        </div>
      </section>

      <section class="panel chart-panel">
        <h2>State / Action Curves</h2>
        <div v-if="hasSeriesData" ref="chartEl" class="chart"></div>
        <div v-else class="page-state">No state or action series found for this episode.</div>
      </section>
    </template>
  </section>
</template>
