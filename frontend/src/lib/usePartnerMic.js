import { useEffect, useRef, useState } from 'react'

const SpeechRecognition =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null

export const partnerMicSupported = Boolean(SpeechRecognition)

/**
 * Listens to the conversation partner (nurse, family) so SilentVoice knows the question
 * being answered. Only the partner's speech is transcribed; the user's video has no audio.
 */
export function usePartnerMic({ enabled, onFinal }) {
  const [interim, setInterim] = useState('')
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const onFinalRef = useRef(onFinal)
  onFinalRef.current = onFinal

  useEffect(() => {
    if (!enabled || !SpeechRecognition) return
    let stopped = false
    const rec = new SpeechRecognition()
    rec.lang = 'en-US'
    rec.continuous = true
    rec.interimResults = true
    rec.onstart = () => {
      setListening(true)
      setError('')
    }
    rec.onresult = (e) => {
      let live = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) {
          const text = r[0].transcript.trim()
          if (text) onFinalRef.current?.(text)
        } else live += r[0].transcript
      }
      setInterim(live.trim())
    }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed') setError('Microphone access is blocked.')
      else if (e.error === 'network') setError('Partner listening needs an internet connection.')
    }
    rec.onend = () => {
      setListening(false)
      setInterim('')
      if (!stopped) {
        try {
          rec.start()
        } catch {
          /* already started */
        }
      }
    }
    try {
      rec.start()
    } catch {
      /* ignore */
    }
    return () => {
      stopped = true
      rec.onend = null
      rec.abort()
      setListening(false)
    }
  }, [enabled])

  return { interim, listening, error }
}
