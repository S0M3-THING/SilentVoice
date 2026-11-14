import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { speak } from '../lib/speech.js'

function useRecorder() {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [blob, setBlob] = useState(null)
  const [error, setError] = useState('')
  const recRef = useRef(null)
  const timerRef = useRef(null)

  const start = async () => {
    setError('')
    setBlob(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true } })
      const rec = new MediaRecorder(stream)
      const chunks = []
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        setBlob(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }))
      }
      recRef.current = rec
      rec.start(200)
      const started = Date.now()
      setSeconds(0)
      timerRef.current = setInterval(() => setSeconds((Date.now() - started) / 1000), 200)
      setRecording(true)
    } catch {
      setError('Microphone access is blocked. Allow the microphone in the address bar, then try again.')
    }
  }
  const stop = () => {
    clearInterval(timerRef.current)
    recRef.current?.state === 'recording' && recRef.current.stop()
    setRecording(false)
  }
  useEffect(() => () => clearInterval(timerRef.current), [])
  return { recording, seconds, blob, error, start, stop, reset: () => setBlob(null) }
}

function SetupVoice({ status, onDone }) {
  const [way, setWay] = useState('passage')
  const [files, setFiles] = useState([])
  const [transcript, setTranscript] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const rec = useRecorder()
  const blobUrl = rec.blob ? URL.createObjectURL(rec.blob) : ''

  const ready = consent && (way === 'passage' ? Boolean(rec.blob) : files.length > 0)

  const make = async () => {
    setBusy(true)
    setError('')
    try {
      const payload =
        way === 'passage'
          ? { files: [new File([rec.blob], 'reading.webm', { type: rec.blob.type })], transcript: '', consent, source: 'recording' }
          : { files, transcript, consent, source: 'upload' }
      onDone(await api.createVoice(payload))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <p className="muted small">
        SilentVoice makes a copy of your voice on this computer with an open model (Qwen3-TTS). It needs a few seconds
        of you speaking clearly. Nothing is uploaded.
      </p>
      <div className="seg" role="tablist" aria-label="How to add your voice">
        <button role="tab" aria-selected={way === 'passage'} aria-pressed={way === 'passage'} onClick={() => setWay('passage')}>
          Read a short passage
        </button>
        <button role="tab" aria-selected={way === 'upload'} aria-pressed={way === 'upload'} onClick={() => setWay('upload')}>
          Use old recordings
        </button>
      </div>

      {way === 'passage' ? (
        <div className="stack">
          <p className="muted small">For anyone who can still speak, or wants to bank their voice before surgery. Read this aloud at your normal pace:</p>
          <blockquote className="passage">{status.reading_passage}</blockquote>
          <div className="inline">
            {rec.recording ? (
              <button className="btn btn-dark" onClick={rec.stop}>Stop ({rec.seconds.toFixed(0)} s)</button>
            ) : (
              <button className="btn btn-dark" onClick={rec.start}>{rec.blob ? 'Record again' : 'Start recording'}</button>
            )}
            {blobUrl && !rec.recording && <audio controls src={blobUrl} aria-label="Your recording" />}
          </div>
          {rec.error && <p className="hint-warn">{rec.error}</p>}
        </div>
      ) : (
        <div className="stack">
          <p className="muted small">
            Voicemails, videos or voice notes from before you lost your voice. 10 to 60 seconds of you talking clearly works
            best, without music or other people talking.
          </p>
          <label className="file-pick">
            <span>{files.length ? `${files.length} recording${files.length > 1 ? 's' : ''} chosen` : 'Choose recordings'}</span>
            <input type="file" accept="audio/*,video/*" multiple onChange={(e) => setFiles([...e.target.files])} />
          </label>
          <label className="field">
            <span>What’s said in them (optional)</span>
            <textarea className="input" rows={2} value={transcript} onChange={(e) => setTranscript(e.target.value)} />
            <span className="muted small">Leave this blank and SilentVoice will write it down for you.</span>
          </label>
        </div>
      )}

      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>This is my own voice, or I have permission from the person it belongs to.</span>
      </label>

      <div>
        <button className="btn btn-primary" disabled={!ready || busy} onClick={make}>
          {busy ? 'Making your voice…' : 'Make my voice'}
        </button>
      </div>
      {busy && <p className="muted small">This takes about a minute the first time, while the voice model downloads.</p>}
      {error && <p className="hint-warn">{error}</p>}
    </div>
  )
}

function ReadyVoice({ status, prefs, setPref, onChanged }) {
  const [transcript, setTranscript] = useState(status.transcript)
  const [msg, setMsg] = useState('')
  const [playing, setPlaying] = useState(false)
  const edited = transcript.trim() !== status.transcript

  useEffect(() => setTranscript(status.transcript), [status.transcript])

  const saveTranscript = async () => {
    try {
      onChanged(await api.setVoiceTranscript(transcript))
      setMsg('Saved.')
    } catch (e) {
      setMsg(e.message)
    }
  }

  const playSample = async () => {
    setPlaying(true)
    setMsg('')
    try {
      await speak('Hello, this is my voice. Can you hear me clearly?', { ...prefs, use_my_voice: true }, status)
    } finally {
      setPlaying(false)
    }
  }

  let engineNote = ''
  if (status.engine_state === 'loading') engineNote = 'Getting your voice ready. The first time downloads the voice model (about 1.5 GB).'
  if (status.engine_state === 'error') engineNote = `The voice model didn’t load: ${status.engine_error}`

  return (
    <div className="stack">
      <p className="ok">Your voice is set up.</p>
      <div className="field">
        <span>The sample it copies ({status.seconds} s)</span>
        <audio controls src={`/api/voice/reference?v=${status.created_at}`} />
      </div>
      <label className="field">
        <span>What’s said in the sample</span>
        <textarea className="input" rows={3} value={transcript} onChange={(e) => setTranscript(e.target.value)} />
        <span className="muted small">
          {status.transcript_source === 'auto'
            ? 'Written automatically. Listen to the sample and fix any wrong words, because a mismatch makes the copy sound less like you.'
            : 'This must match the sample word for word.'}
        </span>
      </label>
      {edited && (
        <div>
          <button className="btn" onClick={saveTranscript}>Save transcript</button>
        </div>
      )}
      <label className="toggle">
        <input type="checkbox" checked={Boolean(prefs.use_my_voice)} onChange={(e) => setPref('use_my_voice', e.target.checked)} />
        <span className="toggle-track" aria-hidden="true" />
        <span className="toggle-copy">
          <span className="toggle-label">Speak in my voice</span>
          <span className="muted small">If your voice can’t be made for a sentence, the device voice is used instead.</span>
        </span>
      </label>
      <div className="inline">
        <button className="btn btn-primary" disabled={playing} onClick={playSample}>
          {playing ? 'Making it…' : 'Play a sentence in my voice'}
        </button>
        <button className="btn btn-danger" onClick={async () => onChanged(await api.deleteVoice())}>Delete my voice</button>
      </div>
      {engineNote && <p className="muted small">{engineNote}</p>}
      {msg && <p className="small">{msg}</p>}
    </div>
  )
}

/** Settings section: make, check and manage the user's own voice. */
export default function YourVoice({ prefs, setPref, voiceStatus, onVoiceChanged }) {
  const [status, setStatus] = useState(voiceStatus)

  const update = (s) => {
    setStatus(s)
    onVoiceChanged(s)
  }

  useEffect(() => {
    api.voice().then(update).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (status?.engine_state !== 'loading') return
    const t = setInterval(() => api.voice().then(update).catch(() => {}), 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.engine_state])

  if (!status) return <p className="muted small">Checking…</p>

  return (
    <section className="sub">
      <h3>Your own voice</h3>
      {!status.available ? (
        <p className="muted small">{status.unavailable_reason} The device voice is used instead.</p>
      ) : status.has_voice ? (
        <ReadyVoice status={status} prefs={prefs} setPref={setPref} onChanged={update} />
      ) : (
        <SetupVoice
          status={status}
          onDone={(s) => {
            update(s)
            setPref('use_my_voice', true)
          }}
        />
      )}
    </section>
  )
}
