// Where a finished sentence goes: out loud on one of the computer's speakers (built-in or
// Bluetooth), or large on screen. The first-run answer only picks the default.
import { useEffect, useState } from 'react'

/** Speakers the browser can play to. Labels appear once camera access is granted. */
export function useSpeakers() {
  const [speakers, setSpeakers] = useState([])

  useEffect(() => {
    const md = navigator.mediaDevices
    if (!md?.enumerateDevices) return
    let alive = true
    const update = async () => {
      try {
        const all = (await md.enumerateDevices()).filter((d) => d.kind === 'audiooutput')
        // Chrome lists the system default twice ("Default - X" and "X"); keep the real devices.
        const real = all.filter((d) => d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications')
        const list = (real.length ? real : all).map((d, i) => ({
          id: d.deviceId === 'default' ? '' : d.deviceId,
          label: d.label || (i === 0 ? 'This computer’s speakers' : `Speaker ${i + 1}`),
          builtIn: /built-in|macbook|internal/i.test(d.label),
        }))
        // Built-in speakers first, then Bluetooth and other outputs.
        list.sort((a, b) => Number(b.builtIn) - Number(a.builtIn))
        if (alive) setSpeakers(list)
      } catch {
        if (alive) setSpeakers([])
      }
    }
    update()
    md.addEventListener?.('devicechange', update)
    return () => {
      alive = false
      md.removeEventListener?.('devicechange', update)
    }
  }, [])

  return speakers
}

/** The choices in "Goes to". Each speaker is its own option, then "On screen". */
export function destinations(speakers, voiceStatus) {
  const how = voiceStatus?.has_voice ? 'Out loud in your own voice' : 'Out loud'
  const list = (speakers.length ? speakers : [{ id: '', label: 'This computer’s speakers', builtIn: true }]).map((s) => ({
    key: `loud:${s.id}`,
    id: 'loud',
    speakerId: s.id,
    label: s.label,
    hint: s.builtIn ? how : `${how}, on this device`,
    action: 'Say it',
    again: 'Say it again',
  }))
  list.push({
    key: 'show',
    id: 'show',
    speakerId: null,
    label: 'On screen',
    hint: 'Large text for the person next to you',
    action: 'Show it',
    again: 'Show it again',
  })
  return list
}

/** The option matching the saved preferences. A speaker that's gone falls back to the first one. */
export function currentDestination(dests, prefs) {
  if (prefs?.destination === 'show') return dests.find((d) => d.id === 'show')
  return dests.find((d) => d.id === 'loud' && d.speakerId === (prefs?.speaker_id || '')) || dests[0]
}
