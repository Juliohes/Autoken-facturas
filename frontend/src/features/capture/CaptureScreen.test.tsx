// Comportamientos observables de la captura directa S6.11. Canvas y cámara se
// simulan porque jsdom no proporciona píxeles ni un MediaStream real.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api, postMultipart } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { analyzeFrame } from './analyzeFrame'
import { CaptureScreen } from './CaptureScreen'
import { grabVideoFrame } from './grabVideoFrame'
import { fileToJpegBlob } from './normalizeToJpeg'
import { processCapturedFrame } from './processCapture'
import { useCameraStream } from './useCameraStream'

vi.mock('../../api/client', () => ({ api: { GET: vi.fn(), POST: vi.fn() }, postMultipart: vi.fn() }))
vi.mock('../session/SessionProvider', () => ({ useSession: vi.fn() }))
vi.mock('./useCameraStream')
vi.mock('./grabVideoFrame')
vi.mock('./analyzeFrame')
vi.mock('./processCapture')
vi.mock('./normalizeToJpeg')

const getMock = api.GET as unknown as Mock<(...args: never[]) => Promise<unknown>>
const postMultipartMock = vi.mocked(postMultipart)
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

function renderScreen(onUploaded = vi.fn(), cameraReady = true, locationState?: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const screenTree = () => (
    <MemoryRouter initialEntries={[{ pathname: '/capturar', state: locationState }]}>
      <QueryClientProvider client={client}><CaptureScreen onUploaded={onUploaded} /></QueryClientProvider>
    </MemoryRouter>
  )
  const view = render(screenTree())
  if (cameraReady) {
    const video = document.querySelector('video')
    if (video) {
      Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
      fireEvent.loadedData(video)
    }
  }
  return { onUploaded, rerender: () => view.rerender(screenTree()), unmount: view.unmount }
}

function successfulUpload() {
  postMultipartMock.mockResolvedValueOnce(new Response(JSON.stringify({
    id: 'file-abc', company_id: 'c1', content_type: 'image/jpeg', size_bytes: 10, sha256: 'x', status: 'pending_ocr', scan_status: 'clean', created_at: '2026-08-13T00:00:00Z',
  }), { status: 201 }))
}

beforeEach(() => {
  getMock.mockReset()
  postMultipartMock.mockReset()
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
  // spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md, C7
  it('S6.14 C7: con un mensaje en el estado de navegación, lo muestra como aviso visible', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen(vi.fn(), true, { message: 'La foto no se pudo leer. Repite la captura.' })

    expect(screen.getByText('La foto no se pudo leer. Repite la captura.')).toBeInTheDocument()
  })

  it('S6.14 C7: sin mensaje en el estado de navegación, no muestra ningún aviso', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()

    expect(screen.queryByTestId('capture-redirect-message')).not.toBeInTheDocument()
  })

  it('C2: el selector y las acciones de captura aparecen sin un enlace redundante al historial', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()

    const directionSelector = screen.getByRole('radiogroup', { name: 'Dirección' })
    const takePhoto = screen.getByRole('button', { name: 'Tomar foto' })
    const multiplePages = screen.getByRole('button', { name: 'Varias hojas' })

    expect(screen.queryByRole('link', { name: /ver historial|mis facturas/i })).not.toBeInTheDocument()
    // R-056: "Subir factura" se ha movido a la pestaña Subir Archivo; ya no está en el escáner.
    expect(screen.queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Capturar factura' })).toHaveClass('sr-only')
    expect(screen.getByRole('heading', { name: 'Capturar factura' }).closest('section')).toHaveClass('tn-capture-entry-screen')
    expect(directionSelector.compareDocumentPosition(takePhoto)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    // "Tomar foto" y "Varias hojas" son botones independientes (bloque A.4): ya no comparten el
    // contenedor .tn-capture-segmented ni sus clases de segmento solapado.
    expect(takePhoto).toHaveClass('tn-capture-primary-btn')
    expect(multiplePages).toHaveClass('tn-capture-secondary-btn')
    expect(multiplePages).not.toHaveClass('tn-capture-primary-btn')
    expect(screen.queryByRole('group', { name: 'Añadir factura' })).not.toBeInTheDocument()
    expect(multiplePages).toHaveAttribute('aria-pressed', 'false')
    expect(takePhoto.querySelector('svg')).toBeInTheDocument()
    expect(multiplePages.querySelector('svg')).toBeInTheDocument()
  })

  it('R-056 C3: entra sin dirección seleccionada y bloquea las acciones de captura', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()

    expect(screen.getByRole('radio', { name: 'Recibida' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'Emitida' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Varias hojas' })).toBeDisabled()
    // R-056: "Subir factura" vive en la pestaña Subir Archivo, no en el escáner.
    expect(screen.queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
  })

  it('R-056 C4: el escáner no muestra la entrada visible de captura continua', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()

    expect(screen.queryByRole('button', { name: 'Varias facturas' })).not.toBeInTheDocument()
  })

  it('C1: el panel inicial conserva dirección, Tomar foto y Subir archivo sin pedir la cámara', () => {
    const open = vi.fn()
    useCameraStreamMock.mockReturnValue({ status: 'idle', stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('radio', { name: 'Recibida' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Emitida' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    // R-056: "Subir factura" vive en la pestaña Subir Archivo, no en el escáner.
    expect(screen.queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
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

  it('S6.13 C3: la subida simple incluye la dirección elegida para que sobreviva al OCR y a una reapertura', async () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    successfulUpload()
    renderScreen()
    const user = userEvent.setup()
    const file = new File(['imagen'], 'factura.jpg', { type: 'image/jpeg' })

    await user.click(screen.getByRole('radio', { name: 'Emitida' }))
    await user.upload(screen.getByLabelText('Elige o toma una foto'), file)
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(postMultipartMock).toHaveBeenCalledOnce())
    const body = postMultipartMock.mock.calls[0][1]
    expect(body.get('direction')).toBe('emitida')
  })

  it('R-052 C8: un duplicado propio no crea otra factura y ofrece revisar la original o repetir', async () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    postMultipartMock.mockResolvedValueOnce(new Response(JSON.stringify({ duplicate_of: 'file-original' }), { status: 409 }))
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()
    const file = new File(['imagen'], 'factura.jpg', { type: 'image/jpeg' })

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.upload(screen.getByLabelText('Elige o toma una foto'), file)
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Factura duplicada' })).toBeInTheDocument())
    expect(onUploaded).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Revisar factura original' })).toHaveAttribute('href', '/confirmar/file-original')
  })

  it('C2: la cámara activa ocupa la pantalla y ofrece guía A4, Capturar foto y Cerrar cámara', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).toHaveClass('fixed', 'inset-0')
    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).toHaveClass('tn-capture-stage')
    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' }).firstElementChild).toHaveClass('tn-capture-stage-body')
    expect(screen.getByTestId('camera-stage-controls')).toHaveClass('tn-capture-stage-controls')
    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).not.toHaveClass('tn-liquid-glass')
    expect(screen.getByTestId('camera-guide-frame')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar cámara' })).toBeInTheDocument()
  })

  it('C2: al activar la cámara conecta el stream al vídeo y arranca su previsualización', async () => {
    const stream = { getTracks: () => [] } as unknown as MediaStream
    const play = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: play })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })

    renderScreen()

    const video = document.querySelector('video') as HTMLVideoElement
    await waitFor(() => expect(video.srcObject).toBe(stream))
    expect(play).toHaveBeenCalled()
  })

  it('R-007: la cámara ofrece AUTO por defecto y MANUAL como alternativa explícita', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('radio', { name: 'Automático' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Manual' })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeEnabled()
  })

  it('R-007: cambiar a MANUAL reinicia AUTO pero mantiene disponible el disparo consciente', async () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Manual' }))

    expect(screen.getByRole('radio', { name: 'Manual' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeEnabled()
    expect(screen.queryByText('Factura lista. Capturando…')).not.toBeInTheDocument()
  })

  it('R-007: si la cámara rechaza un frame, libera el lock y permite volver a intentarlo', async () => {
    const grabError = new Error('capture failed')
    grabVideoFrameMock.mockRejectedValueOnce(grabError)
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo preparar la foto/i)

    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await waitFor(() => expect(grabVideoFrameMock).toHaveBeenCalledTimes(2))
  })

  it('R-052: si falla el análisis OpenCV, conserva la foto y permite revisarla', async () => {
    analyzeFrameMock.mockRejectedValueOnce(new Error('opencv unavailable'))
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    expect(await screen.findByRole('button', { name: 'Usar foto' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, null)
  })

  it('S6.9: Escape cierra el diálogo de cámara y devuelve el control al flujo', async () => {
    const close = vi.fn()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close, retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.keyboard('{Escape}')

    expect(close).toHaveBeenCalledOnce()
  })

  it('S6.12 C3: la cámara simple cubre el viewport y muestra la vista previa a sangre con una guía cercana al borde', () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).toHaveClass('fixed', 'inset-0', 'p-0')
    expect(document.querySelector('video')).toHaveClass('h-full', 'w-full', 'object-cover')
    expect(screen.getByTestId('camera-guide-frame')).toHaveClass('inset-2')
  })

  it('S6.12 C4: una cámara con flash ofrece Linterna y alterna la luz sin cerrar la captura', async () => {
    const applyConstraints = vi.fn().mockResolvedValue(undefined)
    const track = { getCapabilities: () => ({ torch: true }), applyConstraints } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Activar linterna' }))

    expect(applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] })
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Desactivar linterna' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('S6.12 C4: una cámara sin flash sigue lista para capturar sin prometer una linterna inexistente', () => {
    const track = { getCapabilities: () => ({}) } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()

    expect(screen.queryByRole('button', { name: 'Activar linterna' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeEnabled()
  })

  it('S6.12 C4: un fallo al encender la linterna no bloquea ni muestra un error engañoso', async () => {
    const applyConstraints = vi.fn().mockRejectedValue(new DOMException('flash unavailable', 'OverconstrainedError'))
    const track = { getCapabilities: () => ({ torch: true }), applyConstraints } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Activar linterna' }))

    expect(applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] })
    expect(screen.getByRole('button', { name: 'Capturar foto' })).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('S6.12 C6: Varias hojas abre la cámara completa y guía primero hacia los datos fiscales', async () => {
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()

    expect(open).toHaveBeenCalledOnce()
    expect(screen.getByRole('dialog', { name: 'Cámara para capturar factura' })).toHaveClass('fixed', 'inset-0')
    expect(screen.getByText(/página 1.*datos fiscales/i)).toBeInTheDocument()
  })

  it('S6.12 C7: Varias hojas conserva el orden, permite quitar una página y exige dos antes de enviar', async () => {
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()
    const firstPage = new File(['página 1'], 'fiscal.jpg', { type: 'image/jpeg' })
    const secondPage = new File(['página 2'], 'importes.jpg', { type: 'image/jpeg' })

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), firstPage)

    expect(await screen.findByRole('listitem', { name: /página 1.*datos fiscales/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar factura' })).toBeDisabled()
    expect(screen.getByText(/añade.*importes/i)).toBeInTheDocument()

    await user.upload(screen.getByLabelText(/elige o toma una foto/i), secondPage)

    expect(await screen.findByRole('listitem', { name: /página 2.*importes/i })).toBeInTheDocument()
    const [firstThumbnail, secondThumbnail] = screen.getAllByRole('listitem')
    expect(firstThumbnail).toHaveAccessibleName(/página 1.*datos fiscales/i)
    expect(secondThumbnail).toHaveAccessibleName(/página 2.*importes/i)
    expect(screen.getByRole('button', { name: 'Enviar factura' })).toBeEnabled()
    expect(screen.getByText(/datos complementarios/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quitar página 2' }))

    expect(screen.queryByRole('listitem', { name: /página 2.*importes/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar factura' })).toBeDisabled()
  })

  it('S6.12 C7: bloquea una segunda pulsación mientras prepara la página para no descartar ni reordenar capturas', async () => {
    let resolveAnalysis: (value: { sharpness: number; corners: typeof CORNERS }) => void = () => {}
    analyzeFrameMock.mockImplementationOnce(() => new Promise((resolve) => { resolveAnalysis = resolve }))
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()
    const video = document.querySelector('video')
    Object.defineProperties(video as HTMLVideoElement, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video as HTMLVideoElement)
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    expect(screen.getByRole('button', { name: 'Añadiendo página…' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Añadiendo página…' }))

    expect(analyzeFrameMock).toHaveBeenCalledTimes(1)
    resolveAnalysis({ sharpness: 200, corners: CORNERS })

    await screen.findByText(/página 2.*importes/i)
    expect(processCapturedFrameMock).toHaveBeenCalledTimes(1)
  })

  it('S6.12 C7: cada captura multipágina vuelve automáticamente al panel para ver, quitar o enviar las hojas', async () => {
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    const close = vi.fn(() => { status = 'idle' })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream: null, canRetry: true, unavailableReason: null, open, close, retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()
    let video = document.querySelector('video') as HTMLVideoElement
    Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video)
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(close).toHaveBeenCalledOnce())
    rerender()
    expect(screen.getByRole('listitem', { name: /página 1.*datos fiscales/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quitar página 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar factura' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Tomar otra foto' }))
    rerender()
    expect(screen.getByText(/página 2.*importes/i)).toBeInTheDocument()
    video = document.querySelector('video') as HTMLVideoElement
    Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video)
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(close).toHaveBeenCalledTimes(2))
    rerender()
    expect(screen.getAllByRole('listitem', { name: /página \d/i })).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Quitar página 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar factura' })).toBeEnabled()
  })

  it('S6.12 C7: si no puede capturar una página, apaga cámara y linterna antes de mostrar el error', async () => {
    const applyConstraints = vi.fn().mockResolvedValue(undefined)
    const track = { getCapabilities: () => ({ torch: true }), applyConstraints } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    const close = vi.fn(() => { status = 'idle' })
    grabVideoFrameMock.mockReturnValue(null)
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream, canRetry: true, unavailableReason: null, open, close, retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()
    const video = document.querySelector('video') as HTMLVideoElement
    Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video)
    await user.click(screen.getByRole('button', { name: 'Activar linterna' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/cámara aún no está lista/i)
    expect(close).toHaveBeenCalledOnce()
    expect(applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ torch: false }] })
  })

  it('S6.12 C7: si falla la normalización de una captura multipágina, apaga cámara y linterna', async () => {
    const applyConstraints = vi.fn().mockResolvedValue(undefined)
    const track = { getCapabilities: () => ({ torch: true }), applyConstraints } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    const close = vi.fn(() => { status = 'idle' })
    processCapturedFrameMock.mockRejectedValueOnce(new Error('invalid frame'))
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream, canRetry: true, unavailableReason: null, open, close, retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()
    const video = document.querySelector('video') as HTMLVideoElement
    Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video)
    await user.click(screen.getByRole('button', { name: 'Activar linterna' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo preparar la foto/i)
    expect(close).toHaveBeenCalledOnce()
    expect(applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ torch: false }] })
  })

  it('S6.12 C7: si falla la normalización de un fichero multipágina, apaga cámara y linterna', async () => {
    const applyConstraints = vi.fn().mockResolvedValue(undefined)
    const track = { getCapabilities: () => ({ torch: true }), applyConstraints } as unknown as MediaStreamTrack
    const stream = { getTracks: () => [track] } as unknown as MediaStream
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    const close = vi.fn(() => { status = 'idle' })
    fileToJpegBlobMock.mockRejectedValueOnce(new Error('invalid image'))
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockImplementation(() => ({ status, stream, canRetry: true, unavailableReason: null, open, close, retry: vi.fn() }))
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))
    rerender()
    await user.click(screen.getByRole('button', { name: 'Activar linterna' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), new File(['rota'], 'rota.jpg', { type: 'image/jpeg' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo preparar una de las fotos/i)
    expect(close).toHaveBeenCalledOnce()
    expect(applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ torch: false }] })
  })

  it('S6.12 C2, C7 y C8: hasta cinco páginas se envían una sola vez en orden y con la dirección elegida', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Emitida' }))
    await user.click(screen.getByRole('button', { name: 'Varias hojas' }))

    for (const pageNumber of [1, 2, 3, 4, 5]) {
      await user.upload(
        screen.getByLabelText(/elige o toma una foto/i),
        new File([`página ${pageNumber}`], `pagina-${pageNumber}.jpg`, { type: 'image/jpeg' }),
      )
    }

    expect(await screen.findAllByRole('listitem', { name: /página \d/i })).toHaveLength(5)
    await user.upload(
      screen.getByLabelText(/elige o toma una foto/i),
      new File(['página 6'], 'pagina-6.jpg', { type: 'image/jpeg' }),
    )
    expect(screen.getAllByRole('listitem', { name: /página \d/i })).toHaveLength(5)
    expect(screen.getByRole('alert')).toHaveTextContent(/máximo de cinco páginas/i)
    await user.click(screen.getByRole('button', { name: 'Enviar factura' }))

    await waitFor(() => expect(postMultipartMock).toHaveBeenCalledOnce())
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'emitida', false))
  })

  // R-012 y R-015 eliminados: el botón "Varias facturas" fue retirado en R-056
  // (Julio confirmó que cada captura siempre vuelve al Escáner y la captura
  // continua ya no tiene entrada visible). La lógica interna de captura continua
  // se conserva pero no se expone como acción de la pantalla principal.

  // spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md, C8
  it('S6.14 C8: con nitidez baja (varianza del Laplaciano < umbral), onUploaded recibe lowSharpness=true', async () => {
    successfulUpload()
    analyzeFrameMock.mockResolvedValueOnce({ sharpness: 50, corners: CORNERS })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida', true))
  })

  it('S6.14 C8: con nitidez alta, onUploaded recibe lowSharpness=false', async () => {
    successfulUpload()
    analyzeFrameMock.mockResolvedValueOnce({ sharpness: 200, corners: CORNERS })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida', false))
  })

  it('S6.14 C8: el FormData de la subida incluye sharpness_score (nitidez calculada en cliente)', async () => {
    successfulUpload()
    analyzeFrameMock.mockResolvedValueOnce({ sharpness: 123.4, corners: CORNERS })
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(postMultipartMock).toHaveBeenCalledOnce())
    const body = postMultipartMock.mock.calls[0][1]
    expect(body.get('sharpness_score')).toBe('123.4')
  })

  it('S6.14 C8: sin análisis de cliente (selector de archivo), el FormData omite sharpness_score', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()
    const file = new File(['contenido'], 'foto.jpg', { type: 'image/jpeg' })

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), file)
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(postMultipartMock).toHaveBeenCalledOnce())
    const body = postMultipartMock.mock.calls[0][1]
    expect(body.get('sharpness_score')).toBeNull()
  })

  it('R-051: con scanner_v2 apagado conserva la captura sin análisis ni recorte OpenCV', async () => {
    let status: 'idle' | 'active' = 'idle'
    const open = vi.fn(() => { status = 'active' })
    const close = vi.fn(() => { status = 'idle' })
    useSessionMock.mockReturnValue({
      ...USER_SESSION,
      user: { ...USER_SESSION.user, feature_flags: { scanner_v2_enabled: false } },
    })
    useCameraStreamMock.mockImplementation(() => ({ status, stream: null, canRetry: true, unavailableReason: null, open, close, retry: vi.fn() }))
    successfulUpload()
    const { rerender } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Tomar foto' }))
    rerender()
    const video = document.querySelector('video') as HTMLVideoElement
    Object.defineProperties(video, { videoWidth: { configurable: true, value: 640 }, videoHeight: { configurable: true, value: 480 } })
    fireEvent.loadedData(video)
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, null))
    expect(analyzeFrameMock).not.toHaveBeenCalled()
  })

  it('R-010: Capturar foto apaga la cámara, muestra preview y solo sube tras confirmar', async () => {
    const close = vi.fn()
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close, retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))

    await waitFor(() => expect(processCapturedFrameMock).toHaveBeenCalledWith(FAKE_FRAME, CORNERS))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida', false))
    expect(close).toHaveBeenCalled()
    // R-056: tras confirmar, vuelve al escáner con mensaje de éxito; no queda en la pantalla preview.
    expect(await screen.findByText(/factura subida correctamente/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Usar foto' })).not.toBeInTheDocument()
  })

  it('R-010: Repetir revoca el preview, vuelve a cámara y no llama al backend', async () => {
    const open = vi.fn()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open, close: vi.fn(), retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await user.click(await screen.findByRole('button', { name: 'Repetir' }))

    expect(open).toHaveBeenCalledOnce()
    expect(postMultipartMock).not.toHaveBeenCalled()
    expect(onUploaded).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Preparando cámara…' })).toBeInTheDocument()
  })

  it('C3: conserva la dirección elegida hasta el envío directo', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Emitida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'emitida', false))
  })

  it('R-010: el selector normaliza y también exige confirmar el preview', async () => {
    successfulUpload()
    useSessionMock.mockReturnValue(USER_SESSION)
    const { onUploaded } = renderScreen()
    const user = userEvent.setup()
    const file = new File(['contenido'], 'foto.heic', { type: 'image/heic' })

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), file)

    await waitFor(() => expect(fileToJpegBlobMock).toHaveBeenCalledWith(file))
    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith('file-abc', 'recibida', false))
    // R-056: tras confirmar, vuelve al escáner con mensaje de éxito; no queda en la pantalla preview.
    expect(await screen.findByText(/factura subida correctamente/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Usar foto' })).not.toBeInTheDocument()
  })

  it('C4: mientras la API acepta el archivo, comunica que procesa la factura', async () => {
    let resolveUpload: (value: Response) => void = () => {}
    postMultipartMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveUpload = resolve }))
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), new File(['contenido'], 'foto.jpg', { type: 'image/jpeg' }))

    await user.click(await screen.findByRole('button', { name: 'Usar foto' }))
    expect(await screen.findByText('Guardando factura…')).toBeInTheDocument()
    resolveUpload(new Response(JSON.stringify({ id: 'file-abc' }), { status: 201 }))
  })

  it('C5: un fichero no decodificable deja el panel listo para elegir otra foto', async () => {
    fileToJpegBlobMock.mockRejectedValueOnce(new Error('invalid image'))
    useSessionMock.mockReturnValue(USER_SESSION)
    renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.upload(screen.getByLabelText(/elige o toma una foto/i), new File(['x'], 'rota.jpg', { type: 'image/jpeg' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo preparar la foto/i)
    // R-056: "Subir factura" vive en la pestaña Subir Archivo, no en el escáner.
    expect(screen.getByRole('button', { name: 'Tomar foto' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
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
    // R-056: "Subir factura" ya no está en el escáner.
    expect(screen.queryByRole('button', { name: 'Subir factura' })).not.toBeInTheDocument()
  })

  it('C5: un resultado de cámara tras desmontar no puede subir ni navegar', async () => {
    let resolveAnalysis: (value: { sharpness: number; corners: typeof CORNERS }) => void = () => {}
    analyzeFrameMock.mockImplementationOnce(() => new Promise((resolve) => { resolveAnalysis = resolve }))
    useSessionMock.mockReturnValue(USER_SESSION)
    useCameraStreamMock.mockReturnValue({ status: 'active', stream: null, canRetry: true, unavailableReason: null, open: vi.fn(), close: vi.fn(), retry: vi.fn() })
    const { onUploaded, unmount } = renderScreen()
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Recibida' }))
    await user.click(screen.getByRole('button', { name: 'Capturar foto' }))
    unmount()
    resolveAnalysis({ sharpness: 200, corners: CORNERS })

    await waitFor(() => expect(analyzeFrameMock).toHaveBeenCalled())
    expect(postMultipartMock).not.toHaveBeenCalled()
    expect(onUploaded).not.toHaveBeenCalled()
  })
})
