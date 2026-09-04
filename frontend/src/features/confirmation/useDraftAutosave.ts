import { useEffect, useRef, useState } from 'react'

import { formStateToDraftBody, type ConfirmFormState } from './formState'
import { useReviewDraft, type ReviewDraftResult } from './useReviewDraft'
import type { Direction } from '../capture/types'

export type DraftSaveState =
  | 'clean'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'save_error'
  | 'confirming'

interface Options {
  fileId: string
  form: ConfirmFormState
  direction: Direction | null
  revision: number
  onSaved: (result: ReviewDraftResult) => void
  enabled?: boolean
}

/** Guarda el snapshot editable tras 750 ms de inactividad y permite un guardado final explícito. */
export function useDraftAutosave({ fileId, form, direction, revision, onSaved, enabled = true }: Options) {
  const draft = useReviewDraft(fileId)
  const [state, setState] = useState<DraftSaveState>('clean')
  const firstRender = useRef(true)
  const timer = useRef<number | undefined>(undefined)
  const latest = useRef({ form, direction, revision })
  latest.current = { form, direction, revision }

  const saveNow = async (): Promise<boolean> => {
    if (!enabled) return true
    if (latest.current.direction === null) return false
    if (timer.current !== undefined) window.clearTimeout(timer.current)
    setState('saving')
    try {
      const result = await draft.mutateAsync(
        formStateToDraftBody(latest.current.form, {
          direction: latest.current.direction,
          revision: latest.current.revision,
        }),
      )
      onSaved(result)
      setState('saved')
      return true
    } catch {
      setState('save_error')
      return false
    }
  }
  const saveNowRef = useRef(saveNow)
  saveNowRef.current = saveNow

  useEffect(() => {
    if (!enabled) {
      if (timer.current !== undefined) window.clearTimeout(timer.current)
      return
    }
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    if (direction === null) return
    setState('dirty')
    if (timer.current !== undefined) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      void saveNowRef.current()
    }, 750)
    return () => {
      if (timer.current !== undefined) window.clearTimeout(timer.current)
    }
  }, [direction, form, enabled])

  useEffect(() => () => {
    if (timer.current !== undefined) window.clearTimeout(timer.current)
  }, [])

  return {
    state,
    saveNow,
    markConfirming: () => setState('confirming'),
    markConfirmError: () => setState('saved'),
  }
}
