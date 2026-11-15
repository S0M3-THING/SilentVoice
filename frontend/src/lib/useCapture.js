import { useCallback, useEffect, useRef, useState } from 'react'

// Where the mouth guide sits, as a fraction of the video frame. CSS uses the same numbers.
export const MOUTH_BOX = { x: 0.32, y: 0.5, w: 0.36, h: 0.26 }

const MIN_CLIP_MS = 600
const MAX_CLIP_MS = 10000

function pickMimeType() {
  const options = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4']
  if (typeof MediaRecorder === 'undefined') return ''
  return options.find((m) => MediaRecorder.isTypeSupported(m)) || ''
}

/** Webcam with optional patient microphone assist for multimodal lip sync. */
export function useCamera({ voiceAssist = true } = {}) {
  const videoRef = useRef(null)
  const [stream, setStream] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let active = null
    navigator.mediaDevices
      ?.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: voiceAssist ? { echoCancellation: true, noiseSuppression: false, autoGainControl: true } : false,
      })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop())
        active = s
        setStream(s)
        if (videoRef.current) videoRef.current.srcObject = s
      })
      .catch((err) => {
        setError(
          err?.name === 'NotAllowedError'
            ? 'Camera/microphone access is blocked. Allow access in your browser’s address bar, then reload.'
            : 'No camera found. Connect a camera or use the phrase board below.',
        )
      })
    if (!navigator.mediaDevices) setError('This browser can’t use the camera. Open SilentVoice in Chrome.')
    return () => {
      cancelled = true
      active?.getTracks().forEach((t) => t.stop())
    }
  }, [voiceAssist])

  useEffect(() => {
    if (videoRef.current && stream && videoRef.current.srcObject !== stream) {
      videoRef.current.srcObject = stream
    }
  })

  return { videoRef, stream, error }
}

/**
 * Records short clips of the user mouthing words.
 * mode "tap":  tap (or Space) once to start, again to stop. Good for weak hands or a helper.
 * mode "hold": press and hold.
 * `mouthRef` (from useMouthTracker) points the movement meter at the mouth wherever it is.
 * `voiceAssist`: captures faint patient vocal audio to fuse with visual lip reading.
 */
export function useCapture({ videoRef, stream, enabled, onClip, mouthRef, voiceAssist = true }) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  const [brightness, setBrightness] = useState(null)
  const [micLiveText, setMicLiveText] = useState('')

  const recorderRef = useRef(null)
  const speechRecRef = useRef(null)
  const patientTextRef = useRef('')
  const chunksRef = useRef([])
  const startedAtRef = useRef(0)
  const recordingRef = useRef(false)
  const discardRef = useRef(false)
  const onClipRef = useRef(onClip)
  const enabledRef = useRef(enabled)
  onClipRef.current = onClip
  enabledRef.current = enabled

  const start = useCallback(() => {
    if (!stream || recordingRef.current || !enabledRef.current) return
    const mimeType = pickMimeType()
    const rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
    chunksRef.current = []
    discardRef.current = false
    patientTextRef.current = ''
    setMicLiveText('')

    if (voiceAssist) {
      const SR = typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null
      if (SR) {
        try {
          if (speechRecRef.current) {
            try { speechRecRef.current.abort() } catch {}
          }
          const sr = new SR()
          sr.continuous = true
          sr.interimResults = true
          sr.lang = 'en-US'
          let accumulatedFinal = ''
          sr.onresult = (e) => {
            let currentInterim = ''
            for (let i = e.resultIndex; i < e.results.length; i++) {
              const res = e.results[i]
              const transcript = res[0]?.transcript || ''
              if (res.isFinal) {
                accumulatedFinal += ' ' + transcript
              } else {
                currentInterim += ' ' + transcript
              }
            }
            const fullTranscript = (accumulatedFinal + ' ' + currentInterim).trim()
            if (fullTranscript) {
              patientTextRef.current = fullTranscript
              setMicLiveText(fullTranscript)
            }
          }
          sr.onerror = (e) => {
            console.warn('Voice assist audio recognition note:', e.error)
          }
          sr.start()
          speechRecRef.current = sr
        } catch (err) {
          console.warn('Could not start microphone speech recognition:', err)
        }
      }
    }

    rec.ondataavailable = (e) => e.data?.size && chunksRef.current.push(e.data)
    rec.onstop = async () => {
      const duration = Date.now() - startedAtRef.current
      if (discardRef.current || duration < MIN_CLIP_MS) {
        if (speechRecRef.current) {
          try { speechRecRef.current.abort() } catch {}
          speechRecRef.current = null
        }
        setMicLiveText('')
        return
      }

      // If speech recognition is active, request it to finish decoding and wait for the final results!
      if (speechRecRef.current) {
        try {
          speechRecRef.current.stop()
        } catch {}
        // Give speech recognition 400ms to deliver pending words from the audio buffer
        await new Promise((r) => setTimeout(r, 400))
        speechRecRef.current = null
      }

      const type = rec.mimeType || mimeType || 'video/webm'
      const blob = new Blob(chunksRef.current, { type })
      const text = (patientTextRef.current || '').trim()
      setMicLiveText('')
      if (blob.size) onClipRef.current?.(blob, type, text)
    }
    recorderRef.current = rec
    startedAtRef.current = Date.now()
    recordingRef.current = true
    setRecording(true)
    setSeconds(0)
    rec.start(100)
  }, [stream, voiceAssist])

  const stop = useCallback((discard = false) => {
    if (!recordingRef.current) return
    discardRef.current = discard
    recordingRef.current = false
    setRecording(false)
    if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop()
  }, [])

  const toggle = useCallback(() => (recordingRef.current ? stop() : start()), [start, stop])

  // If capturing gets disabled mid-clip (e.g. a dialog opened), throw the clip away.
  useEffect(() => {
    if (!enabled && recordingRef.current) stop(true)
  }, [enabled, stop])

  // Movement meter + lighting check on a tiny downscaled copy of the frame.
  useEffect(() => {
    if (!stream) return
    const canvas = document.createElement('canvas')
    const W = 96
    const H = 72
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    let prev = null
    let prevKey = ''
    let ema = 0
    let frame = 0

    const timer = setInterval(() => {
      const video = videoRef.current
      if (!video || video.readyState < 2) return
      ctx.drawImage(video, 0, 0, W, H)
      const { data } = ctx.getImageData(0, 0, W, H)

      // The box around the mouth: tracked if we know where it is, otherwise the guide.
      const m = mouthRef?.current
      const box = m
        ? { x: m.x - m.face_w * 0.35, y: m.y - m.face_w * 0.2, w: m.face_w * 0.7, h: m.face_w * 0.4 }
        : { x: MOUTH_BOX.x, y: MOUTH_BOX.y - MOUTH_BOX.h / 2, w: MOUTH_BOX.w, h: MOUTH_BOX.h }
      const x0 = Math.max(0, Math.round(box.x * W))
      const y0 = Math.max(0, Math.round(box.y * H))
      const x1 = Math.min(W, Math.max(x0 + 2, Math.round((box.x + box.w) * W)))
      const y1 = Math.min(H, Math.max(y0 + 2, Math.round((box.y + box.h) * H)))
      const key = `${x0},${y0},${x1},${y1}`

      const roi = new Float32Array((x1 - x0) * (y1 - y0))
      let k = 0
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const i = (y * W + x) * 4
          roi[k++] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
        }
      }
      let diff = 0
      if (prev && key === prevKey) {
        for (let i = 0; i < roi.length; i++) diff += Math.abs(roi[i] - prev[i])
        diff /= roi.length
      }
      prev = roi
      prevKey = key
      ema = ema * 0.6 + diff * 0.4

      frame += 1
      if (frame % 8 === 0) {
        let sum = 0
        for (let i = 0; i < data.length; i += 16) sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
        setBrightness(sum / (data.length / 16))
      }
      setLevel(Math.min(1, ema / 18))
      if (recordingRef.current) setSeconds((Date.now() - startedAtRef.current) / 1000)
      if (recordingRef.current && Date.now() - startedAtRef.current > MAX_CLIP_MS) stop()
    }, 66)

    return () => clearInterval(timer)
  }, [stream, videoRef, stop, mouthRef])

  return { recording, seconds, level, brightness, start, stop, toggle, micLiveText }
}
