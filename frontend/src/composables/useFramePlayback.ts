import { onUnmounted, watch, type Ref } from 'vue'

interface FramePlaybackOptions {
  playing: Ref<boolean>
  playbackRate: Ref<number>
  frameIndex: Ref<number>
  frameCount: () => number
  frameDurationMs: () => number
}

export function useFramePlayback(options: FramePlaybackOptions) {
  let timer = 0

  function stop() {
    window.clearTimeout(timer)
    timer = 0
  }

  function scheduleNextFrame() {
    stop()
    const count = options.frameCount()
    if (!options.playing.value || !count) return
    timer = window.setTimeout(() => {
      timer = 0
      if (options.frameIndex.value >= count - 1) {
        options.playing.value = false
        return
      }
      options.frameIndex.value += 1
    }, Math.max(8, options.frameDurationMs() / options.playbackRate.value))
  }

  function frameRendered() {
    if (options.playing.value) scheduleNextFrame()
  }

  watch(options.playing, (playing) => {
    if (!playing) {
      stop()
      return
    }
    if (options.frameIndex.value >= options.frameCount() - 1) options.frameIndex.value = 0
    scheduleNextFrame()
  })

  watch(options.playbackRate, () => {
    if (options.playing.value) scheduleNextFrame()
  })

  onUnmounted(stop)

  return { frameRendered, stop }
}
