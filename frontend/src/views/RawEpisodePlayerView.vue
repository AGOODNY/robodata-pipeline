<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { RawEpisodeDetail, RawEpisodeSeries, RawFrame } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const episodeName = computed(() => route.params.episode as string)
const episode = ref<RawEpisodeDetail | null>(null)
const series = ref<RawEpisodeSeries | null>(null)
const frames = ref<RawFrame[]>([])
const selectedCamera = ref('pikaGripperDepthCamera')
const currentIndex = ref(0)
const playing = ref(false)
const loading = ref(true)
const error = ref('')
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let timer = 0

const currentFrame = computed(() => frames.value[currentIndex.value] ?? null)
const firstTimestamp = computed(() => frames.value[0]?.timestamp ?? currentFrame.value?.timestamp ?? 0)
const currentSeconds = computed(() => (currentFrame.value ? currentFrame.value.timestamp - firstTimestamp.value : 0))
const totalSeconds = computed(() => episode.value?.duration_seconds ?? currentSeconds.value)

function seconds(value: number | null | undefined) {
  return value == null ? 'N/A' : `${value.toFixed(2)}s`
}

function selectedCameraFps() {
  const camera = episode.value?.cameras.find((item) => item.key === selectedCamera.value)
  return camera?.fps ?? 30
}

async function loadFrames() {
  const response = await api.rawFrames(dataset.value, episodeName.value, selectedCamera.value)
  frames.value = response.frames
  currentIndex.value = Math.min(currentIndex.value, Math.max(response.frames.length - 1, 0))
}

function previousFrame() {
  currentIndex.value = Math.max(0, currentIndex.value - 1)
}

function nextFrame() {
  currentIndex.value = Math.min(Math.max(frames.value.length - 1, 0), currentIndex.value + 1)
}

function stopTimer() {
  window.clearInterval(timer)
  timer = 0
}

function startTimer() {
  stopTimer()
  const interval = Math.max(24, 1000 / selectedCameraFps())
  timer = window.setInterval(() => {
    if (currentIndex.value >= frames.value.length - 1) {
      playing.value = false
      return
    }
    nextFrame()
  }, interval)
}

function lineData(line: { timestamps: number[]; values: Array<number | null> }) {
  const base = line.timestamps[0] ?? 0
  return line.timestamps.map((timestamp, index) => [timestamp - base, line.values[index]])
}

function renderChart() {
  if (!chartEl.value || !series.value) return
  chart?.dispose()
  chart = echarts.init(chartEl.value)
  const chartSeries = series.value.groups.flatMap((group) =>
    group.lines
      .filter((line) => line.timestamps.length)
      .map((line) => ({
        name: `${group.label}.${line.label}`,
        type: 'line',
        symbol: 'none',
        data: lineData(line),
      })),
  )
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 52, right: 24, top: 72, bottom: 48 },
    xAxis: { type: 'value', name: 'time (s)' },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }],
    series: chartSeries,
  })
  updateMarker()
}

function updateMarker() {
  if (!chart) return
  chart.setOption({
    xAxis: {
      axisPointer: {
        show: true,
        value: currentSeconds.value,
        snap: false,
        lineStyle: { color: '#17211d', width: 1 },
      },
    },
  })
}

function resizeChart() {
  chart?.resize()
}

watch(playing, (value) => {
  if (value) startTimer()
  else stopTimer()
})

watch(currentIndex, updateMarker)

watch(selectedCamera, async () => {
  playing.value = false
  currentIndex.value = 0
  try {
    await loadFrames()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
})

onMounted(async () => {
  try {
    episode.value = await api.rawEpisode(dataset.value, episodeName.value)
    selectedCamera.value = episode.value.cameras.find((camera) => camera.frame_count > 0)?.key ?? selectedCamera.value
    await loadFrames()
    series.value = await api.rawSeries(dataset.value, episodeName.value)
    await nextTick()
    renderChart()
    window.addEventListener('resize', resizeChart)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopTimer()
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Raw Player</p>
        <h1>{{ dataset }} / {{ episodeName }}</h1>
      </div>
      <RouterLink class="button" :to="`/datasets/raw/${dataset}/episodes`">Episodes</RouterLink>
    </header>

    <PageState :loading="loading" :error="error" />

    <template v-if="episode">
      <div class="metric-row">
        <MetricCard label="Format" :value="episode.format" />
        <MetricCard label="Frame" :value="frames.length ? `${currentIndex + 1} / ${frames.length}` : 'N/A'" />
        <MetricCard label="Seconds" :value="`${seconds(currentSeconds)} / ${seconds(totalSeconds)}`" />
        <MetricCard label="Stop Trigger" :value="episode.has_gripper_trigger_stop ? 'gripper double click' : 'none'" />
      </div>

      <section class="panel raw-player-panel">
        <div class="video-tabs">
          <button
            v-for="camera in episode.cameras"
            :key="camera.key"
            :class="{ active: selectedCamera === camera.key }"
            :disabled="!camera.frame_count"
            @click="selectedCamera = camera.key"
          >
            {{ camera.key }} ({{ camera.frame_count }})
          </button>
        </div>

        <div class="raw-frame-stage">
          <img v-if="currentFrame" :src="currentFrame.url" :alt="`${selectedCamera} frame ${currentIndex + 1}`" />
          <div v-else class="page-state">No RGB frames for this camera.</div>
        </div>

        <div class="raw-controls">
          <button @click="playing = !playing" :disabled="!frames.length">{{ playing ? 'Pause' : 'Play' }}</button>
          <button @click="previousFrame" :disabled="!frames.length || currentIndex === 0">Prev</button>
          <button @click="nextFrame" :disabled="!frames.length || currentIndex >= frames.length - 1">Next</button>
          <input
            v-model.number="currentIndex"
            type="range"
            min="0"
            :max="Math.max(frames.length - 1, 0)"
            :disabled="!frames.length"
          />
          <span>{{ seconds(currentSeconds) }}</span>
        </div>
      </section>

      <section class="panel chart-panel">
        <h2>State Curves</h2>
        <div v-if="series?.groups.some((group) => group.lines.some((line) => line.timestamps.length))" ref="chartEl" class="chart"></div>
        <div v-else class="page-state">No state series found for this episode.</div>
      </section>
    </template>
  </section>
</template>
