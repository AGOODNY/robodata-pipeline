<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { ValidationIssue } from '../api/types'
import PageState from '../components/PageState.vue'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string)
const issues = ref<ValidationIssue[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    issues.value = await api.validation(dataset.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

const grouped = computed(() => ({
  error: issues.value.filter((issue) => issue.level === 'error'),
  warning: issues.value.filter((issue) => issue.level === 'warning'),
  info: issues.value.filter((issue) => issue.level === 'info'),
}))
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Format Checker</p>
        <h1>{{ dataset }}</h1>
      </div>
    </header>

    <PageState :loading="loading" :error="error" />

    <div v-if="issues.length" class="content-grid three-columns">
      <section v-for="level in (['error', 'warning', 'info'] as const)" :key="level" class="panel">
        <h2>{{ level.toUpperCase() }} · {{ grouped[level].length }}</h2>
        <article v-for="issue in grouped[level]" :key="`${issue.code}-${issue.path}-${issue.message}`" class="issue" :class="level">
          <strong>{{ issue.code }}</strong>
          <p>{{ issue.message }}</p>
          <small v-if="issue.path">{{ issue.path }}</small>
        </article>
      </section>
    </div>
  </section>
</template>
