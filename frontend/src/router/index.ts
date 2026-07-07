import { createRouter, createWebHistory } from 'vue-router'

import DatasetSelectView from '../views/DatasetSelectView.vue'
import DatasetOverviewView from '../views/DatasetOverviewView.vue'
import EpisodesView from '../views/EpisodesView.vue'
import EpisodePlayerView from '../views/EpisodePlayerView.vue'
import SeriesView from '../views/SeriesView.vue'
import ValidationView from '../views/ValidationView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'datasets', component: DatasetSelectView },
    { path: '/datasets/:dataset/overview', name: 'overview', component: DatasetOverviewView },
    { path: '/datasets/:dataset/episodes', name: 'episodes', component: EpisodesView },
    { path: '/datasets/:dataset/episodes/:episode', name: 'player', component: EpisodePlayerView },
    { path: '/datasets/:dataset/episodes/:episode/series', name: 'series', component: SeriesView },
    { path: '/datasets/:dataset/validation', name: 'validation', component: ValidationView },
  ],
})
