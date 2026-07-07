import type {
  DatasetListItem,
  DatasetSummary,
  EpisodeDetail,
  EpisodeListItem,
  EpisodeSeries,
  ValidationIssue,
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
  datasets: () => request<DatasetListItem[]>('/api/datasets'),
  summary: (dataset: string) => request<DatasetSummary>(`/api/datasets/${dataset}/summary`),
  episodes: (dataset: string) => request<EpisodeListItem[]>(`/api/datasets/${dataset}/episodes`),
  episode: (dataset: string, episode: number) =>
    request<EpisodeDetail>(`/api/datasets/${dataset}/episodes/${episode}`),
  series: (dataset: string, episode: number) =>
    request<EpisodeSeries>(`/api/datasets/${dataset}/episodes/${episode}/series`),
  validation: (dataset: string) => request<ValidationIssue[]>(`/api/datasets/${dataset}/validation`),
}
