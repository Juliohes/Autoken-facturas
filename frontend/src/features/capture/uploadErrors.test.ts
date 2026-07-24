import { describe, expect, it } from 'vitest'

import { describeUploadError } from './uploadErrors'

describe('describeUploadError (S2.2 C14)', () => {
  it('409: duplicado, no reintentable', () => {
    expect(describeUploadError(409).retryable).toBe(false)
  })

  it('413: demasiado grande, no reintentable', () => {
    expect(describeUploadError(413).retryable).toBe(false)
  })

  it('415: tipo no admitido, no reintentable', () => {
    expect(describeUploadError(415).retryable).toBe(false)
  })

  it('503: servicio caído, reintentable', () => {
    expect(describeUploadError(503).retryable).toBe(true)
  })

  it('otro código: mensaje del backend si viene, reintentable por defecto', () => {
    const info = describeUploadError(500, 'boom')
    expect(info.message).toBe('boom')
    expect(info.retryable).toBe(true)
  })
})
