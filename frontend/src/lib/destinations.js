// Where a finished sentence goes: out loud on one of the computer's speakers (built-in or
// Bluetooth), or large on screen. The first-run answer only picks the default.
import { useEffect, useState } from 'react'

/** Speakers the browser can play to. Labels appear once camera access is granted. */
export function useSpeakers() {
  const [speakers, setSpeakers] = useState([])
  const [backendBlackHole, setBackendBlackHole] = useState(false)

  useEffect(() => {
    let alive = true
    fetch('/api/audio/devices')
      .then((r) => r.json())
      .then((data) => {
        if (alive && data.blackhole_detected) {
          setBackendBlackHole(true)
        }
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const md = navigator.mediaDevices
    if (!md?.enumerateDevices) return
    let alive = true
    const update = async () => {
      try {
        const all = (await md.enumerateDevices()).filter((d) => d.kind === 'audiooutput')
        // Chrome lists the system default twice ("Default - X" and "X"); keep the real devices.
        const real = all.filter((d) => d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications')
        const list = (real.length ? real : all).map((d, i) => {
          const isVirtualMic = /blackhole/i.test(d.label)
          return {
            id: d.deviceId === 'default' ? '' : d.deviceId,
            label: d.label || (i === 0 ? 'This computer’s speakers' : `Speaker ${i + 1}`),
            builtIn: !isVirtualMic && /built-in|macbook|internal/i.test(d.label),
            isVirtualMic,
          }
        })

        // If backend detected BlackHole on host system, make sure virtual mic is recognized
        const hasVirtualMic = list.some((s) => s.isVirtualMic)
        if (!hasVirtualMic && backendBlackHole) {
          list.unshift({
            id: 'blackhole-loopback',
            label: 'BlackHole 2ch (Virtual Audio Loopback)',
            builtIn: false,
            isVirtualMic: true,
          })
        }

        // Built-in speakers first, then BlackHole virtual mic, then Bluetooth and others
        list.sort((a, b) => {
          if (a.isVirtualMic && !b.isVirtualMic) return -1
          if (!a.isVirtualMic && b.isVirtualMic) return 1
          return Number(b.builtIn) - Number(a.builtIn)
        })
        if (alive) setSpeakers(list)
      } catch {
        if (alive) setSpeakers([])
      }
    }
    update()
    const timer = setInterval(() => alive && update(), 2000)
    window.addEventListener?.('focus', update)
    md.addEventListener?.('devicechange', update)
    return () => {
      alive = false
      clearInterval(timer)
      window.removeEventListener?.('focus', update)
      md.removeEventListener?.('devicechange', update)
    }
  }, [backendBlackHole])

  return speakers
}

/** The choices in "Goes to". Each speaker is its own option, then "On screen". */
export function destinations(speakers, voiceStatus) {
  const how = voiceStatus?.has_voice ? 'Out loud in your own voice' : 'Out loud'
  const list = (speakers.length ? speakers : [{ id: '', label: 'This computer’s speakers', builtIn: true }]).map((s) => ({
    key: `loud:${s.id}`,
    id: 'loud',
    speakerId: s.id,
    label: s.isVirtualMic ? 'BlackHole 2ch (Zoom & Meet Virtual Mic)' : s.label,
    hint: s.isVirtualMic
      ? 'Virtual microphone for Zoom, Google Meet & video calls'
      : s.builtIn
        ? how
        : `${how}, on this device`,
    action: s.isVirtualMic ? 'Send to Zoom / Meet' : 'Say it',
    again: s.isVirtualMic ? 'Send again' : 'Say it again',
    isVirtualMic: Boolean(s.isVirtualMic),
  }))
  list.push({
    key: 'show',
    id: 'show',
    speakerId: null,
    label: 'On screen',
    hint: 'Large text for the person next to you',
    action: 'Show it',
    again: 'Show it again',
    isVirtualMic: false,
  })
  return list
}

export function findBlackHoleSpeaker(speakers) {
  return speakers.find((s) => s.isVirtualMic || /blackhole/i.test(s.label))
}

/** The option matching the saved preferences. A speaker that's gone falls back to the first one. */
export function currentDestination(dests, prefs) {
  if (prefs?.destination === 'show') return dests.find((d) => d.id === 'show')
  return dests.find((d) => d.id === 'loud' && d.speakerId === (prefs?.speaker_id || '')) || dests[0]
}
