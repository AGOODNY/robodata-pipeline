<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()
const dataset = computed(() => route.params.dataset as string | undefined)

const navItems = computed(() => {
  if (!dataset.value) return []
  return [
    { label: 'Overview', to: `/datasets/${dataset.value}/overview` },
    { label: 'Episodes', to: `/datasets/${dataset.value}/episodes` },
    { label: 'Validation', to: `/datasets/${dataset.value}/validation` },
  ]
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand">
        <span class="brand-mark">R</span>
        <span>
          <strong>RoboData</strong>
          <small>Pipeline</small>
        </span>
      </RouterLink>

      <nav class="nav-section">
        <RouterLink to="/">Datasets</RouterLink>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to">
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="future-section">
        <span>Later Pipeline</span>
        <button disabled>Raw Viewer</button>
        <button disabled>Converter</button>
        <button disabled>Subtask Labels</button>
        <button disabled>Training Export</button>
      </div>
    </aside>

    <main class="main-panel">
      <RouterView />
    </main>
  </div>
</template>
