// Tests de comportamiento de `CaptureScreen` (S2.2, C1-C3/C7-C14). Cámara, grabado de frames y
// análisis mockeados (jsdom no reproduce vídeo/canvas real, ver spec §6); `useCompanyOptions`/
// `useUploadCapture` corren de verdad contra un cliente `api` mockeado, mismo patrón que el resto
// del proyecto.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { analyzeFrame } from './analyzeFrame'
import { CaptureScreen } from './CaptureScreen'
import { grabVideoFrame } from './grabVideoFrame'
import { fileToJpegBlob } from './normalizeToJpeg'
import { processCapturedFrame } from './processCapture'
import { useCameraStream } from './useCameraStream'
import { useFrameAnalysisLoop } from './useFrameAnalysisLoop'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))
vi.mock('./useCameraStream')
vi.mock('./useFrameAnalysisLoop')
vi.mock('./grabVideoFrame')
vi.mock('./analyzeFrame')
vi.mock('./processCapture')
vi.mock('./normalizeToJpeg')

const getMock = api.GET as unknown as Mock<(...args: never[]) => Promise<unknown>>
const postMock = api.POST as unknown as Mock<(...args: never[]) => Promise<unknown>>
const useSessionMock = vi.mocked(useSession)
const useCameraStreamMock = vi.mocked(useCameraStream)
const useFrameAnalysisLoopMock = vi.mocked(useFrameAnalysisLoop)
const grabVideoFrameMock = vi.mocked(grabVideoFrame)
const analyzeFrameMock = vi.mocked(analyzeFrame)
const processCapturedFrameMock = vi.mocked(processCapturedFrame)
const fileToJpegBlobMock = vi.mocked(fileToJpegBlob)

const TENANT_ADMIN_SESSION = {
  status: 'authenticated' as const,
  user: { id: 't1', email: 'ana@ilex.es', role: 'tenant_admin' as const, tenant: 'ilex', company: null, is_admin_tech: false },
  login: vi.fn(),
  logout: vi.fn(),
}

const USER_SESSION = {
  status: 'authenticated' as const,
  user: {
    id: 'u1',
    email: 'raul@ilex.es',
    role: 'user' as const,
    tenant: 'ilex',
    company: { id: 'c1', name: 'Cliente SL' },
    is_admin_tech: false,
  },
  login: vi.fn(),
  logout: vi.fn(),
}

const FAKE_FRAME = { width: 10, height: 10, data: new Uint8ClampedArray(400) } as ImageData
const FAKE_BLOB = new Blob(['fake-jpeg'], { type: 'image/jpeg' })
const CORNERS = [
  { x: 1, y: 1 },
  { x: 9, y: 1 },
  { x: 9, y: 9 },
  { x: 1, y: 9 },
]

function renderScreen(onUploaded = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <CaptureScreen onUploaded={onUploaded} />
      </QueryClientProvider>
    </MemoryRouter>,
  )
  return { onUploaded }
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  useFrameAnalysisLoopMock.mockReset()
  grabVideoFrameMock.mockReset()
  grabVideoFrameMock.mockReturnValue(FAKE_FRAME)
  analyzeFrameMock.mockReset()
  analyzeFrameMock.mockResolvedValue({ sharpness: 200, corners: CORNERS })
  processCapturedFrameMock.mockReset()
  processCapturedFrameMock.mockResolvedValue(FAKE_BLOB)
  fileToJpegBlobMock.mockReset()
  fileToJpegBlobMock.mockResolvedValue(FAKE_BLOB)
  useSessionMock.mockReturnValue(TENANT_ADMIN_SESSION)
  useCameraStreamMock.mockReturnValue({ status: 'active', stream: null })
  getMock.mockImplementation((path: string) => {
    if (path === '/api/v1/companies') {
      return Promise.resolve({ data: [{ id: 'c1', name: 'Cliente SL' }], error: undefined })
    }
    throw new Error(`ruta GET no mockeada: ${path}`)
  })
})

describe('CaptureScreen (S2.2)', () => {
  it('C2: con cámara activa, muestra la vista previa en vivo y el botón de captura manual', () => {
    renderScreen()

    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    expect(screen.queryByText(/no se pudo acceder a la cámara/i)).not.toBeInTheDocument()
  })

  it('C3: sin cámara disponible, muestra el selector de fichero nativo', () => {
    useCameraStreamMock.mockReturnValue({ status: 'unavailable', stream: null })
    renderScreen()

    expect(screen.queryByRole('button', { name: 'Tomar foto' })).not.toBeInTheDocument()
    expect(screen.getByText(/no se pudo acceder a la cámara/i)).toBeInTheDocument()
  })

  it('C3: elegir un fichero del selector nativo normaliza a JPEG y lleva a la revisión', async () => {
    useCameraStreamMock.mockReturnValue({ status: 'unavailable', stream: null })
    renderScreen()
    const user = userEvent.setup()
    const file = new File(['contenido'], 'foto.heic', { type: 'image/heic' })

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), file)

    await waitFor(() => expect(fileToJpegBlobMock).toHaveBeenCalledWith(file))
    expect(await screen.findByRole('heading', { name: 'Revisar foto' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('C3: un fichero que no se puede decodificar muestra un aviso claro, sin quedarse en una revisión vacía', async () => {
    // `accept="image/*"` filtra en el navegador (y en `userEvent.upload`, que lo simula) los
    // ficheros que no declaran un MIME de imagen — pero eso no garantiza que el navegador SEPA
    // decodificarlo de verdad (p. ej. un HEIC corrupto, o un formato que ese navegador no soporta):
    // de ahí que `fileToJpegBlob` (no el tipo declarado) sea la fuente de verdad del rechazo.
    useCameraStreamMock.mockReturnValue({ status: 'unavailable', stream: null })
    fileToJpegBlobMock.mockRejectedValueOnce(new Error('The source image cannot be decoded'))
    renderScreen()
    const user = userEvent.setup()
    const file = new File(['contenido'], 'foto.heic', { type: 'image/heic' })

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), file)

    expect(await screen.findByRole('alert')).toHaveTextContent(/no es una imagen válida/i)
    expect(screen.queryByRole('heading', { name: 'Revisar foto' })).not.toBeInTheDocument()
  })

  it('C7: pulsar "Tomar foto" antes de que la cámara esté lista avisa, sin capturar nada', async () => {
    grabVideoFrameMock.mockReturnValue(null)
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/todavía se está preparando/i)
    expect(screen.queryByRole('heading', { name: 'Revisar foto' })).not.toBeInTheDocument()
    expect(processCapturedFrameMock).not.toHaveBeenCalled()
  })

  it('§5: user sin empresa asignada nunca llega a ver la cámara ni el fallback de fichero', () => {
    useSessionMock.mockReturnValue({
      ...USER_SESSION,
      user: { ...USER_SESSION.user, company: null },
    })
    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no se pudo cargar tu empresa/i)
    expect(screen.queryByRole('button', { name: 'Tomar foto' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/elige o toma una foto/i)).not.toBeInTheDocument()
  })

  it('regresión (auditoría): la auto-captura del bucle en vivo llega hasta la revisión con su frame', async () => {
    renderScreen()

    const lastCall = useFrameAnalysisLoopMock.mock.calls.at(-1)
    const onAnalysis = lastCall?.[2]
    expect(onAnalysis).toBeInstanceOf(Function)
    act(() => onAnalysis?.({ sharpness: 200, corners: CORNERS }, FAKE_FRAME))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Revisar foto' })).toBeInTheDocument())
    expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, CORNERS)
    expect(await screen.findByAltText('Foto capturada')).toBeInTheDocument()
  })

  it('C8: tras capturar con esquinas detectadas, muestra la revisión sin aviso de borrosidad', async () => {
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Revisar foto' })).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(await screen.findByAltText('Foto capturada')).toBeInTheDocument()
    expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, CORNERS)
  })

  it('C9: sin esquinas detectadas, procesa el frame completo igualmente (sin bloquear)', async () => {
    analyzeFrameMock.mockResolvedValue({ sharpness: 200, corners: null })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    await waitFor(() => expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, null))
    expect(await screen.findByAltText('Foto capturada')).toBeInTheDocument()
  })

  it('C7: una captura manual forzada con nitidez baja avisa, sin bloquear el avance', async () => {
    analyzeFrameMock.mockResolvedValue({ sharpness: 5, corners: null })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/puede salir borrosa/i)
    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    expect(screen.getByRole('button', { name: 'Usar esta foto' })).not.toBeDisabled()
  })

  it('C10: "Repetir" vuelve a la vista de cámara sin haber llamado a la subida', async () => {
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })
    await user.click(screen.getByRole('button', { name: 'Repetir' }))

    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    expect(postMock).not.toHaveBeenCalled()
  })

  it('C12: tenant_admin debe elegir una empresa antes de poder subir', async () => {
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })

    const uploadButton = screen.getByRole('button', { name: 'Usar esta foto' })
    expect(uploadButton).toBeDisabled()

    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    expect(uploadButton).not.toBeDisabled()
  })

  it('C11: user sube directo a su empresa fija, sin selector', async () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })

    expect(screen.queryByLabelText('Empresa')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Usar esta foto' })).not.toBeDisabled()
  })

  it('C13: subida con éxito llama a onUploaded con el id y la dirección elegida', async () => {
    postMock.mockResolvedValueOnce({
      data: {
        id: 'file-abc',
        company_id: 'c1',
        content_type: 'image/jpeg',
        size_bytes: 10,
        sha256: 'x',
        status: 'pending_ocr',
        scan_status: 'clean',
        created_at: '2026-07-24T00:00:00Z',
      },
      error: undefined,
      response: { status: 201 },
    })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Emitida' }))
    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })
    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    await user.click(screen.getByRole('button', { name: 'Usar esta foto' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'emitida'))
  })

  it('C14: un 409 muestra "ya se había subido" y no ofrece reintentar', async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'duplicate_of' },
      response: { status: 409 },
    })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })
    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    await user.click(screen.getByRole('button', { name: 'Usar esta foto' }))

    expect(await screen.findByText(/ya se había subido/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    // La foto capturada sigue mostrándose: no hace falta repetir la captura.
    expect(screen.getByAltText('Foto capturada')).toBeInTheDocument()
  })

  it('C14: un 503 ofrece reintentar sin perder la foto', async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'unavailable' },
      response: { status: 503 },
    })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    await screen.findByRole('heading', { name: 'Revisar foto' })
    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    await user.click(screen.getByRole('button', { name: 'Usar esta foto' }))

    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
})
