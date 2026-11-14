import { useEffect, useRef, useState } from 'react'

const INTERVAL_MS = 120 // about 8 looks a second
const SMOOTH = 0.6 // how quickly the slot follows (0..1)
const LOST_AFTER_MS = 2500

/**
 * Follows the mouth so the lip slot stays centred when the user moves.
 * Sends a small JPEG to the local server a few times a second; nothing is stored.
 * Returns the smoothed mouth position (fractions of the frame) as state and as a ref.
 */
export function useMouthTracker({ videoRef, stream, enabled }) {
  const [mouth, setMouth] = useState(null)
  const mouthRef = useRef(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    if (!enabled || !stream || unavailable) {
      mouthRef.current = null
      setMouth(null)
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = 320
    canvas.height = 240
    const ctx = canvas.getContext('2d')
    let busy = false
    let alive = true
    let lastSeen = 0
    let failures = 0

    const tick = async () => {
      const video = videoRef.current
      if (busy || !video || video.readyState < 2) return
      busy = true
      try {
        if (video.videoWidth) canvas.height = Math.round((320 * video.videoHeight) / video.videoWidth)
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.7))
        const form = new FormData()
        form.append('frame', blob, 'frame.jpg')
        const res = await fetch('/api/mouth', { method: 'POST', body: form })
        if (res.status === 503 || res.status === 404) {
          if (++failures >= 3 && alive) setUnavailable(true)
          return
        }
        const m = await res.json()
        if (!alive) return
        failures = 0
        if (m.found) {
          lastSeen = Date.now()
          const p = mouthRef.current
          const next = p
            ? {
                x: p.x + (m.x - p.x) * SMOOTH,
                y: p.y + (m.y - p.y) * SMOOTH,
                face_w: p.face_w + (m.face_w - p.face_w) * SMOOTH,
              }
            : { x: m.x, y: m.y, face_w: m.face_w }
          // Ignore tiny wobbles so the picture doesn't shimmer.
          if (!p || Math.abs(next.x - p.x) > 0.004 || Math.abs(next.y - p.y) > 0.004 || Math.abs(next.face_w - p.face_w) > 0.006) {
            mouthRef.current = next
            setMouth(next)
          }
        } else if (Date.now() - lastSeen > LOST_AFTER_MS && mouthRef.current) {
          mouthRef.current = null
          setMouth(null)
        }
      } catch {
        /* server busy or restarting: try again next tick */
      } finally {
        busy = false
      }
    }

    const timer = setInterval(tick, INTERVAL_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [enabled, stream, videoRef, unavailable])

  return { mouth, mouthRef, unavailable }
}

/**
 * Where to place the video inside the slot so the mouth sits in the middle.
 * The face is scaled to about three quarters of the slot's width, so the lips sit in the middle
 * with some room around them.
 */
export function slotVideoStyle(mouth, slot, mirrored, aspect = 4 / 3) {
  if (!mouth || !slot?.width) return null
  const width = Math.min(slot.width * 6, Math.max(slot.width * 1.4, (slot.width * 0.75) / Math.max(mouth.face_w, 0.05)))
  const height = width / aspect
  const mx = mirrored ? 1 - mouth.x : mouth.x
  return {
    width: `${width}px`,
    height: `${height}px`,
    left: `${slot.width / 2 - mx * width}px`,
    top: `${slot.height / 2 - mouth.y * height}px`,
    transform: mirrored ? 'scaleX(-1)' : 'none',
  }
}
