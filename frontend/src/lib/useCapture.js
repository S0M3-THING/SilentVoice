import { useCallback, useEffect, useRef, useState } from 'react'

// Where the mouth guide sits, as a fraction of the video frame. CSS uses the same numbers.
export const MOUTH_BOX = { x: 0.32, y: 0.5, w: 0.36, h: 0.26 }

const MIN_CLIP_MS = 600
const MAX_CLIP_MS = 10000
const QUIET_TO_STOP_MS = 850
const COOLDOWN_MS = 900

function pickMimeType() {
  const options = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4']
  if (typeof MediaRecorder === 'undefined') return ''
  return options.find((m) => MediaRecorder.isTypeSupported(m)) || ''
}

/** Silent webcam (no microphone is ever requested for the camera). */
export function useCamera() {
  const videoRef = useRef(null)
  const [stream, setStream] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let active = null
    navigator.mediaDevices
      ?.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
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
            ? 'Camera access is blocked. Allow the camera in your browser’s address bar, then reload.'
            : 'No camera found. Connect a camera or use the phrase board below.',
        )
      })
    if (!navigator.mediaDevices) setError('This browser can’t use the camera. Open SilentVoice in Chrome.')
    return () => {
      cancelled = true
      active?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  useEffect(() => {
    if (videoRef.current && stream && videoRef.current.srcObject !== stream) {
      videoRef.current.srcObject = stream
    }
  })

  return { videoRef, stream, error }
}

/**
 * Records short clips of the user mouthing words.
 * mode "auto": hands-free. Starts when the lips move inside the guide, stops after a pause.
 * mode "tap":  tap once to start, tap again to stop (good for weak hands or a helper).
 * mode "hold": press and hold.
 */
export function useCapture({ videoRef, stream, mode, sensitivity = 0.5, enabled, onClip }) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [level, setLevel] = useState(0)
  const [brightness, setBrightness] = useState(null)

  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const startedAtRef = useRef(0)
  const recordingRef = useRef(false)
  const discardRef = useRef(false)
  const quietMsRef = useRef(0)
  const aboveRef = useRef(0)
  const cooldownUntilRef = useRef(0)
  const onClipRef = useRef(onClip)
  const settingsRef = useRef({ mode, sensitivity, enabled })
  onClipRef.current = onClip
  settingsRef.current = { mode, sensitivity, enabled }

  const start = useCallback(() => {
    if (!stream || recordingRef.current || !settingsRef.current.enabled) return
    const mimeType = pickMimeType()
    const rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
    chunksRef.current = []
    discardRef.current = false
    rec.ondataavailable = (e) => e.data?.size && chunksRef.current.push(e.data)
    rec.onstop = () => {
      const duration = Date.now() - startedAtRef.current
      cooldownUntilRef.current = Date.now() + COOLDOWN_MS
      if (discardRef.current || duration < MIN_CLIP_MS) return
      const type = rec.mimeType || mimeType || 'video/webm'
      const blob = new Blob(chunksRef.current, { type })
      if (blob.size) onClipRef.current?.(blob, type)
    }
    recorderRef.current = rec
    startedAtRef.current = Date.now()
    quietMsRef.current = 0
    recordingRef.current = true
    setRecording(true)
    setSeconds(0)
    rec.start(100)
  }, [stream])

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

  // Motion + lighting analysis on a tiny downscaled copy of the frame.
  useEffect(() => {
    if (!stream) return
    const canvas = document.createElement('canvas')
    const W = 96
    const H = 72
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    let prev = null
    let ema = 0
    let lastTick = performance.now()
    let frame = 0

    const x0 = Math.round(MOUTH_BOX.x * W)
    const y0 = Math.round(MOUTH_BOX.y * H)
    const x1 = Math.round((MOUTH_BOX.x + MOUTH_BOX.w) * W)
    const y1 = Math.round((MOUTH_BOX.y + MOUTH_BOX.h) * H)

    const timer = setInterval(() => {
      const video = videoRef.current
      if (!video || video.readyState < 2) return
      const now = performance.now()
      const dt = now - lastTick
      lastTick = now
      ctx.drawImage(video, 0, 0, W, H)
      const { data } = ctx.getImageData(0, 0, W, H)

      const roi = new Float32Array((x1 - x0) * (y1 - y0))
      let k = 0
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const i = (y * W + x) * 4
          roi[k++] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
        }
      }
      let diff = 0
      if (prev) {
        for (let i = 0; i < roi.length; i++) diff += Math.abs(roi[i] - prev[i])
        diff /= roi.length
      }
      prev = roi
      ema = ema * 0.6 + diff * 0.4

      frame += 1
      if (frame % 8 === 0) {
        let sum = 0
        for (let i = 0; i < data.length; i += 16) sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
        setBrightness(sum / (data.length / 16))
      }
      setLevel(Math.min(1, ema / 18))

      if (recordingRef.current) setSeconds((Date.now() - startedAtRef.current) / 1000)

      const { mode: m, sensitivity: s, enabled: en } = settingsRef.current
      if (recordingRef.current && Date.now() - startedAtRef.current > MAX_CLIP_MS) return stop()
      if (m !== 'auto' || !en) {
        aboveRef.current = 0
        return
      }
      const startAt = 10 - 7 * Math.max(0, Math.min(1, s))
      const stopAt = startAt * 0.5
      if (!recordingRef.current) {
        if (Date.now() < cooldownUntilRef.current) return
        aboveRef.current = ema > startAt ? aboveRef.current + 1 : 0
        if (aboveRef.current >= 2) {
          aboveRef.current = 0
          start()
        }
      } else {
        quietMsRef.current = ema < stopAt ? quietMsRef.current + dt : 0
        if (quietMsRef.current >= QUIET_TO_STOP_MS) stop()
      }
    }, 66)

    return () => clearInterval(timer)
  }, [stream, videoRef, start, stop])

  return { recording, seconds, level, brightness, start, stop, toggle }
}
