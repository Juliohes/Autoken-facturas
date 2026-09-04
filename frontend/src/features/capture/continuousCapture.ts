export interface ContinuousCaptureState {
  sessionId: string
  accepted: Array<{
    fileId: string
    sequence: number
    acceptedAt: string
  }>
  currentSequence: number
  maxItems: number
}

export const CONTINUOUS_CAPTURE_MAX_ITEMS = 10

export function createContinuousCaptureState(sessionId: string): ContinuousCaptureState {
  return {
    sessionId,
    accepted: [],
    currentSequence: 0,
    maxItems: CONTINUOUS_CAPTURE_MAX_ITEMS,
  }
}

export function hasReachedContinuousLimit(state: ContinuousCaptureState): boolean {
  return state.accepted.length >= state.maxItems
}

export function acceptContinuousUpload(
  state: ContinuousCaptureState,
  fileId: string,
  acceptedAt = new Date().toISOString(),
): { added: boolean; state: ContinuousCaptureState } {
  if (state.accepted.some((entry) => entry.fileId === fileId) || hasReachedContinuousLimit(state)) {
    return { added: false, state }
  }

  const sequence = state.currentSequence + 1
  return {
    added: true,
    state: {
      ...state,
      accepted: [...state.accepted, { fileId, sequence, acceptedAt }],
      currentSequence: sequence,
    },
  }
}
