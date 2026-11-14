import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './lib/api.js'
import { playAlert, speak } from './lib/speech.js'
import { useCamera, useCapture } from './lib/useCapture.js'
import { usePartnerMic } from './lib/usePartnerMic.js'
import { currentDestination, destinations, useSpeakers } from './lib/destinations.js'
import { useMouthTracker } from './lib/useMouthTracker.js'
import Shortcuts from './components/Shortcuts.jsx'
import CameraPanel from './components/CameraPanel.jsx'
import Sentence from './components/Sentence.jsx'
import SidePanel from './components/SidePanel.jsx'
import PartnerPanel from './components/PartnerPanel.jsx'
import Board from './components/Board.jsx'
import PainScale from './components/PainScale.jsx'
import PartnerView from './components/PartnerView.jsx'
import Settings from './components/Settings.jsx'
import Setup from './components/Setup.jsx'

const URGENT_RE = /can'?t breathe|cannot breathe|suction|nurse|in pain|pain is ([7-9]|10)\b|\bhelp\b|choking|bleeding|emergency/i

const DONE_NOTE = {
  loud: 'Said out loud.',
  show: 'Shown on screen.',
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [profile, setProfile] = useState(null)
  const [secrets, setSecrets] = useState({})
  const [voiceStatus, setVoiceStatus] = useState(null)
  const [entries, setEntries] = useState([])
  const [current, setCurrent] = useState(null)
  const [reading, setReading] = useState(false)
  const [readError, setReadError] = useState('')
  const [partnerText, setPartnerText] = useState('')
  const [modal, setModal] = useState(null)
  const [toast, setToast] = useState('')
  const [setupBusy, setSetupBusy] = useState(false)
  const lastActivity = useRef(Date.now())

  const prefs = profile?.preferences
  const modelState = health ? health.model_state : 'offline'
  const touch = () => (lastActivity.current = Date.now())

  // ---------------------------------------------------------------- loading
  useEffect(() => {
    let alive = true
    let timer
    const poll = async () => {
      try {
        const h = await api.health()
        if (!alive) return
        setHealth(h)
        setVoiceStatus(h.voice)
        timer = setTimeout(poll, h.model_state === 'ready' ? 20000 : 3000)
      } catch {
        if (!alive) return
        setHealth(null)
        timer = setTimeout(poll, 3000)
      }
    }
    poll()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    if (!health || profile) return
    Promise.all([api.profile(), api.secrets()])
      .then(async ([p, s]) => {
        setProfile(p)
        setSecrets(s)
        if (p.preferences.keep_history) setEntries((await api.log()).entries)
      })
      .catch((e) => setToast(e.message))
  }, [health, profile])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 4000)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    if (!prefs) return
    document.documentElement.style.setProperty('--scale', prefs.text_scale || 1)
    document.documentElement.dataset.contrast = prefs.high_contrast ? 'high' : 'normal'
  }, [prefs])

  // Clear the screen after a quiet spell, if asked to.
  useEffect(() => {
    const minutes = prefs?.auto_clear_minutes || 0
    if (!minutes) return
    const timer = setInterval(() => {
      if (Date.now() - lastActivity.current < minutes * 60000) return
      setCurrent(null)
      setReadError('')
      setPartnerText('')
      if (!prefs.keep_history) setEntries([])
    }, 10000)
    return () => clearInterval(timer)
  }, [prefs])

  // ---------------------------------------------------------------- actions
  const savePrefs = useCallback((patch) => {
    setProfile((p) => ({ ...p, preferences: { ...p.preferences, ...patch } }))
    api.saveProfile({ preferences: patch }).catch((e) => setToast(e.message))
  }, [])

  const saveProfile = useCallback(async (patch) => {
    try {
      setProfile(await api.saveProfile(patch))
    } catch (e) {
      setToast(e.message)
    }
  }, [])

  const runSetup = useCallback(async (use) => {
    setSetupBusy(true)
    try {
      const p = await api.setup(use)
      setProfile(p)
      if (!p.preferences.keep_history) setEntries([])
    } catch (e) {
      setToast(e.message)
    } finally {
      setSetupBusy(false)
    }
  }, [])

  const addEntry = useCallback(
    (entry) => {
      const local = { ...entry, id: `l${Date.now()}${Math.random().toString(16).slice(2, 6)}`, ts: Date.now() / 1000 }
      setEntries((l) => [...l, local].slice(-300))
      if (prefs?.keep_history) api.addLog(entry).catch(() => {})
    },
    [prefs],
  )

  const speakers = useSpeakers()
  const dests = useMemo(() => destinations(speakers, voiceStatus), [speakers, voiceStatus])
  const dest = currentDestination(dests, prefs)
  const destId = dest.id
  // The speaker to use: the chosen one, or (when showing on screen) the first one for urgent lines.
  const speakerId = (dest.id === 'loud' ? dest : dests[0]).speakerId || ''

  const deliver = useCallback(
    async (text, source, extra = {}) => {
      if (!text) return
      touch()
      const urgent = URGENT_RE.test(text)
      const target = extra.forceLoud ? 'loud' : destId
      setReadError('')
      setCurrent((c) => ({
        ...(source === 'lipread' && c ? c : { alternatives: [] }),
        text,
        source,
        urgent,
        done: true,
        needsConfirm: false,
        doneNote: DONE_NOTE[target],
        ...extra,
      }))
      addEntry({ speaker: 'user', text, source, confidence: extra.confidence ?? null, raw: extra.raw ?? null })

      if (target === 'loud') {
        if (urgent && prefs?.alert_sound) {
          playAlert(speakerId)
          await new Promise((r) => setTimeout(r, 750))
        }
        speak(text, { ...prefs, speaker_id: speakerId }, voiceStatus)
      } else {
        setModal({ type: 'show', text })
      }
    },
    [addEntry, destId, prefs, voiceStatus, speakerId],
  )

  const handleClip = useCallback(
    async (blob, mimeType) => {
      touch()
      setReading(true)
      setReadError('')
      try {
        const history = entries.slice(-6).map((e) => ({ speaker: e.speaker === 'user' ? 'me' : 'them', text: e.text }))
        const data = await api.lipread({ blob, mimeType, prefs, partnerText, history })
        const r = data.result
        if (!r.text) throw new Error('No words came through. Try again a little slower, or spell it.')
        const next = {
          text: r.text,
          label: r.confidence_label,
          confidence: r.confidence,
          alternatives: r.alternatives,
          repaired: r.repaired,
          raw: data.vsr_candidates?.[0]?.text,
          urgent: r.urgent,
          needsConfirm: r.needs_confirmation,
          done: false,
          source: 'lipread',
        }
        setCurrent(next)
        if (!r.needs_confirmation && destId === 'loud') {
          deliver(r.text, 'lipread', { confidence: r.confidence, raw: next.raw, label: r.confidence_label })
        }
      } catch (e) {
        setReadError(e.message)
      } finally {
        setReading(false)
      }
    },
    [entries, prefs, partnerText, destId, deliver],
  )

  const onPartner = useCallback(
    (text) => {
      touch()
      setPartnerText(text)
      addEntry({ speaker: 'partner', text, source: 'mic' })
    },
    [addEntry],
  )

  const pressShortcut = useCallback(
    (b) => (b.action === 'pain_scale' ? setModal({ type: 'pain' }) : deliver(b.text, 'quick', { forceLoud: Boolean(b.urgent) })),
    [deliver],
  )

  // ---------------------------------------------------------------- capture
  const { videoRef, stream, error: cameraError } = useCamera()
  const awaitingConfirm = Boolean(current?.needsConfirm && !current?.done)
  const mode = prefs?.capture_mode === 'hold' ? 'hold' : 'tap'
  const modalOpen = Boolean(modal)
  const captureEnabled = modelState === 'ready' && !reading && !modalOpen
  const following = prefs ? prefs.follow_lips !== false : false
  const tracker = useMouthTracker({ videoRef, stream, enabled: following && !reading && !modalOpen })

  const capture = useCapture({
    videoRef,
    stream,
    enabled: captureEnabled,
    onClip: handleClip,
    mouthRef: tracker.mouthRef,
  })
  const mic = usePartnerMic({ enabled: Boolean(prefs?.partner_mic), onFinal: onPartner })

  const captureRef = useRef(capture)
  captureRef.current = capture
  useEffect(() => {
    const typing = () => ['input', 'textarea', 'select', 'button'].includes(document.activeElement?.tagName?.toLowerCase())
    const down = (e) => {
      if (e.code !== 'Space' || e.repeat || modalOpen || typing()) return
      e.preventDefault()
      if (mode === 'hold') captureRef.current.start()
      else captureRef.current.toggle()
    }
    const up = (e) => {
      if (e.code !== 'Space' || modalOpen || typing() || mode !== 'hold') return
      e.preventDefault()
      captureRef.current.stop()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [mode, modalOpen])

  const lastSaid = current?.text || [...entries].reverse().find((e) => e.speaker === 'user')?.text || ''

  // ---------------------------------------------------------------- render
  if (!profile) {
    return (
      <main className="boot">
        <p className="wordmark">SilentVoice</p>
        <p className="muted">
          {health === null ? 'Waiting for the SilentVoice server. Start it with ./start.sh, then reload.' : 'Loading…'}
        </p>
      </main>
    )
  }

  if (!prefs.use) return <Setup onDone={runSetup} busy={setupBusy} />

  return (
    <div className="app">
      <header className="top">
        <p className="wordmark">SilentVoice</p>
        <p className="top-note">
          {modelState === 'ready' ? 'Your camera is read on this computer. Video is never saved.' : 'Lip reading is starting…'}
        </p>
        <div className="top-actions">
          <button className="btn" onClick={() => setModal({ type: 'settings' })}>Settings</button>
        </div>
      </header>

      <Shortcuts
        buttons={profile.quick_buttons}
        onPress={pressShortcut}
        onEdit={() => setModal({ type: 'settings', tab: 'Phrases and names' })}
      />

      <main className="layout">
        <CameraPanel
          videoRef={videoRef}
          cameraError={cameraError}
          capture={capture}
          mode={mode}
          onModeChange={(m) => savePrefs({ capture_mode: m })}
          busy={reading ? 'reading' : awaitingConfirm ? 'confirm' : null}
          modelState={modelState}
          unmirror={prefs.unmirror}
          mouth={tracker.mouth}
          following={following && !tracker.unavailable}
        />

        <div className="center">
        <PartnerPanel
          partner={{ text: partnerText, interim: mic.interim, micOn: Boolean(prefs.partner_mic), listening: mic.listening, error: mic.error }}
          onPartnerTyped={onPartner}
          onToggleMic={() => savePrefs({ partner_mic: !prefs.partner_mic })}
        />

        <Sentence
          current={current}
          reading={reading}
          error={readError}
          dest={dest}
          onDeliver={(t) => deliver(t, current?.source || 'lipread', { confidence: current?.confidence, raw: current?.raw, label: current?.label })}
          onPickAlt={(a) => deliver(a, 'lipread', { confidence: null, raw: current?.raw, label: null, repaired: false })}
          onFallback={(tab) => setModal({ type: 'board', tab })}
        />
        </div>

        <SidePanel
          dests={dests}
          destKey={dest.key}
          onDest={(d) => savePrefs(d.id === 'loud' ? { destination: 'loud', speaker_id: d.speakerId } : { destination: 'show' })}
          entries={entries}
          blur={prefs.privacy_blur}
          keepHistory={prefs.keep_history}
          onRepeat={(t) => deliver(t, 'repeat')}
        />
      </main>

      {modal?.type === 'board' && (
        <Board
          initialTab={modal.tab}
          phrases={profile.phrases}
          names={profile.names || []}
          onClose={() => setModal(null)}
          onSay={(text, source) => {
            setModal(null)
            deliver(text, source)
          }}
        />
      )}
      {modal?.type === 'pain' && (
        <PainScale
          onClose={() => setModal(null)}
          onSay={(text) => {
            setModal(null)
            deliver(text, 'quick', { forceLoud: true })
          }}
        />
      )}
      {modal?.type === 'show' && <PartnerView text={modal.text || lastSaid} onClose={() => setModal(null)} />}
      {modal?.type === 'settings' && (
        <Settings
          initialTab={modal.tab}
          profile={profile}
          onPrefs={savePrefs}
          onSaveProfile={saveProfile}
          onSetup={runSetup}
          secrets={secrets}
          onSaveSecrets={async (v) => {
            try {
              setSecrets(await api.saveSecrets(v))
              setHealth(await api.health())
            } catch (e) {
              setToast(e.message)
            }
          }}
          voiceStatus={voiceStatus}
          onVoiceChanged={setVoiceStatus}
          health={health}
          speakerId={speakerId}
          onClearLog={async () => {
            await api.clearLog()
            setEntries([])
          }}
          onReset={async () => setProfile(await api.resetProfile())}
          onClose={() => setModal(null)}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  )
}
