// Comportamientos observables de la captura directa S6.11. Canvas y cámara se
// simulan porque jsdom no proporciona píxeles ni un MediaStream real.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

vi.mock('../../api/client', () => ({ api: { GET: vi.fn(), POST: vi.fn() } }))
vi.mock('../session/SessionProvider', () => ({ useSession: vi.fn() }))
vi.mock('./useCameraStream')
vi.mock('./grabVideoFrame')
vi.mock('./analyzeFrame')
vi.mock('./processCapture')
vi.mock('./normalizeToJpeg')

const getMock = api.GET as unknown as Mock<(...args: never[]) => Promise<unknown>>
const postMock = api.POST as unknown as Mock<(...args: never[]) => Promise<unknown>>
const useSessionMock = vi.mocked(useSession)
const useCameraStreamMock = vi.mocked(useCameraStream)
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
  user: { id: 'u1', email: 'raul@ilex.es', role: 'user' as const, tenant: 'ilex', company: { id: 'c1', name: 'Cliente SL' }, is_admin_tech: false },
  login: vi.fn(),
  logout: vi.fn(),
}
const FAKE_FRAME = { width: 10, height: 10, data: new Uint8ClampedArray(400) } as ImageData
const FAKE_BLOB = new Blob(['fake-jpeg'], { type: 'image/jpeg' })
const CORNERS = [{ x: 1, y: 1 }, { x: 9, y: 1 }, { x: 9, y: 9 }, { x: 1, y: 9 }]

function renderScreen(onUploaded = vi.fn(), cameraReady = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<MemoryRouter><QueryClientProvider client={client}><CaptureScreen onUploaded={onUploaded} /></QueryClientProvider></MemoryRouter>)
  if (cameraReady) {
    const video = document.querySelector('video')
    if (video) {
      Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
      fireEvent.loadedData(video)
    }
  }
  return { onUploaded, unmount: view.unmount }
}

function successfulUpload() {
  postMock.mockResolvedValueOnce({
    data: { id: 'file-abc', company_id: 'c1', content_type: 'image/jpeg', size_bytes: 10, sha256: 'x', status: 'pending_ocr', scan_status: 'clean', created_at: '2026-08-13T00:00:00Z' },
    error: undefined,
    response: { status: 201 },
  })
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  grabVideoFrameMock.mockReset()
  grabVideoFrameMock.mockReturnValue(FAKE_FRAME)
  analyzeFrameMock.mockReset()
  analyzeFrameMock.mockResolvedValue({ sharpness: 200, corners: CORNERS })
  processCapturedFrameMock.mockReset()
  processCapturedFrameMock.mockResolvedValue(FAKE_BLOB)
  fileToJpegBlobMock.mockReset()
  fileToJpegBlobMock.mockResolvedValue(FAKE_BLOB)
  useSessionMock.mockReturnValue(TENANT_ADMIN_SESSION)
  useCameraStreamMock.mockReturnValue({ status: 'idle', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
  getMock.mockResolvedValue({ data: [{ id: 'c1', name: 'Cliente SL' }], error: undefined })
})

describe('CaptureScreen (S6.11)', () => {
  it('C1: el panel inicial conserva dirección, Tomar foto y Subir archivo sin pedir la cámara', () => {
    const open = vi.fn()
    useCameraStreamMock.mockReturnValue({ status: 'idle', stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('radio', { name: 'Recibida' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Emitida' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subir archivo' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir cámara' })).not.toBeInTheDocument()
    expect(open).not.toHaveBeenCalled()
  })

  it('C2: tras elegir empresa, Tomar foto solicita la cámara y muestra el overlay completo', async () => {
    const open = vi.fn()
    useCameraStreamMock.mockReturnValue({ status: 'idle', stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await screen.findByRole('option', { name: 'Cliente SL' })
    await user.selectOptions(screen.getByLabelText('Empresa'), 'c1')
    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    expect(open).toHaveBeenCalledOnce()
  })

  it('C2: tenant_admin no abre la cámara hasta elegir la empresa autorizada', async () => {
    const open = vi.fn()
    useCameraStreamMock.mockReturnValue({ status: 'idle', stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))

    expect(open).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/elige una empresa/i)
  })

  it('C2: la cámara activa ocupa la pantalla y ofrece guía A4, Capturar foto y Cerrar cámara', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).toHaveClass('fixed', 'inset-0')
    expect(screen.getByTestId('camera-guide-frame')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar cámara' })).toBeInTheDocument()
  })

  it('C3: Capturar foto apaga la cámara, normaliza y sube directamente sin revisión', async () => {
    const close = vi.fn()
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close, retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, CORNERS))
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida'))
    expect(close).toHaveBeenCalled()
    expect(screen.queryByRole('heading', { name: 'Revisar foto' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Usar esta foto' })).not.toBeInTheDocument()
  })

  it('C3: conserva la dirección elegida hasta el envío directo', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Emitida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'emitida'))
  })

  it('C4: el selector normaliza y envía el archivo sin revisión intermedia', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()
    const file = new File(['contenido'], 'foto.heic', { type: 'image/heic' })

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), file)

    await waitFor(() => expect(fileToJpegBlobMock).toHaveBeenCalledWith(file))
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida'))
    expect(screen.queryByRole('heading', { name: 'Revisar foto' })).not.toBeInTheDocument()
  })

  it('C4: mientras la API acepta el archivo, comunica que procesa la factura', async () => {
    let resolveUpload: (value: unknown) => void = () => {}
    postMock.mockImplementationOnce(() => new Promise((resolve) => { resolveUpload = resolve }))
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), new File(['contenido'], 'foto.jpg', { type: 'image/jpeg' }))

    expect(await screen.findByText('Procesando factura...')).toBeInTheDocument()
    resolveUpload({ data: { id: 'file-abc' }, error: undefined, response: { status: 201 } })
  })

  it('C5: un fichero no decodificable deja el panel listo para elegir otra foto', async () => {
    fileToJpegBlobMock.mockRejectedValueOnce(new Error('invalid image'))
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), new File(['x'], 'rota.jpg', { type: 'image/jpeg' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo preparar la foto/i)
    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subir archivo' })).toBeInTheDocument()
  })

  it('C5: cerrar la cámara detiene el stream', async () => {
    const close = vi.fn()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close, retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Cerrar cámara' }))

    expect(close).toHaveBeenCalledOnce()
  })

  it('C5: user sin empresa no puede abrir cámara ni selector de archivo', () => {
    useSessionMock.mockReturnValue({ ...USER_SESSION, user: { ...USER_SESSION.user, company: null } })
    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no se pudo cargar tu empresa/i)
    expect(screen.queryByRole('button', { name: 'Tomar foto' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Subir archivo' })).not.toBeInTheDocument()
  })

  it('C5: un resultado de cámara tras desmontar no puede subir ni navegar', async () => {
    let resolveAnalysis: (value: { sharpness: number; corners: typeof CORNERS }) => void = () => {}
    analyzeFrameMock.mockImplementationOnce(() => new Promise((resolve) => { resolveAnalysis = resolve }))
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded, unmount } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    unmount()
    resolveAnalysis({ sharpness: 200, corners: CORNERS })

    await waitFor(() => expect(analyzeFrameMock).toHaveBeenCalled())
    expect(postMock).not.toHaveBeenCalled()
    expect(onUploaded).not.toHaveBeenCalled()
  })
})
