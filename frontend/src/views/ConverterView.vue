<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import type { CatalogDataset, ConversionJob, ConversionPreflight, ConversionRequest, DatasetFormat } from '../api/types'
import MetricCard from '../components/MetricCard.vue'
import PageState from '../components/PageState.vue'

const router = useRouter()
const datasets = ref<CatalogDataset[]>([])
const sourceKey = ref('')
const targetFormat = ref<Exclude<DatasetFormat, 'raw'> | ''>('')
const actionType = ref<'joint' | 'tcp' | 'all' | ''>('')
const tcpActionSource = ref<'endpose' | 'target'>('endpose')
const instruction = ref('')
const preflight = ref<ConversionPreflight | null>(null)
const job = ref<ConversionJob | null>(null)
const loading = ref(true)
const checking = ref(false)
const starting = ref(false)
const error = ref('')
let pollTimer = 0

const source = computed(() => datasets.value.find((item) => `${item.format}:${item.name}` === sourceKey.value) ?? null)
const payload = computed<ConversionRequest | null>(() => {
  if (!source.value || !targetFormat.value || (source.value.format === 'raw' && !actionType.value)) return null
  return {
  source_name: source.value.name,
  source_format: source.value.format,
  target_format: targetFormat.value,
  options: { action_type: actionType.value || 'joint', tcp_action_source: tcpActionSource.value, fps: 30, trim_trigger_tail: true, trim_tail_seconds: 0.5, instruction: instruction.value },
  }
})
const canStart = computed(() => Boolean(preflight.value?.valid_episodes) && !checking.value && !job.value && (targetFormat.value === 'hdf5' || preflight.value?.encoder_available))
const jobIsActive = computed(() => job.value?.status === 'queued' || job.value?.status === 'running')
const jobProgress = computed(() => {
  if (!job.value?.total_frames) return 0
  return Math.min(100, Math.round((job.value.completed_frames / job.value.total_frames) * 100))
})
const jobStatusText = computed(() => {
  if (!job.value) return ''
  if (job.value.status === 'queued') return 'Queued — waiting for the converter worker to start'
  if (job.value.status === 'running') return 'Converting — keep this page open or return later'
  if (job.value.status === 'completed') return 'Conversion completed successfully'
  if (job.value.status === 'cancelled') return 'Conversion cancelled'
  return 'Conversion failed'
})

async function refreshPreflight() {
  if (!payload.value || job.value) {
    preflight.value = null
    checking.value = false
    return
  }
  checking.value = true; error.value = ''
  try { preflight.value = await api.converterPreflight(payload.value) }
  catch (err) { error.value = err instanceof Error ? err.message : String(err); preflight.value = null }
  finally { checking.value = false }
}

async function startConversion() {
  if (!payload.value) return
  starting.value = true; error.value = ''
  try { job.value = await api.createConversion(payload.value); pollJob() }
  catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { starting.value = false }
}

async function pollJob() {
  if (!job.value) return
  try {
    job.value = await api.conversionJob(job.value.id)
    if (job.value.status === 'queued' || job.value.status === 'running') pollTimer = window.setTimeout(pollJob, 700)
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
}

async function cancelConversion() { if (job.value) job.value = await api.cancelConversion(job.value.id) }
function openOutput() { if (job.value?.output_name) router.push(`/datasets/${job.value.target_format}/${job.value.output_name}/overview`) }

watch([sourceKey, targetFormat, actionType, tcpActionSource], refreshPreflight)
onMounted(async () => {
  try {
    datasets.value = await api.catalog()
  } catch (err) { error.value = err instanceof Error ? err.message : String(err) }
  finally { loading.value = false }
})
onUnmounted(() => window.clearTimeout(pollTimer))
</script>

<template>
  <section class="page">
    <header class="page-header"><div><p class="eyebrow">Background conversion</p><h1>Converter</h1></div></header>
    <PageState :loading="loading" :error="error" />
    <template v-if="!loading && datasets.length">
      <section class="panel converter-form">
        <label>Source dataset<select v-model="sourceKey" :disabled="!!job"><option disabled value="">Select a source dataset</option><option v-for="item in datasets" :key="`${item.format}:${item.name}`" :value="`${item.format}:${item.name}`">{{ item.format_label }} · {{ item.name }}</option></select></label>
        <label>Target format<select v-model="targetFormat" :disabled="!!job"><option disabled value="">Select a target format</option><option value="lerobot_v21">LeRobot 2.1</option><option value="lerobot_v30">LeRobot 3.0</option><option value="hdf5">RoboData HDF5</option></select></label>
        <template v-if="source?.format === 'raw'"><label>Action mode<select v-model="actionType" :disabled="!!job"><option disabled value="">Select an action mode</option><option value="joint">Joint</option><option value="tcp">TCP</option><option value="all">All (joint + TCP)</option></select></label><label v-if="actionType === 'tcp'">TCP action<select v-model="tcpActionSource" :disabled="!!job"><option value="endpose">Next actual TCP</option><option value="target">Target TCP</option></select></label></template>
        <label class="wide">Task override (optional)<input v-model="instruction" :disabled="!!job" placeholder="Use instructions.json or infer from task folder" /></label>
      </section>

      <section v-if="checking && !preflight" class="panel preflight-loading"><span class="spinner" aria-hidden="true"></span><div><h2>Preparing preflight…</h2><p>Checking episode frames, timestamps, and smart-tail cleaning. Large Raw datasets can take a few seconds.</p></div></section>
      <section v-if="preflight" class="panel">
        <h2>Preflight</h2>
        <div class="metric-row"><MetricCard label="Valid episodes" :value="`${preflight.valid_episodes} / ${preflight.total_episodes}`" /><MetricCard label="Output frames" :value="preflight.total_output_frames" /><MetricCard label="Trigger trims" :value="preflight.trim_trigger_episodes" /><MetricCard label="Video encoder" :value="preflight.encoder_available ? 'Ready' : 'Missing'" /></div>
        <p v-if="targetFormat !== 'hdf5' && !preflight.encoder_available" class="notice error-notice">LeRobot export is disabled because the backend cannot find PyAV, which creates MP4 camera videos. In <code>robodata-pipeline/backend</code>, run <code>.\.venv\Scripts\python.exe -m pip install -r requirements.txt</code>, then restart the backend with that same <code>.venv</code> Python environment and refresh this page.</p>
        <p v-if="source?.format === 'raw'" class="notice">Smart cleaning is on: only gripper-double-click stop episodes lose their final 0.5 seconds. Raw files are never changed.</p>
        <table><thead><tr><th>Episode</th><th>Frames</th><th>Trimmed</th><th>Status</th></tr></thead><tbody><tr v-for="episode in preflight.episodes" :key="episode.name"><td>{{ episode.name }}</td><td>{{ episode.source_frames }} → {{ episode.output_frames }}</td><td>{{ episode.trimmed_frames }}</td><td>{{ episode.valid ? 'Ready' : episode.warnings.join('; ') }}</td></tr></tbody></table>
        <div v-if="!job" class="converter-actions"><button :disabled="!canStart || starting" :title="!canStart && targetFormat !== 'hdf5' && !preflight.encoder_available ? 'Install PyAV in the backend environment to enable LeRobot export.' : ''" @click="startConversion"><span v-if="checking || starting" class="spinner" aria-hidden="true"></span>{{ checking ? 'Checking…' : starting ? 'Starting conversion…' : 'Convert' }}</button></div>
      </section>

      <section v-if="job" class="panel conversion-job" :class="`is-${job.status}`"><div class="job-heading"><div><h2>Conversion job</h2><p><span v-if="jobIsActive" class="spinner" aria-hidden="true"></span>{{ jobStatusText }}</p></div><strong>{{ jobProgress }}%</strong></div><div class="conversion-progress" role="progressbar" :aria-valuenow="jobProgress" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${jobProgress}%` }"></span></div><div class="metric-row"><MetricCard label="Status" :value="job.status" /><MetricCard label="Stage" :value="job.stage" /><MetricCard label="Episodes" :value="`${job.completed_episodes} / ${job.total_episodes}`" /><MetricCard label="Frames" :value="`${job.completed_frames} / ${job.total_frames}`" /></div><p v-if="job.message" class="notice error-notice">{{ job.message }}</p><p v-else-if="job.status === 'failed'" class="notice error-notice">The converter stopped before publishing an output dataset. Check the backend terminal for details.</p><p v-if="job.warnings.length" class="notice warning-notice">Completed with source warnings: {{ job.warnings.join(' · ') }}</p><div class="converter-actions"><button v-if="jobIsActive" @click="cancelConversion">Cancel</button><button v-if="job.status === 'completed'" @click="openOutput">View dataset</button></div></section>
    </template>
  </section>
</template>
