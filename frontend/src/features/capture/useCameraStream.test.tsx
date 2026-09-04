// Comportamiento de recuperación de cámara S6.9. jsdom no tiene hardware, por eso se prueba el
// contrato observable de getUserMedia y la liberación de tracks con streams simulados.
import { act, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCameraStream, type CameraStreamState } from './useCameraStream'

function CameraProbe({ onChange }: { onChange: (state: CameraStreamState) => void }) {
  const camera = useCameraStream()
  useEffect(() => onChange(camera), [camera, onChange])
  return <p>{camera.status}</p>
}

function fakeStream() {
  const track = {
    stop: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }
  return { stream: { getTracks: () => [track] } as unknown as MediaStream, track }
}

describe('useCameraStream (S6.9)', () => {
  const getUserMedia = vi.fn()

  beforeEach(() => {
    getUserMedia.mockReset()
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    })
  })

  it('S6.10 C2: no solicita la cámara hasta que la persona la abre explícitamente', () => {
    render(<CameraProbe onChange={() => undefined} />)

    expect(screen.getByText('idle')).toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
  })

  it('C2: si la trasera exacta no existe, solicita una cámara de vídeo compatible al abrirla', async () => {
    const { stream } = fakeStream()
    getUserMedia.mockRejectedValueOnce(new DOMException('sin trasera', 'OverconstrainedError'))
    getUserMedia.mockResolvedValueOnce(stream)
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)
    await act(async () => camera?.open())

    await waitFor(() => expect(screen.getByText('active')).toBeInTheDocument())
    expect(getUserMedia).toHaveBeenNthCalledWith(1, {
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    })
    expect(getUserMedia).toHaveBeenNthCalledWith(2, {
      video: true,
      audio: false,
    })
  })

  it('C1: si el navegador informa que no hay lente trasera, prueba una cámara compatible', async () => {
    const { stream } = fakeStream()
    getUserMedia.mockRejectedValueOnce(new DOMException('sin trasera', 'NotFoundError'))
    getUserMedia.mockResolvedValueOnce(stream)
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)
    await act(async () => camera?.open())

    await waitFor(() => expect(screen.getByText('active')).toBeInTheDocument())
    expect(getUserMedia).toHaveBeenNthCalledWith(2, {
      video: true,
      audio: false,
    })
  })

  it('S6.14 C1: la resolución pedida es siempre "ideal", nunca "exact"/"min", en ambos intentos', async () => {
    const { stream } = fakeStream()
    getUserMedia.mockRejectedValueOnce(new DOMException('sin trasera', 'OverconstrainedError'))
    getUserMedia.mockResolvedValueOnce(stream)
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)
    await act(async () => camera?.open())

    await waitFor(() => expect(screen.getByText('active')).toBeInTheDocument())
    for (const call of getUserMedia.mock.calls) {
      const constraints = call[0] as { video: MediaTrackConstraints | boolean }
      if (typeof constraints.video !== 'object') continue
      expect(constraints.video).toMatchObject({ width: { ideal: 1920 }, height: { ideal: 1080 } })
      const width = constraints.video.width as Record<string, unknown>
      const height = constraints.video.height as Record<string, unknown>
      expect(width).not.toHaveProperty('exact')
      expect(width).not.toHaveProperty('min')
      expect(height).not.toHaveProperty('exact')
      expect(height).not.toHaveProperty('min')
    }
  })

  it('C7: si se deniega el permiso, no abre una segunda solicitud y ofrece recuperación', async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException('denegado', 'NotAllowedError'))
    const states: CameraStreamState[] = []
    render(<CameraProbe onChange={(state) => { states.push(state) }} />)
    await act(async () => states.at(-1)?.open())

    await waitFor(() => expect(states.at(-1)?.status).toBe('unavailable'))
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(states.at(-1)?.canRetry).toBe(true)
  })

  it('C4: si la solicitud no termina, deja de esperar y permite recuperar la cámara', async () => {
    vi.useFakeTimers()
    getUserMedia.mockImplementation(() => new Promise(() => undefined))
    const states: CameraStreamState[] = []
    render(<CameraProbe onChange={(state) => { states.push(state) }} />)
    await act(async () => states.at(-1)?.open())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(states.at(-1)?.status).toBe('unavailable')
    expect(states.at(-1)?.canRetry).toBe(true)
    vi.useRealTimers()
  })

  it('C5: reintentar detiene el stream anterior antes de solicitar otro', async () => {
    const first = fakeStream()
    const second = fakeStream()
    getUserMedia.mockResolvedValueOnce(first.stream).mockResolvedValueOnce(second.stream)
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)
    await act(async () => camera?.open())

    await waitFor(() => expect(camera?.status).toBe('active'))
    await act(async () => camera?.retry())

    expect(first.track.stop).toHaveBeenCalledOnce()
    await waitFor(() => expect(camera?.stream).toBe(second.stream))
  })

  it('S6.10 C5: cerrar detiene todas las pistas y vuelve al estado inactivo', async () => {
    const { stream, track } = fakeStream()
    getUserMedia.mockResolvedValue(stream)
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)

    await act(async () => camera?.open())
    await waitFor(() => expect(camera?.status).toBe('active'))
    await act(async () => camera?.close())

    expect(track.stop).toHaveBeenCalledOnce()
    expect(screen.getByText('idle')).toBeInTheDocument()
  })

  it('S6.10 C5: un rechazo tardío tras cerrar no reabre el estado de error', async () => {
    let rejectRequest: (error: Error) => void = () => undefined
    getUserMedia.mockImplementation(() => new Promise((_, reject) => {
      rejectRequest = reject
    }))
    let camera: CameraStreamState | null = null
    render(<CameraProbe onChange={(state) => { camera = state }} />)

    await act(async () => camera?.open())
    await act(async () => camera?.close())
    await act(async () => rejectRequest(new DOMException('denegado', 'NotAllowedError')))

    expect(screen.getByText('idle')).toBeInTheDocument()
  })
})
