import { useEffect, useRef, useState } from 'react'
import { slotVideoStyle } from '../lib/useMouthTracker.js'

function lightingHint(brightness) {
  if (brightness == null) return ''
  if (brightness < 55) return 'It’s too dark to see your lips. Face a lamp or window.'
  if (brightness > 215) return 'Very bright light. Try facing the light instead of having it behind you.'
  return ''
}

function useSize(ref) {
  const [size, setSize] = useState(null)
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [ref])
  return size
}

/**
 * The "lip slot": a narrow window that shows only your mouth, so nobody glancing at the
 * screen sees your face. It follows your mouth when you move. "Show whole camera" opens the
 * full view for lining yourself up.
 */
export default function CameraPanel({
  videoRef,
  cameraError,
  capture,
  busy,
  modelState,
  unmirror,
  mouth,
  following,
}) {
  const [full, setFull] = useState(false)
  const slotRef = useRef(null)
  const slotSize = useSize(slotRef)
  const { recording, seconds, level, brightness, start, stop } = capture
  const hint = lightingHint(brightness)
  const video = videoRef.current
  const aspect = video?.videoWidth ? video.videoWidth / video.videoHeight : 4 / 3
  const tracked = !full && following ? slotVideoStyle(mouth, slotSize, !unmirror, aspect) : null

  let status
  if (cameraError) status = cameraError
  else if (modelState !== 'ready')
    status =
      modelState === 'error'
        ? 'Lip reading is unavailable right now. Shortcuts, phrases and spelling still work.'
        : 'Lip reading is starting. Shortcuts, phrases and spelling already work.'
  else if (busy === 'reading') status = 'Reading your lips…'
  else if (busy === 'confirm') status = 'Check the sentence before it goes anywhere.'
  else if (recording) status = `Watching your lips: ${seconds.toFixed(1)} s. Let go when you’re done.`
  else status = 'Hold the button or the Space bar while you mouth your sentence, then let go.'

  const disabled = Boolean(cameraError) || modelState !== 'ready' || busy === 'reading'
  // Lip reading only runs while the button is held down.
  const holdProps = {
    onPointerDown: (e) => {
      e.currentTarget.setPointerCapture?.(e.pointerId)
      start()
    },
    onPointerUp: () => stop(),
    onPointerCancel: () => stop(true),
    onKeyDown: (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) {
        e.preventDefault()
        e.stopPropagation()
        start()
      }
    },
    onKeyUp: (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        e.stopPropagation()
        stop()
      }
    },
  }

  const guideStyle =
    full && mouth
      ? {
          left: `${((unmirror ? mouth.x : 1 - mouth.x) - mouth.face_w * 0.4) * 100}%`,
          top: `${(mouth.y - mouth.face_w * 0.22) * 100}%`,
          width: `${mouth.face_w * 80}%`,
          height: `${mouth.face_w * 44 * aspect}%`,
        }
      : undefined

  return (
    <section className="camera" aria-label="Camera">
      <div
        ref={slotRef}
        className={`${full ? 'stage' : 'slot'} ${recording ? 'is-live' : ''} ${unmirror ? '' : 'mirrored'} ${tracked ? 'is-tracked' : ''}`}
      >
        <video ref={videoRef} autoPlay playsInline muted style={tracked || undefined} />
        {full && <div className="mouth-guide" style={guideStyle} aria-hidden="true" />}
        <span className={`slot-dot ${recording ? 'on' : ''}`} aria-hidden="true" />
        <div className="slot-meter" aria-hidden="true">
          <div style={{ transform: `scaleX(${level})` }} />
        </div>
      </div>

      <button className="text-btn" onClick={() => setFull((f) => !f)} aria-pressed={full}>
        {full ? 'Show only my mouth' : 'Show whole camera to line up'}
      </button>
      {following && !mouth && !cameraError && modelState === 'ready' && (
        <p className="fine">Looking for your face. Sit so your whole face is in view.</p>
      )}

      {hint && !cameraError && <p className="hint-warn">{hint}</p>}
      <p className="camera-status" role="status" aria-live="polite">
        {status}
      </p>

      <div className="camera-actions">
        <button className={`btn btn-dark ${recording ? 'is-live' : ''}`} disabled={disabled && !recording} {...holdProps}>
          {recording ? 'Reading… let go when done' : 'Hold to read my lips'}
        </button>
      </div>
      <p className="fine">Or hold the Space bar.</p>
    </section>
  )
}
