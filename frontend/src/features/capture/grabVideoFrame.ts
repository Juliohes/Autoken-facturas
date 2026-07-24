// Extrae el frame actual de un `<video>` como `ImageData`, vía un `<canvas>` intermedio (S2.2).
// Aparte para poder mockearlo en los tests de orquestación: jsdom no reproduce vídeo real, así que
// `video.videoWidth` siempre vale 0 ahí — no hay frame real que grabar en ese entorno.
export function grabVideoFrame(video: HTMLVideoElement): ImageData | null {
  if (video.videoWidth === 0 || video.videoHeight === 0) return null
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(video, 0, 0)
  return ctx.getImageData(0, 0, canvas.width, canvas.height)
}
