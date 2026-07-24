import { describe, expect, it } from 'vitest'

import { UploadCaptureError } from './useUploadCapture'
import { describeUploadState, resolveEffectiveCompanyId } from './captureSelectors'

describe('resolveEffectiveCompanyId (S2.2 C11/C12)', () => {
  it('user: siempre su propia empresa, ignorando cualquier selección', () => {
    expect(resolveEffectiveCompanyId('user', 'c1', 'c2')).toBe('c1')
  })

  it('user sin empresa fijada (dato inconsistente): cadena vacía, nunca undefined', () => {
    expect(resolveEffectiveCompanyId('user', undefined, 'c2')).toBe('')
  })

  it('tenant_admin: la empresa elegida en el selector', () => {
    expect(resolveEffectiveCompanyId('tenant_admin', undefined, 'c2')).toBe('c2')
  })
})

describe('describeUploadState (S2.2 C14)', () => {
  it('sin error: sin mensaje, reintentable por defecto', () => {
    expect(describeUploadState(null, false)).toEqual({ message: null, retryable: true })
  })

  it('UploadCaptureError: usa su mensaje y reintentabilidad tal cual', () => {
    const error = new UploadCaptureError({ message: 'ya se había subido', retryable: false })
    expect(describeUploadState(error, true)).toEqual({ message: 'ya se había subido', retryable: false })
  })

  it('error genérico (no UploadCaptureError): mensaje por defecto, reintentable', () => {
    expect(describeUploadState(new Error('boom'), true)).toEqual({
      message: 'No se pudo subir la foto.',
      retryable: true,
    })
  })
})
