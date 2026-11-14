import { useState } from 'react'

const MODES = [
  ['auto', 'When I move'],
  ['tap', 'Tap'],
  ['hold', 'Hold'],
]

function lightingHint(brightness) {
  if (brightness == null) return ''
  if (brightness < 55) return 'It’s too dark to see your lips. Face a lamp or window.'
  if (brightness > 215) return 'Very bright light. Try facing the light instead of having it behind you.'
  return ''
}

/**
 * The "lip slot": a narrow window that shows only your mouth, so nobody glancing at the
 * screen sees your face. "Show whole camera" opens the full view for lining yourself up.
 */
export default function CameraPanel({
  videoRef,
  cameraError,
  capture,
  mode,
  onModeChange,
  paused,
  onTogglePause,
  busy,
  modelState,
  unmirror,
}) {
  const [full, setFull] = useState(false)
  const { recording, seconds, level, brightness, start, stop, toggle } = capture
  const hint = lightingHint(brightness)

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
  else if (mode === 'auto') status = paused ? 'Paused. Nothing is being read.' : 'Start mouthing, then pause when you’re done.'
  else if (mode === 'tap') status = 'Tap Start, mouth your sentence, then tap Done.'
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

  return (
    <section className="camera" aria-label="Camera">
      <div className={`${full ? 'stage' : 'slot'} ${recording ? 'is-live' : ''} ${unmirror ? '' : 'mirrored'}`}>
        <video ref={videoRef} autoPlay playsInline muted />
        {full && <div className="mouth-guide" aria-hidden="true" />}
        <span className={`slot-dot ${recording ? 'on' : ''}`} aria-hidden="true" />
        <div className="slot-meter" aria-hidden="true">
          <div style={{ transform: `scaleX(${level})` }} />
        </div>
      </div>

      <button className="text-btn" onClick={() => setFull((f) => !f)} aria-pressed={full}>
        {full ? 'Show only my mouth' : 'Show whole camera to line up'}
      </button>

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
          {recording
            ? mode === 'hold'
              ? 'Release when done'
              : 'Done'
            : mode === 'hold'
              ? 'Hold to read'
              : 'Start'}
        </button>
        {mode === 'auto' && (
          <button className="btn" onClick={onTogglePause} disabled={Boolean(cameraError)}>
            {paused ? 'Resume' : 'Pause'}
          </button>
        )}
      </div>
      <p className="fine">Space bar works too.</p>
    </section>
  )
}
