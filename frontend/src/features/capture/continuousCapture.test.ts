import { describe, expect, it } from 'vitest'

import {
  acceptContinuousUpload,
  createContinuousCaptureState,
  hasReachedContinuousLimit,
} from './continuousCapture'

describe('continuous capture session (R-012)', () => {
  it('starts empty with a maximum of ten invoices', () => {
    expect(createContinuousCaptureState('session-1')).toEqual({
      sessionId: 'session-1',
      accepted: [],
      currentSequence: 0,
      maxItems: 10,
    })
  })

  it('assigns an increasing sequence and acceptance timestamp to each distinct upload', () => {
    const state = createContinuousCaptureState('session-1')

    const first = acceptContinuousUpload(state, 'file-1', '2026-08-24T10:00:00.000Z')
    const second = acceptContinuousUpload(first.state, 'file-2', '2026-08-24T10:00:01.000Z')

    expect(first).toEqual({
      added: true,
      state: {
        sessionId: 'session-1',
        accepted: [{ fileId: 'file-1', sequence: 1, acceptedAt: '2026-08-24T10:00:00.000Z' }],
        currentSequence: 1,
        maxItems: 10,
      },
    })
    expect(second.state.accepted[1]).toEqual({ fileId: 'file-2', sequence: 2, acceptedAt: '2026-08-24T10:00:01.000Z' })
  })

  it('does not add a duplicate file id or consume a sequence', () => {
    const state = acceptContinuousUpload(createContinuousCaptureState('session-1'), 'file-1', '2026-08-24T10:00:00.000Z').state

    const result = acceptContinuousUpload(state, 'file-1', '2026-08-24T10:00:01.000Z')

    expect(result).toEqual({ added: false, state })
  })

  it('stops accepting invoices at ten', () => {
    let state = createContinuousCaptureState('session-1')
    for (let index = 1; index <= 10; index += 1) {
      state = acceptContinuousUpload(state, `file-${index}`, `2026-08-24T10:00:${String(index).padStart(2, '0')}.000Z`).state
    }

    expect(hasReachedContinuousLimit(state)).toBe(true)
    expect(acceptContinuousUpload(state, 'file-11', '2026-08-24T10:01:00.000Z')).toEqual({ added: false, state })
  })
})
