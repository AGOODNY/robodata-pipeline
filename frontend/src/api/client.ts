import type {
  CatalogDataset,
  DatasetListItem,
  DatasetSummary,
  EpisodeDetail,
  EpisodeListItem,
  EpisodeSeries,
  RawDatasetListItem,
  RawDatasetSummary,
  RawEpisodeDetail,
  RawEpisodeListItem,
  RawEpisodeSeries,
  RawFrameList,
} from './types'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  catalog: () => request<CatalogDataset[]>('/api/catalog/datasets'),
  datasets: () => request<DatasetListItem[]>('/api/datasets'),
  summary: (dataset: string) => request<DatasetSummary>(`/api/datasets/${dataset}/summary`),
  episodes: (dataset: string) => request<EpisodeListItem[]>(`/api/datasets/${dataset}/episodes`),
  episode: (dataset: string, episode: number) =>
    request<EpisodeDetail>(`/api/datasets/${dataset}/episodes/${episode}`),
  series: (dataset: string, episode: number) =>
    request<EpisodeSeries>(`/api/datasets/${dataset}/episodes/${episode}/series`),
  rawDatasets: () => request<RawDatasetListItem[]>('/api/raw/datasets'),
  rawSummary: (dataset: string) => request<RawDatasetSummary>(`/api/raw/datasets/${dataset}/summary`),
  rawEpisodes: (dataset: string) =>
    request<RawEpisodeListItem[]>(`/api/raw/datasets/${dataset}/episodes`),
  rawEpisode: (dataset: string, episode: string) =>
    request<RawEpisodeDetail>(`/api/raw/datasets/${dataset}/episodes/${episode}`),
  rawFrames: (dataset: string, episode: string, camera: string) =>
    request<RawFrameList>(
      `/api/raw/datasets/${dataset}/episodes/${episode}/frames?camera=${encodeURIComponent(camera)}`,
    ),
  rawSeries: (dataset: string, episode: string) =>
    request<RawEpisodeSeries>(`/api/raw/datasets/${dataset}/episodes/${episode}/series`),
}
