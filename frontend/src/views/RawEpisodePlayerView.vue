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
  playing.value = false
  currentIndex.value = Math.max(0, currentIndex.value - 1)
}

function advanceFrame() {
  currentIndex.value = Math.min(Math.max(frames.value.length - 1, 0), currentIndex.value + 1)
}

function nextFrame() {
  playing.value = false
  advanceFrame()
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
    advanceFrame()
  }, interval)
}

function lineData(line: { timestamps: number[]; values: Array<number | null> }) {
  const base = line.timestamps[0] ?? 0
  return line.timestamps.map((timestamp, index) => [timestamp - base, line.values[index]])
}

function progressMarkLine() {
  return {
    symbol: 'none',
    silent: true,
    lineStyle: { color: '#7e8781', type: 'dashed', width: 1.5 },
    label: { show: false },
    data: [{ xAxis: currentSeconds.value }],
  }
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
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 52, right: 24, top: 72, bottom: 48 },
    xAxis: { type: 'value', name: 'time (s)' },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }],
    series: chartSeries.map((item, index) => (index === 0 ? { ...item, markLine: progressMarkLine() } : item)),
  })
  updateMarker()
}

function updateMarker() {
  if (!chart) return
  chart.setOption({
    animation: false,
    series: [{ markLine: progressMarkLine() }],
  })
  if (!playing.value) window.requestAnimationFrame(showCurrentFrameTooltip)
}

function showCurrentFrameTooltip() {
  if (!chart || !chartEl.value || playing.value || !currentFrame.value) return
  const x = chart.convertToPixel({ xAxisIndex: 0 }, currentSeconds.value)
  if (typeof x !== 'number') return
  chart.dispatchAction({
    type: 'showTip',
    x,
    y: Math.max(80, chartEl.value.clientHeight / 2),
  })
}

function hideCurrentFrameTooltip() {
  chart?.dispatchAction({ type: 'hideTip' })
}

function resizeChart() {
  chart?.resize()
}

watch(playing, (value) => {
  if (value) {
    hideCurrentFrameTooltip()
    startTimer()
  } else {
    stopTimer()
    updateMarker()
  }
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
          <div v-else class="page-state">No readable RGB frames. The stored JPG files for this camera are empty.</div>
        </div>

        <div class="raw-controls">
          <button
            class="play-control"
            :aria-label="playing ? 'Pause playback' : 'Play frames'"
            :title="playing ? 'Pause playback' : 'Play frames'"
            @click="playing = !playing"
            :disabled="!frames.length"
          >
            <span v-if="playing" aria-hidden="true">&#10074;&#10074;</span>
            <span v-else aria-hidden="true">&#9654;</span>
            {{ playing ? 'Pause' : 'Play' }}
          </button>
          <button
            class="frame-control"
            aria-label="Previous frame"
            title="Previous frame"
            @click="previousFrame"
            :disabled="!frames.length || currentIndex === 0"
          >
            <span aria-hidden="true">&#9664;</span>
            Prev
          </button>
          <button
            class="frame-control"
            aria-label="Next frame"
            title="Next frame"
            @click="nextFrame"
            :disabled="!frames.length || currentIndex >= frames.length - 1"
          >
            Next
            <span aria-hidden="true">&#9654;</span>
          </button>
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
