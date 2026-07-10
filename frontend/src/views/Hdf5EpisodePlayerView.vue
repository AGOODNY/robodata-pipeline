<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeDetail, EpisodeSeries, RawFrame } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const episodeIndex = computed(() => Number(route.params.episode))
const episode = ref<EpisodeDetail | null>(null)
const series = ref<EpisodeSeries | null>(null)
const frames = ref<RawFrame[]>([])
const camera = ref('pikaGripperDepthCamera')
const frameIndex = ref(0)
const error = ref(''); const loading = ref(true)
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const current = computed(() => frames.value[frameIndex.value] ?? null)
const seconds = computed(() => current.value && frames.value[0] ? current.value.timestamp - frames.value[0].timestamp : 0)

async function loadFrames() {
  try { frames.value = (await api.hdf5Frames(dataset.value, episodeIndex.value, camera.value)).frames; frameIndex.value = 0 }
  catch { if (camera.value !== 'orbbecCamera') { camera.value = 'orbbecCamera'; return } throw new Error('No RGB frames stored in this HDF5 episode') }
}
function renderChart() {
  if (!chartEl.value || !series.value) return
  chart?.dispose(); chart = echarts.init(chartEl.value)
  const names = series.value.state_names
  chart.setOption({ animation: false, tooltip: { trigger: 'axis' }, legend: { type: 'scroll', top: 0 }, grid: { left: 52, right: 24, top: 72, bottom: 48 }, xAxis: { type: 'value', name: 'time (s)' }, yAxis: { type: 'value', scale: true }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }], series: names.map((name, index) => ({ name: `state.${name}`, type: 'line', symbol: 'none', data: series.value!.timestamp.map((stamp, row) => [stamp, series.value!.observation_state[row][index]]) })) })
}
watch(camera, loadFrames)
onMounted(async () => { try { episode.value = await api.episode(dataset.value, episodeIndex.value); series.value = await api.series(dataset.value, episodeIndex.value); await loadFrames(); await nextTick(); renderChart() } catch (err) { error.value = err instanceof Error ? err.message : String(err) } finally { loading.value = false } })
onUnmounted(() => chart?.dispose())
</script>

<template>
  <section class="page"><header class="page-header"><div><p class="eyebrow">RoboData HDF5 Player</p><h1>{{ dataset }} / #{{ episodeIndex }}</h1></div><RouterLink class="button" :to="`/datasets/hdf5/${dataset}/episodes`">Episodes</RouterLink></header><PageState :loading="loading" :error="error" />
    <template v-if="episode"><div class="metric-row"><MetricCard label="Format" value="RoboData HDF5" /><MetricCard label="Frame" :value="`${frameIndex + 1} / ${frames.length}`" /><MetricCard label="Seconds" :value="`${seconds.toFixed(2)}s`" /><MetricCard label="Task" :value="episode.tasks.join(', ')" /></div>
      <section class="panel raw-player-panel"><div class="video-tabs"><button :class="{ active: camera === 'pikaGripperDepthCamera' }" @click="camera = 'pikaGripperDepthCamera'">Gripper camera</button><button :class="{ active: camera === 'orbbecCamera' }" @click="camera = 'orbbecCamera'">Orbbec camera</button></div><div class="raw-frame-stage"><img v-if="current" :src="current.url" alt="HDF5 frame" /><div v-else class="page-state">No RGB frame available.</div></div><div class="raw-controls"><button class="frame-control" :disabled="frameIndex === 0" @click="frameIndex--">Prev</button><button class="frame-control" :disabled="frameIndex >= frames.length - 1" @click="frameIndex++">Next</button><input v-model.number="frameIndex" type="range" min="0" :max="Math.max(frames.length - 1, 0)" /><span>{{ seconds.toFixed(2) }}s</span></div></section>
      <section class="panel chart-panel"><h2>State curves</h2><div v-if="series?.timestamp.length" ref="chartEl" class="chart"></div><div v-else class="page-state">No state series found.</div></section>
    </template></section>
</template>
