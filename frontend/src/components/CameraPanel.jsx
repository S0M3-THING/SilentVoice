import { useEffect, useRef, useState } from 'react'
import { slotVideoStyle } from '../lib/useMouthTracker.js'

const MODES = [
  ['tap', 'Tap to start and stop'],
  ['hold', 'Press and hold'],
]

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
  mode,
  onModeChange,
  busy,
  modelState,
  unmirror,
  mouth,
  following,
}) {
  const [full, setFull] = useState(false)
  const slotRef = useRef(null)
  const slotSize = useSize(slotRef)
  const { recording, seconds, level, brightness, start, stop, toggle } = capture
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
  else if (recording) status = `Watching your lips: ${seconds.toFixed(1)} s`
  else if (mode === 'tap') status = 'Press Start, mouth your sentence, then press Done.'
  else status = 'Hold the button while you mouth your sentence.'

  const disabled = Boolean(cameraError) || modelState !== 'ready' || busy === 'reading'
  const holdProps =
    mode === 'hold'
      ? {
          onPointerDown: (e) => {
            e.currentTarget.setPointerCapture?.(e.pointerId)
            start()
          },
          onPointerUp: () => stop(),
          onPointerCancel: () => stop(true),
        }
      : { onClick: toggle }

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

      <fieldset className="choice">
        <legend>Start reading</legend>
        <div className="seg">
          {MODES.map(([id, label]) => (
            <button key={id} aria-pressed={mode === id} onClick={() => onModeChange(id)}>
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="camera-actions">
        <button className={`btn btn-dark ${recording ? 'is-live' : ''}`} disabled={disabled && !recording} {...holdProps}>
          {recording ? (mode === 'hold' ? 'Release when done' : 'Done') : mode === 'hold' ? 'Hold to read' : 'Start'}
        </button>
      </div>
      <p className="fine">Space bar works too.</p>
    </section>
  )
}
