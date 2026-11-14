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
    let fatal = false
    let quickEnds = 0
    let startedAt = 0
    let restartTimer = null
    const rec = new SpeechRecognition()
    rec.lang = 'en-US'
    rec.continuous = true
    rec.interimResults = true
    const begin = () => {
      startedAt = Date.now()
      try {
        rec.start()
      } catch {
        /* already started */
      }
    }
    rec.onstart = () => {
      setListening(true)
      setError('')
    }
    rec.onresult = (e) => {
      quickEnds = 0
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
      // These won't fix themselves by retrying; stop instead of restarting in a loop.
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        fatal = true
        setError('Microphone access is blocked. Allow the microphone in the address bar, then turn listening on again.')
      } else if (e.error === 'audio-capture') {
        fatal = true
        setError('No microphone found.')
      } else if (e.error === 'network') {
        fatal = true
        setError('Listening needs an internet connection in this browser. You can type what they said instead.')
      }
    }
    rec.onend = () => {
      setListening(false)
      setInterim('')
      if (stopped || fatal) return
      // Chrome ends recognition after silence; restart, but back off if it keeps ending at once.
      quickEnds = Date.now() - startedAt < 1500 ? quickEnds + 1 : 0
      if (quickEnds >= 5) {
        setError('Listening keeps stopping. Turn it off and on again, or type what they said.')
        return
      }
      restartTimer = setTimeout(begin, 250 * (quickEnds + 1))
    }
    begin()
    return () => {
      stopped = true
      clearTimeout(restartTimer)
      rec.onend = null
      rec.abort()
      setListening(false)
      setError('')
    }
  }, [enabled])

  return { interim, listening, error }
}
