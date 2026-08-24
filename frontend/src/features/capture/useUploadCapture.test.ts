import { describe, expect, it } from 'vitest'

import { UploadCaptureError, readUploadResult } from './useUploadCapture'

describe('upload contract (R-011)', () => {
  it('acepta una respuesta 201 con id de fichero', async () => {
    await expect(readUploadResult(new Response(JSON.stringify({ id: 'file-1' }), { status: 201 }))).resolves.toEqual({ id: 'file-1', duplicate: false })
  })

  it.each([200, 202, 203])('rechaza una respuesta %s aunque incluya un id', async (status) => {
    await expect(readUploadResult(new Response(JSON.stringify({ id: 'file-1' }), { status }))).rejects.toBeInstanceOf(UploadCaptureError)
  })

  it('conserva el camino explícito de duplicado propio en 409', async () => {
    await expect(readUploadResult(new Response(JSON.stringify({ duplicate_of: 'file-original' }), { status: 409 }))).resolves.toEqual({ id: 'file-original', duplicate: true })
  })
})
