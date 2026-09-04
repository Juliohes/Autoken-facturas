import { useEffect, useRef, useState } from 'react'

import { sourcePointToScreen, type ScreenPoint } from './coordinates'
import type { Corner } from './types'

export type DocumentOverlayState = 'none' | 'detected' | 'good' | 'stabilizing' | 'auto_armed'

export interface DocumentOverlayProps {
  corners: readonly Corner[] | null
  sourceWidth: number
  sourceHeight: number
  state?: DocumentOverlayState
}

function pointsForOverlay(
  corners: readonly Corner[] | null,
  sourceWidth: number,
  sourceHeight: number,
  containerWidth: number,
  containerHeight: number,
): ScreenPoint[] | null {
  if (!corners || corners.length !== 4 || sourceWidth <= 0 || sourceHeight <= 0 || containerWidth <= 0 || containerHeight <= 0) return null
  return corners.map((corner) => sourcePointToScreen(corner, {
    sourceWidth,
    sourceHeight,
    containerWidth,
    containerHeight,
  }))
}

export function DocumentOverlay({ corners, sourceWidth, sourceHeight, state = 'none' }: DocumentOverlayProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const points = pointsForOverlay(corners, sourceWidth, sourceHeight, size.width, size.height)
  const polygonPoints = points?.map(({ x, y }) => `${x},${y}`).join(' ')
  const stroke = 'currentColor'
  const strokeWidth = state === 'good' || state === 'auto_armed' ? 4 : 3
  const opacity = state === 'none' ? 0.35 : state === 'stabilizing' ? 0.65 : 1

  useEffect(() => {
    const element = svgRef.current
    if (!element) return undefined
    const updateSize = () => {
      const rect = element.getBoundingClientRect()
      setSize((current) => current.width === rect.width && current.height === rect.height
        ? current
        : { width: rect.width, height: rect.height })
    }
    updateSize()
    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver(updateSize)
      observer.observe(element)
      return () => observer.disconnect()
    }
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  return (
    <svg
      ref={svgRef}
      data-testid="document-overlay"
      aria-hidden="true"
      className="tn-document-overlay pointer-events-none absolute inset-0 h-full w-full text-[color:var(--brand-cyan-light)]"
    >
      <rect
        x="6%"
        y="10%"
        width="88%"
        height="80%"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity={opacity}
        strokeDasharray={state === 'stabilizing' ? '8 6' : undefined}
        vectorEffect="non-scaling-stroke"
      />
      {polygonPoints && (
        <polygon
          data-testid="document-overlay-polygon"
          points={polygonPoints}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          opacity={opacity}
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  )
}
