import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { speak, stopSpeaking } from './speech.js'
import { findBlackHoleSpeaker } from './destinations.js'

const MIN_CONFIDENCE_DEFAULT = 0.52
const CHUNK_DURATION_MS = 1800
const DEDUP_WINDOW_MS = 4000

function pickMimeType() {
  const options = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4']
  if (typeof MediaRecorder === 'undefined') return ''
  return options.find((m) => MediaRecorder.isTypeSupported(m)) || ''
}

function normalizePhrase(str) {
  return (str || '')
    .toLowerCase()
    .replace(/[^\w\s]/g, '')
    .trim()
}

/**
 * Live visual speech recognition loop for Zoom virtual microphone transmission.
 * Captures rolling video windows, evaluates mouth movement, transcribes via Auto-AVSR,
 * filters low-confidence hypotheses and duplicates, and routes synthetic speech to BlackHole 2ch.
 */
export function useLiveMic({
  stream,
  videoRef,
  enabled,
  modelReady,
  prefs,
  partnerText,
  speakers,
  voiceStatus,
  onDelivered,
}) {
  const [active, setActive] = useState(false)
  const [muted, setMuted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lastPrediction, setLastPrediction] = useState(null)
  const [liveLog, setLiveLog] = useState([])
  const [latencyMs, setLatencyMs] = useState(0)
  const [targetSpeakerId, setTargetSpeakerId] = useState('')

  const activeRef = useRef(false)
  const mutedRef = useRef(false)
  const busyRef = useRef(false)
  const lastSpokenRef = useRef({ text: '', time: 0 })
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const recorderRef = useRef(null)
  const chunkTimerRef = useRef(null)

  // Detect BlackHole 2ch output device
  const blackHoleSpeaker = findBlackHoleSpeaker(speakers)
  const isBlackHoleDetected = Boolean(blackHoleSpeaker)

  // Default to BlackHole if detected, or saved speaker
  useEffect(() => {
    if (blackHoleSpeaker?.id && !targetSpeakerId) {
      setTargetSpeakerId(blackHoleSpeaker.id)
    } else if (!targetSpeakerId && speakers.length > 0) {
      setTargetSpeakerId(speakers[0].id)
    }
  }, [blackHoleSpeaker, speakers, targetSpeakerId])

  // Sequential speech queue to avoid overlapping audio in Zoom
  const processAudioQueue = useCallback(async () => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return
    if (mutedRef.current) {
      audioQueueRef.current = []
      return
    }

    const nextItem = audioQueueRef.current.shift()
    if (!nextItem) return

    isPlayingRef.current = true
    try {
      await speak(
        nextItem.text,
        {
          ...prefs,
          speaker_id: targetSpeakerId || blackHoleSpeaker?.id || '',
        },
        voiceStatus,
      )
    } catch {
      // Audio fallback handled in speak()
    } finally {
      isPlayingRef.current = false
      if (audioQueueRef.current.length > 0) {
        processAudioQueue()
      }
    }
  }, [prefs, targetSpeakerId, blackHoleSpeaker, voiceStatus])

  const enqueueSpeech = useCallback(
    (text, metadata = {}) => {
      const entry = {
        id: `live-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        text,
        ts: Date.now(),
        muted: mutedRef.current,
        confidence: metadata.confidence,
        confidenceLabel: metadata.confidence_label,
        latencyMs: metadata.latencyMs || 0,
      }

      setLiveLog((prev) => [entry, ...prev.slice(0, 49)])
      onDelivered?.(text, entry)

      if (mutedRef.current) return

      audioQueueRef.current.push({ text })
      processAudioQueue()
    },
    [onDelivered, processAudioQueue],
  )

  // Stability & Deduplication filter
  const isDuplicateOrUnstable = useCallback((rawText, confidence, confidenceLabel) => {
    const text = normalizePhrase(rawText)
    if (!text) return true

    // Confidence filter: reject low confidence hypotheses in live mode
    const minConf = Number(prefs?.live_min_confidence) || MIN_CONFIDENCE_DEFAULT
    if (confidence != null && confidence < minConf) {
      return true
    }
    if (confidenceLabel === 'low') {
      return true
    }

    const now = Date.now()
    const last = lastSpokenRef.current
    const prevText = normalizePhrase(last.text)

    // Exact duplicate within cooldown window
    if (prevText === text && now - last.time < DEDUP_WINDOW_MS) {
      return true
    }

    // Substring / prefix of what was just spoken (e.g. "thank" right after "thank you")
    if (prevText.startsWith(text) && now - last.time < 2500 && text.length < prevText.length) {
      return true
    }

    return false
  }, [prefs])

  // Process a captured video window
  const handleChunkReady = useCallback(
    async (blob, mimeType) => {
      if (!activeRef.current || busyRef.current) return
      busyRef.current = true
      setBusy(true)

      const startT = performance.now()
      try {
        const data = await api.lipread({
          blob,
          mimeType,
          prefs: { ...prefs, recognition_mode: 'fast' },
          partnerText,
          history: [],
        })

        const r = data?.result
        const recognized = r?.text?.trim()
        const totalMs = Math.round(performance.now() - startT)
        setLatencyMs(totalMs)

        if (recognized) {
          const duplicate = isDuplicateOrUnstable(recognized, r.confidence, r.confidence_label)
          setLastPrediction({
            text: recognized,
            confidence: r.confidence,
            confidenceLabel: r.confidence_label,
            isDuplicate: duplicate,
            repaired: r.repaired,
            latencyMs: totalMs,
          })

          if (!duplicate) {
            lastSpokenRef.current = { text: recognized, time: Date.now() }
            enqueueSpeech(recognized, {
              confidence: r.confidence,
              confidence_label: r.confidence_label,
              latencyMs: totalMs,
            })
          }
        }
      } catch (err) {
        // Silent recovery on intermittent window drops
      } finally {
        busyRef.current = false
        setBusy(false)
      }
    },
    [prefs, partnerText, isDuplicateOrUnstable, enqueueSpeech],
  )

  // Continuous window recorder
  const recordWindow = useCallback(() => {
    if (!activeRef.current || !stream) return

    const mimeType = pickMimeType()
    let recorder
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
    } catch {
      return
    }

    const chunks = []
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data)
    }

    recorder.onstop = () => {
      if (!activeRef.current) return
      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || 'video/webm' })
      if (blob.size > 500) {
        handleChunkReady(blob, recorder.mimeType || mimeType || 'video/webm')
      }
      // Schedule the next temporal slice if still active
      if (activeRef.current) {
        recordWindow()
      }
    }

    recorderRef.current = recorder
    recorder.start()

    chunkTimerRef.current = setTimeout(() => {
      if (recorder.state === 'recording') {
        recorder.stop()
      }
    }, CHUNK_DURATION_MS)
  }, [stream, handleChunkReady])

  const startLive = useCallback(() => {
    if (!stream || !modelReady) return
    activeRef.current = true
    setActive(true)
    recordWindow()
  }, [stream, modelReady, recordWindow])

  const stopLive = useCallback(() => {
    activeRef.current = false
    setActive(false)
    if (chunkTimerRef.current) clearTimeout(chunkTimerRef.current)
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try {
        recorderRef.current.stop()
      } catch {}
    }
    stopSpeaking()
    audioQueueRef.current = []
    isPlayingRef.current = false
  }, [])

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev
      mutedRef.current = next
      if (next) {
        stopSpeaking()
        audioQueueRef.current = []
        isPlayingRef.current = false
      }
      return next
    })
  }, [])

  const sendImmediateText = useCallback(
    (text) => {
      if (!text || !text.trim()) return
      const trimmed = text.trim()
      lastSpokenRef.current = { text: trimmed, time: Date.now() }
      enqueueSpeech(trimmed, { confidence: 1.0, confidence_label: 'high', latencyMs: 0 })
    },
    [enqueueSpeech],
  )

  const clearLiveLog = useCallback(() => {
    setLiveLog([])
  }, [])

  // Cleanup on unmount or when stream changes
  useEffect(() => {
    return () => {
      activeRef.current = false
      if (chunkTimerRef.current) clearTimeout(chunkTimerRef.current)
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try {
          recorderRef.current.stop()
        } catch {}
      }
      stopSpeaking()
    }
  }, [])

  return {
    active,
    muted,
    busy,
    latencyMs,
    lastPrediction,
    liveLog,
    targetSpeakerId,
    setTargetSpeakerId,
    isBlackHoleDetected,
    blackHoleSpeaker,
    startLive,
    stopLive,
    toggleMute,
    sendImmediateText,
    clearLiveLog,
  }
}
