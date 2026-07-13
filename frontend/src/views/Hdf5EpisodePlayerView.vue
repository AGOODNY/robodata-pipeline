<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeDetail, EpisodeSeries, Hdf5Camera, RawFrame } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'
import PlaybackControls from '../components/PlaybackControls.vue'
import { useFramePlayback } from '../composables/useFramePlayback'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const episodeIndex = computed(() => Number(route.params.episode))
const episode = ref<EpisodeDetail | null>(null)
const series = ref<EpisodeSeries | null>(null)
const frames = ref<RawFrame[]>([])
const cameras = ref<Hdf5Camera[]>([])
const camera = ref('')
const frameIndex = ref(0)
const playing = ref(false)
const playbackRate = ref(1)
const error = ref(''); const loading = ref(true)
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const PROGRESS_MARKER_SERIES_ID = 'hdf5-progress-marker'
const current = computed(() => frames.value[frameIndex.value] ?? null)
const seconds = computed(() => current.value && frames.value[0] ? current.value.timestamp - frames.value[0].timestamp : 0)
const totalSeconds = computed(() => frames.value.length > 1 ? frames.value.at(-1)!.timestamp - frames.value[0].timestamp : 0)
const frameStep = computed(() => {
  for (let index = 1; index < frames.value.length; index += 1) {
    const step = frames.value[index].timestamp - frames.value[index - 1].timestamp
    if (step > 0) return step
  }
  return 1 / 30
})

const { frameRendered } = useFramePlayback({
  playing,
  playbackRate,
  frameIndex,
  frameCount: () => frames.value.length,
  frameDurationMs: () => frameStep.value * 1000,
})

async function loadFrames() {
  if (!camera.value) {
    frames.value = []
    return
  }
  const loaded = (await api.hdf5Frames(dataset.value, episodeIndex.value, camera.value)).frames
  frames.value = loaded.map((frame) => ({ ...frame, url: frame.url.startsWith('/hdf5-media/') ? `/api${frame.url}` : frame.url }))
  frameIndex.value = 0
}

async function selectCamera(key: string) {
  if (key === camera.value) return
  playing.value = false
  frameIndex.value = 0
  camera.value = key
  error.value = ''
  try { await loadFrames() }
  catch (err) { error.value = err instanceof Error ? err.message : String(err); frames.value = [] }
}

function previousFrame() {
  playing.value = false
  frameIndex.value = Math.max(0, frameIndex.value - 1)
}

function advanceFrame() {
  frameIndex.value = Math.min(Math.max(frames.value.length - 1, 0), frameIndex.value + 1)
}

function nextFrame() {
  playing.value = false
  advanceFrame()
}

function progressMarkLine() {
  return {
    symbol: 'none',
    silent: true,
    lineStyle: { color: '#7e8781', type: 'dashed', width: 1.5 },
    label: { show: false },
    data: [{ xAxis: seconds.value }],
  }
}

function renderChart() {
  if (!chartEl.value || !series.value) return
  chart?.dispose(); chart = echarts.init(chartEl.value)
  const stateNames = series.value.state_names
  const actionNames = series.value.action_names.length ? series.value.action_names : stateNames
  const startTimestamp = series.value.timestamp[0] ?? 0
  const stateLines = stateNames.map((name, index) => ({ name: `state.${name}`, type: 'line', symbol: 'none', data: series.value!.timestamp.map((stamp, row) => [stamp - startTimestamp, series.value!.observation_state[row][index]]) }))
  const actionLines = actionNames.map((name, index) => ({ name: `action.${name}`, type: 'line', symbol: 'none', lineStyle: { type: 'dashed' }, data: series.value!.timestamp.map((stamp, row) => [stamp - startTimestamp, series.value!.action[row][index]]) }))
  const chartSeries = [...stateLines, ...actionLines]
  chart.setOption({ animation: false, tooltip: { trigger: 'axis', confine: true, enterable: true, extraCssText: 'max-height: 520px; overflow-y: auto;' }, legend: { type: 'scroll', top: 0 }, grid: { left: 52, right: 24, top: 72, bottom: 48 }, xAxis: { type: 'value', name: 'time (s)', min: 0, max: totalSeconds.value }, yAxis: { type: 'value', scale: true }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }], series: chartSeries.map((item, index) => index === 0 ? { ...item, id: PROGRESS_MARKER_SERIES_ID, markLine: progressMarkLine() } : item) })
}

function updateMarker() {
  if (!chart) return
  chart.setOption({ animation: false, series: [{ id: PROGRESS_MARKER_SERIES_ID, markLine: progressMarkLine() }] })
  if (!playing.value) window.requestAnimationFrame(showCurrentFrameTooltip)
}

function showCurrentFrameTooltip() {
  if (!chart || !chartEl.value || playing.value || !series.value?.timestamp.length) return
  const x = chart.convertToPixel({ xAxisIndex: 0 }, seconds.value)
  if (typeof x !== 'number') return
  chart.dispatchAction({ type: 'showTip', x, y: Math.max(80, chartEl.value.clientHeight / 2) })
}

function hideCurrentFrameTooltip() { chart?.dispatchAction({ type: 'hideTip' }) }

function resizeChart() { chart?.resize() }

watch(playing, (value) => {
  if (value) {
    hideCurrentFrameTooltip()
  } else {
    updateMarker()
  }
})
watch(frameIndex, updateMarker)
onMounted(async () => { try { episode.value = await api.episode(dataset.value, episodeIndex.value); series.value = await api.series(dataset.value, episodeIndex.value); cameras.value = (await api.hdf5Cameras(dataset.value, episodeIndex.value)).cameras; if (!cameras.value.length) throw new Error('No RGB frames stored in this HDF5 episode'); camera.value = cameras.value[0].key; await loadFrames(); await nextTick(); renderChart(); updateMarker(); window.addEventListener('resize', resizeChart) } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { loading.value = false } })
onUnmounted(() => { window.removeEventListener('resize', resizeChart); chart?.dispose() })
</script>

<template>
  <section class="page"><header class="page-header"><div><p class="eyebrow">HDF5 Player</p><h1>{{ dataset }} / #{{ episodeIndex }}</h1></div><RouterLink class="button" :to="`/datasets/hdf5/${dataset}/episodes`">Episodes</RouterLink></header><PageState :loading="loading" :error="error" />
  <template v-if="episode"><div class="metric-row"><MetricCard label="Format" value="HDF5" /><MetricCard label="Frame" :value="frames.length ? `${frameIndex + 1} / ${frames.length}` : 'N/A'" /><MetricCard label="Seconds" :value="`${seconds.toFixed(2)}s / ${totalSeconds.toFixed(2)}s`" /><MetricCard label="Task" :value="episode.tasks.join(', ')" /></div>
      <section class="panel raw-player-panel"><div class="video-tabs"><button v-for="item in cameras" :key="item.key" :class="{ active: camera === item.key }" :disabled="!item.frame_count" @click="selectCamera(item.key)">{{ item.key }} ({{ item.frame_count }})</button></div><div class="raw-frame-stage"><img v-if="current" :src="current.url" :alt="`${camera} frame ${frameIndex + 1}`" @load="frameRendered" @error="frameRendered" /><div v-else class="page-state">No RGB frame available.</div></div><PlaybackControls v-model:playback-rate="playbackRate" :playing="playing" :disabled="!frames.length" :at-start="frameIndex === 0" :at-end="frameIndex >= frames.length - 1" :position="frameIndex" :max="Math.max(frames.length - 1, 0)" :step="1" :time-label="`${seconds.toFixed(2)}s`" @toggle="playing = !playing" @previous="previousFrame" @next="nextFrame" @seek="playing = false; frameIndex = $event" /></section>
      <section class="panel chart-panel"><h2>State / Action Curves</h2><div v-if="series?.timestamp.length" ref="chartEl" class="chart"></div><div v-else class="page-state">No state or action series found.</div></section>
    </template></section>
</template>
