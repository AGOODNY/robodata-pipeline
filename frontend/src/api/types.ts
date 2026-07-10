export interface DatasetListItem {
  name: string
  path: string
  codebase_version: string | null
  robot_type: string | null
  total_episodes: number | null
  total_frames: number | null
  fps: number | null
}

export type DatasetFormat = 'lerobot_v21' | 'lerobot_v30' | 'hdf5' | 'raw'

export interface CatalogDataset {
  name: string
  path: string
  format: DatasetFormat
  format_label: string
  robot_type: string | null
  total_episodes: number | null
  total_frames: number | null
  fps: number | null
}

export interface DeletedDataset {
  name: string
  deleted: boolean
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

export interface RawDatasetListItem {
  name: string
  path: string
  total_episodes: number
  format: string
}

export interface RawCameraStream {
  key: string
  relative_path: string
  frame_count: number
  fps: number | null
  from_timestamp: number | null
  to_timestamp: number | null
}

export interface RawEpisodeListItem {
  name: string
  path: string
  frame_count: number
  duration_seconds: number | null
  has_gripper_trigger_stop: boolean
  cameras: RawCameraStream[]
}

export interface RawEpisodeDetail extends RawEpisodeListItem {
  format: string
  statistic: Record<string, any>
  trigger_stop: Record<string, any> | null
}

export interface RawDatasetSummary {
  name: string
  path: string
  format: string
  total_episodes: number
  total_frames: number
  total_seconds: number | null
  trigger_stop_episodes: number
  cameras: RawCameraStream[]
}

export interface RawFrame {
  index: number
  timestamp: number
  relative_path: string
  url: string
}

export interface RawFrameList {
  camera: string
  frames: RawFrame[]
}

export interface RawSeriesLine {
  key: string
  label: string
  timestamps: number[]
  values: Array<number | null>
}

export interface RawSeriesGroup {
  key: string
  label: string
  lines: RawSeriesLine[]
}

export interface RawEpisodeSeries {
  episode_name: string
  groups: RawSeriesGroup[]
}

export interface ConverterOptions {
  action_type: 'joint' | 'tcp' | 'all'
  tcp_action_source: 'endpose' | 'target'
  fps: number
  trim_trigger_tail: boolean
  trim_tail_seconds: number
  instruction: string
}

export interface ConversionRequest {
  source_name: string
  source_format: DatasetFormat
  target_format: Exclude<DatasetFormat, 'raw'>
  options: ConverterOptions
}

export interface ConversionPreflightEpisode {
  name: string
  source_frames: number
  output_frames: number
  trimmed_frames: number
  warnings: string[]
  valid: boolean
}

export interface ConversionPreflight {
  source_name: string
  source_format: DatasetFormat
  target_format: Exclude<DatasetFormat, 'raw'>
  total_episodes: number
  valid_episodes: number
  total_output_frames: number
  trim_trigger_episodes: number
  encoder_available: boolean
  episodes: ConversionPreflightEpisode[]
}

export interface ConversionJob {
  id: string
  source_name: string
  source_format: DatasetFormat
  target_format: Exclude<DatasetFormat, 'raw'>
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  stage: string
  completed_episodes: number
  total_episodes: number
  completed_frames: number
  total_frames: number
  message: string
  warnings: string[]
  output_name: string | null
  output_path: string | null
}
