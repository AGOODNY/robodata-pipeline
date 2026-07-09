<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { api } from '../api/client'
import type { EpisodeSeries } from '../api/types'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const format = computed(() => route.params.format as string)
const episodeIndex = computed(() => Number(route.params.episode))
const series = ref<EpisodeSeries | null>(null)
const loading = ref(true)
const error = ref('')
const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chartEl.value || !series.value) return
  chart = echarts.init(chartEl.value)
  const names = series.value.state_names.length ? series.value.state_names : series.value.action_names
  const stateLines = names.map((name, index) => ({
    name: `state.${name}`,
    type: 'line',
    symbol: 'none',
    data: series.value!.observation_state.map((row, rowIndex) => [series.value!.timestamp[rowIndex], row[index]]),
  }))
  const actionLines = names.map((name, index) => ({
    name: `action.${name}`,
    type: 'line',
    symbol: 'none',
    lineStyle: { type: 'dashed' },
    data: series.value!.action.map((row, rowIndex) => [series.value!.timestamp[rowIndex], row[index]]),
  }))
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 52, right: 24, top: 72, bottom: 48 },
    xAxis: { type: 'value', name: 'time (s)' },
    yAxis: { type: 'value', scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 24 }],
    series: [...stateLines, ...actionLines],
  })
}

function resizeChart() {
  chart?.resize()
}

onMounted(async () => {
  try {
    series.value = await api.series(dataset.value, episodeIndex.value)
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
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">State / Action Curves</p>
        <h1>{{ dataset }} / #{{ episodeIndex }}</h1>
      </div>
      <RouterLink class="button" :to="`/datasets/${format}/${dataset}/episodes/${episodeIndex}`">Player</RouterLink>
    </header>

    <PageState :loading="loading" :error="error" />

    <section v-show="series" class="panel chart-panel">
      <div ref="chartEl" class="chart"></div>
    </section>
  </section>
</template>
