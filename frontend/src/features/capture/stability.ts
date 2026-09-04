import { DEFAULT_SCANNER_CONFIG, type ScannerConfig } from './scannerConfig'
import type { Corner } from './types'

export interface StabilitySample {
  corners: Corner[] | null
  areaRatio: number | null
}

export interface StabilityState {
  since: number | null
  frames: number
  previousCorners: Corner[] | null
  initialAreaRatio: number | null
  maxMovementRatio: number
  maxAreaVariationRatio: number
}

export const INITIAL_STABILITY: StabilityState = {
  since: null,
  frames: 0,
  previousCorners: null,
  initialAreaRatio: null,
  maxMovementRatio: 0,
  maxAreaVariationRatio: 0,
}

function resetWithSample(sample: StabilitySample, at: number): StabilityState {
  return {
    since: at,
    frames: 1,
    previousCorners: sample.corners,
    initialAreaRatio: sample.areaRatio,
    maxMovementRatio: 0,
    maxAreaVariationRatio: 0,
  }
}

function maxCornerMovement(previous: Corner[], current: Corner[], diagonal: number): number {
  return Math.max(...current.map((corner, index) => {
    const prior = previous[index]
    return Math.hypot(corner.x - prior.x, corner.y - prior.y) / diagonal
  }))
}

export function advanceStability(
  state: StabilityState,
  sample: StabilitySample,
  at: number,
  sourceWidth: number,
  sourceHeight: number,
  config: ScannerConfig = DEFAULT_SCANNER_CONFIG,
): { state: StabilityState; stableLongEnough: boolean } {
  const validSample = sample.corners?.length === 4
    && sample.areaRatio !== null
    && Number.isFinite(sample.areaRatio)
    && sourceWidth > 0
    && sourceHeight > 0
    && sample.corners.every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y)
      && x >= 0 && x <= sourceWidth && y >= 0 && y <= sourceHeight)
  if (!validSample) return { state: INITIAL_STABILITY, stableLongEnough: false }

  if (!state.previousCorners || state.initialAreaRatio === null) {
    const next = resetWithSample(sample, at)
    return { state: next, stableLongEnough: false }
  }

  const diagonal = Math.max(1, Math.hypot(sourceWidth, sourceHeight))
  const movement = maxCornerMovement(state.previousCorners, sample.corners!, diagonal)
  const areaVariation = Math.abs(sample.areaRatio! - state.initialAreaRatio) / Math.max(state.initialAreaRatio, Number.EPSILON)
  if (movement > config.maxCornerMovementRatio || areaVariation > config.maxAreaVariationRatio) {
    const next = resetWithSample(sample, at)
    return { state: next, stableLongEnough: false }
  }

  const next: StabilityState = {
    ...state,
    frames: state.frames + 1,
    previousCorners: sample.corners,
    maxMovementRatio: Math.max(state.maxMovementRatio, movement),
    maxAreaVariationRatio: Math.max(state.maxAreaVariationRatio, areaVariation),
  }
  const stableLongEnough = at - (next.since ?? at) >= config.stableRequiredMs
    && next.frames >= config.stableMinFrames
  return { state: next, stableLongEnough }
}
