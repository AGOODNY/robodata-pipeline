export interface DatasetListItem {
  name: string
  path: string
  codebase_version: string | null
  robot_type: string | null
  total_episodes: number | null
  total_frames: number | null
  fps: number | null
}

export interface VideoAsset {
  key: string
  relative_path: string
  url: string
  exists: boolean
  from_timestamp: number | null
  to_timestamp: number | null
}

export interface DatasetSummary extends DatasetListItem {
  total_tasks: number | null
  features: Record<string, any>
  tasks: Array<Record<string, any>>
  stats: Record<string, any>
}

export interface EpisodeListItem {
  episode_index: number
  tasks: string[]
  length: number
  dataset_from_index: number | null
  dataset_to_index: number | null
  videos: VideoAsset[]
}

export interface EpisodeDetail extends EpisodeListItem {
  stats: Record<string, any>
}

export interface EpisodeSeries {
  episode_index: number
  timestamp: number[]
  observation_state: number[][]
  action: number[][]
  state_names: string[]
  action_names: string[]
}

export interface ValidationIssue {
  level: 'error' | 'warning' | 'info'
  code: string
  message: string
  path: string | null
}
