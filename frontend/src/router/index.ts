import { createRouter, createWebHistory } from 'vue-router'

import DatasetSelectView from '../views/DatasetSelectView.vue'
import DatasetOverviewView from '../views/DatasetOverviewView.vue'
import EpisodesView from '../views/EpisodesView.vue'
import EpisodePlayerView from '../views/EpisodePlayerView.vue'
import SeriesView from '../views/SeriesView.vue'
import RawDatasetOverviewView from '../views/RawDatasetOverviewView.vue'
import RawEpisodesView from '../views/RawEpisodesView.vue'
import RawEpisodePlayerView from '../views/RawEpisodePlayerView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'datasets', component: DatasetSelectView },
    { path: '/datasets/raw/:dataset/overview', name: 'raw-overview', component: RawDatasetOverviewView },
    { path: '/datasets/raw/:dataset/episodes', name: 'raw-episodes', component: RawEpisodesView },
    { path: '/datasets/raw/:dataset/episodes/:episode', name: 'raw-player', component: RawEpisodePlayerView },
    { path: '/datasets/:format/:dataset/overview', name: 'overview', component: DatasetOverviewView },
    { path: '/datasets/:format/:dataset/episodes', name: 'episodes', component: EpisodesView },
    { path: '/datasets/:format/:dataset/episodes/:episode', name: 'player', component: EpisodePlayerView },
    { path: '/datasets/:format/:dataset/episodes/:episode/series', name: 'series', component: SeriesView },
  ],
})
