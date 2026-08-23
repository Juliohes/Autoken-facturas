import type { Corner, NormalizedPoint } from './types'

export interface CoordinateSpace {
  sourceWidth: number
  sourceHeight: number
  containerWidth: number
  containerHeight: number
}

export interface ScreenPoint {
  x: number
  y: number
}

function transform(space: CoordinateSpace) {
  const scale = Math.max(
    space.containerWidth / space.sourceWidth,
    space.containerHeight / space.sourceHeight,
  )
  const renderedWidth = space.sourceWidth * scale
  const renderedHeight = space.sourceHeight * scale
  return {
    scale,
    offsetX: (space.containerWidth - renderedWidth) / 2,
    offsetY: (space.containerHeight - renderedHeight) / 2,
  }
}

export function sourcePointToScreen(point: Corner, space: CoordinateSpace): ScreenPoint {
  const { scale, offsetX, offsetY } = transform(space)
  return { x: point.x * scale + offsetX, y: point.y * scale + offsetY }
}

export function screenPointToSource(point: ScreenPoint, space: CoordinateSpace): Corner {
  const { scale, offsetX, offsetY } = transform(space)
  return { x: (point.x - offsetX) / scale, y: (point.y - offsetY) / scale }
}

export function normalizedPointToScreen(point: NormalizedPoint, space: CoordinateSpace): ScreenPoint {
  return sourcePointToScreen({ x: point.x * space.sourceWidth, y: point.y * space.sourceHeight }, space)
}

export function screenPointToNormalized(point: ScreenPoint, space: CoordinateSpace): NormalizedPoint {
  const source = screenPointToSource(point, space)
  return { x: source.x / space.sourceWidth, y: source.y / space.sourceHeight }
}
