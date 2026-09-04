import { beforeEach, describe, expect, it, vi } from 'vitest'

import { postMultipart } from '../../api/client'
import { UploadCaptureError, readUploadResult, uploadCapture, uploadMultipageCapture } from './useUploadCapture'

vi.mock('../../api/client', () => ({ postMultipart: vi.fn() }))

const postMultipartMock = vi.mocked(postMultipart)

describe('upload contract (R-011)', () => {
  beforeEach(() => {
    postMultipartMock.mockReset()
    postMultipartMock.mockResolvedValue(new Response(JSON.stringify({ id: 'file-1' }), { status: 201 }))
  })

  it('acepta una respuesta 201 con id de fichero', async () => {
    await expect(readUploadResult(new Response(JSON.stringify({ id: 'file-1' }), { status: 201 }))).resolves.toEqual({ id: 'file-1', duplicate: false })
  })

  it.each([200, 202, 203])('rechaza una respuesta %s aunque incluya un id', async (status) => {
    await expect(readUploadResult(new Response(JSON.stringify({ id: 'file-1' }), { status }))).rejects.toBeInstanceOf(UploadCaptureError)
  })

  it('conserva el camino explícito de duplicado propio en 409', async () => {
    await expect(readUploadResult(new Response(JSON.stringify({ duplicate_of: 'file-original' }), { status: 409 }))).resolves.toEqual({ id: 'file-original', duplicate: true })
  })

  it('separa la subida simple del hook y construye el multipart del contrato', async () => {
    const result = await uploadCapture({
      blob: new Blob(['jpeg'], { type: 'image/jpeg' }),
      companyId: 'company-1',
      direction: 'recibida',
      captureSessionId: 'session-1',
      captureSequence: 2,
      sharpnessScore: 123.5,
    })

    expect(result).toEqual({ id: 'file-1', duplicate: false })
    expect(postMultipartMock).toHaveBeenCalledWith('/api/v1/uploads', expect.any(FormData))
    const formData = postMultipartMock.mock.calls[0][1] as FormData
    expect(formData.get('company_id')).toBe('company-1')
    expect(formData.get('capture_session_id')).toBe('session-1')
    expect(formData.get('capture_sequence')).toBe('2')
    expect(formData.get('sharpness_score')).toBe('123.5')
  })

  it('separa la subida multipágina y conserva el orden de las páginas', async () => {
    const result = await uploadMultipageCapture({
      blobs: [new Blob(['one'], { type: 'image/jpeg' }), new Blob(['two'], { type: 'image/jpeg' })],
      companyId: 'company-1',
      direction: 'emitida',
    })

    expect(result).toEqual({ id: 'file-1', duplicate: false })
    expect(postMultipartMock).toHaveBeenCalledWith('/api/v1/uploads/batch', expect.any(FormData))
    const formData = postMultipartMock.mock.calls[0][1] as FormData
    expect(formData.getAll('files')).toHaveLength(2)
    expect((formData.getAll('files')[0] as File).name).toBe('pagina-1.jpg')
    expect((formData.getAll('files')[1] as File).name).toBe('pagina-2.jpg')
  })
})
