import { useEffect, useRef, useState } from 'react'
import { slotVideoStyle } from '../lib/useMouthTracker.js'

const MODES = [
  ['tap', 'Tap mode'],
  ['hold', 'Hold mode'],
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
  voiceAssist,
  onToggleVoiceAssist,
  isLiveMicActive,
  onToggleLiveMic,
  isBlackHole,
}) {
  const [full, setFull] = useState(false)
  const slotRef = useRef(null)
  const slotSize = useSize(slotRef)
  const { recording, seconds, level, brightness, start, stop, toggle, micLiveText } = capture
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
  else if (isLiveMicActive) status = 'Streaming continuously to Zoom & Google Meet via BlackHole…'
  else if (busy === 'reading') status = 'Reading your lips and audio…'
  else if (busy === 'confirm') status = 'Check the sentence before it goes anywhere.'
  else if (recording) {
    status = micLiveText
      ? `🎙️ Hearing: “${micLiveText}” (${seconds.toFixed(1)} s)`
      : `Watching lips & mic: ${seconds.toFixed(1)} s (press Stop when done)`
  }
  else if (mode === 'tap') status = 'Press Start, mouth or speak your sentence, then press Stop.'
  else status = 'Hold the button while you mouth or speak your sentence.'

  if (voiceAssist && !cameraError && modelState === 'ready' && !isLiveMicActive && !recording) {
    status += ' • Voice Assist listening for faint speech'
  }

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

      <fieldset className="choice choice-reading-mode">
        <legend className="reading-mode-legend">Reading mode</legend>
        <div className="seg seg-reading-mode" role="radiogroup" aria-label="Reading mode">
          {MODES.map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={mode === id}
              aria-pressed={mode === id}
              className={`seg-btn ${mode === id ? 'is-active' : ''}`}
              onClick={() => onModeChange(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      {mode === 'tap' ? (
        <div className="camera-actions tap-controls">
          <button
            className={`btn btn-start ${recording ? 'is-recording' : ''}`}
            disabled={disabled || recording}
            onClick={() => start()}
            type="button"
            aria-label="Start recording lips and voice"
          >
            <span className="dot-indicator on" aria-hidden="true" />
            <span>Start</span>
          </button>
          <button
            className={`btn btn-stop ${recording ? 'is-live' : ''}`}
            disabled={disabled || !recording}
            onClick={() => stop(false)}
            type="button"
            aria-label="Stop recording and recognize speech"
          >
            <span className="square-indicator" aria-hidden="true" />
            <span>{recording ? `Stop (${seconds.toFixed(1)}s)` : 'Stop'}</span>
          </button>
          {recording && (
            <button
              className="btn btn-cancel-recording"
              onClick={() => stop(true)}
              type="button"
              title="Discard this clip without recognizing"
              aria-label="Discard recording"
            >
              ✕
            </button>
          )}
        </div>
      ) : (
        <div className="camera-actions hold-controls">
          <button
            className={`btn btn-hold ${recording ? 'is-live' : ''}`}
            disabled={disabled && !recording}
            {...holdProps}
            type="button"
          >
            <span className={recording ? 'square-indicator' : 'dot-indicator on'} aria-hidden="true" />
            <span>{recording ? `Release when done (${seconds.toFixed(1)}s)` : 'Hold while speaking'}</span>
          </button>
        </div>
      )}

      {recording && micLiveText && (
        <div className="mic-live-preview" role="status" aria-live="polite">
          <span className="live-mic-dot" aria-hidden="true" />
          <span className="live-mic-label">Heard:</span>
          <span className="live-mic-text">“{micLiveText}”</span>
        </div>
      )}

      <div className="camera-options-card">
        <div className="camera-options-info">
          <span className="options-icon" aria-hidden="true">{voiceAssist ? '🎙️' : '🔇'}</span>
          <div className="options-copy">
            <span className="options-title">Microphone Audio Assist</span>
            <span className="options-sub">
              {voiceAssist ? 'Utmost priority for voice, verified with lips' : 'Mouth lip-reading only (microphone ignored)'}
            </span>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={voiceAssist}
          className={`switch-toggle ${voiceAssist ? 'is-on' : 'is-off'}`}
          onClick={onToggleVoiceAssist}
          aria-label="Toggle Microphone Audio Assist"
          title="Captures microphone audio and gives it utmost priority, using lip reading as a visual verifier."
        >
          <span className="switch-thumb" aria-hidden="true" />
        </button>
      </div>

      <p className="fine">Space bar works too.</p>
    </section>
  )
}
