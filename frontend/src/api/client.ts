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
  ConversionJob,
  ConversionPreflight,
  ConversionRequest,
  DeletedDataset,
  Hdf5CameraList,
} from './types'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`)
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
  converterPreflight: (payload: ConversionRequest) =>
    send<ConversionPreflight>('/api/converter/preflight', 'POST', payload),
  createConversion: (payload: ConversionRequest) =>
    send<ConversionJob>('/api/converter/jobs', 'POST', payload),
  conversionJob: (jobId: string) => request<ConversionJob>(`/api/converter/jobs/${jobId}`),
  cancelConversion: (jobId: string) => send<ConversionJob>(`/api/converter/jobs/${jobId}`, 'DELETE'),
  deleteDataset: (dataset: string) => send<DeletedDataset>(`/api/catalog/datasets/${encodeURIComponent(dataset)}`, 'DELETE'),
  hdf5Frames: (dataset: string, episode: number, camera: string) =>
    request<RawFrameList>(`/api/datasets/${dataset}/episodes/${episode}/frames?camera=${encodeURIComponent(camera)}`),
  hdf5Cameras: (dataset: string, episode: number) =>
    request<Hdf5CameraList>(`/api/datasets/${dataset}/episodes/${episode}/cameras`),
}
