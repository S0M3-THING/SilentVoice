import { useEffect, useState } from 'react'
import Modal from './Modal.jsx'
import { api } from '../lib/api.js'
import { listSystemVoices, speak } from '../lib/speech.js'

const TABS = ['How you use it', 'Reading', 'Voice', 'Privacy', 'Phrases and names', 'Display']

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={Boolean(checked)} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden="true" />
      <span className="toggle-copy">
        <span className="toggle-label">{label}</span>
        {hint && <span className="muted small">{hint}</span>}
      </span>
    </label>
  )
}

function Choice({ label, value, options, onChange }) {
  return (
    <fieldset className="choice">
      <legend>{label}</legend>
      <div className="seg">
        {options.map(([v, text]) => (
          <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function UseTab({ prefs, onSetup }) {
  return (
    <div className="stack">
      <p className="muted">
        This only changes your starting settings: shortcuts, where sentences go, privacy and confirmation. Your
        phrases and names stay.
      </p>
      <Choice
        label="I’m using SilentVoice because"
        value={prefs.use}
        onChange={onSetup}
        options={[
          ['care', 'I can’t use my voice'],
          ['quiet', 'I need to stay quiet'],
        ]}
      />
    </div>
  )
}

function ReadingTab({ prefs, setPref }) {
  return (
    <div className="stack">
      <Choice
        label="Start reading"
        value={prefs.capture_mode}
        onChange={(v) => setPref('capture_mode', v)}
        options={[
          ['auto', 'When I move'],
          ['tap', 'Tap to start and stop'],
          ['hold', 'Press and hold'],
        ]}
      />
      <label className="field">
        <span>How easily “When I move” starts</span>
        <input type="range" min="0" max="1" step="0.05" value={prefs.sensitivity} onChange={(e) => setPref('sensitivity', Number(e.target.value))} />
        <span className="muted small">Raise it if small movements aren’t noticed. Lower it if it starts on its own.</span>
      </label>
      <Choice
        label="Lip reading"
        value={prefs.recognition_mode}
        onChange={(v) => setPref('recognition_mode', v)}
        options={[
          ['fast', 'Faster'],
          ['accurate', 'More accurate, slower'],
        ]}
      />
      <Toggle
        label="Only use my saved phrases"
        hint="The most reliable option when you’re tired or unwell. SilentVoice picks the closest saved phrase."
        checked={prefs.phrases_only}
        onChange={(v) => setPref('phrases_only', v)}
      />
      <Toggle label="Brighten dim video" checked={prefs.low_light_boost} onChange={(v) => setPref('low_light_boost', v)} />
      <Toggle label="My camera image is already flipped" checked={prefs.unmirror} onChange={(v) => setPref('unmirror', v)} />
    </div>
  )
}

function VoiceTab({ prefs, setPref, voiceStatus, onVoiceChanged, secrets, onSaveSecrets }) {
  const [voices, setVoices] = useState(listSystemVoices())
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [key, setKey] = useState('')

  useEffect(() => {
    const update = () => setVoices(listSystemVoices())
    window.speechSynthesis?.addEventListener?.('voiceschanged', update)
    return () => window.speechSynthesis?.removeEventListener?.('voiceschanged', update)
  }, [])

  const clone = async () => {
    setBusy(true)
    setMsg('')
    try {
      onVoiceChanged(await api.cloneVoice(files, 'My SilentVoice'))
      setPref('use_my_voice', true)
      setMsg('Your voice is ready.')
      setFiles([])
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <Choice
        label="Before a sentence goes anywhere"
        value={prefs.confirm_policy}
        onChange={(v) => setPref('confirm_policy', v)}
        options={[
          ['unsure', 'Ask me when unsure'],
          ['always', 'Always ask me'],
          ['never', 'Never ask'],
        ]}
      />
      <label className="field">
        <span>Device voice</span>
        <select className="input" value={prefs.voice_name} onChange={(e) => setPref('voice_name', e.target.value)}>
          <option value="">Default</option>
          {voices.map((v) => (
            <option key={v.name} value={v.name}>{v.name}</option>
          ))}
        </select>
      </label>
      <div className="pair">
        <label className="field">
          <span>Speed</span>
          <input type="range" min="0.6" max="1.4" step="0.05" value={prefs.voice_rate} onChange={(e) => setPref('voice_rate', Number(e.target.value))} />
        </label>
        <label className="field">
          <span>Pitch</span>
          <input type="range" min="0.6" max="1.4" step="0.05" value={prefs.voice_pitch} onChange={(e) => setPref('voice_pitch', Number(e.target.value))} />
        </label>
      </div>
      <div>
        <button className="btn" onClick={() => speak('Hello, this is how I sound.', prefs, voiceStatus)}>Play a sample</button>
      </div>

      <section className="sub">
        <h3>Speak in your own voice</h3>
        <p className="muted small">
          Upload about a minute of old recordings of your voice, such as voicemails or videos. SilentVoice makes a copy of
          your voice with ElevenLabs. Sentences you’ve said once keep working offline.
        </p>
        {!secrets.elevenlabs_api_key ? (
          <form className="inline" onSubmit={(e) => { e.preventDefault(); onSaveSecrets({ elevenlabs_api_key: key }); setKey('') }}>
            <label className="sr-only" htmlFor="el-key">ElevenLabs API key</label>
            <input id="el-key" className="input" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="ElevenLabs API key" />
            <button className="btn" disabled={!key.trim()}>Save key</button>
          </form>
        ) : voiceStatus?.has_voice ? (
          <>
            <Toggle label="Use my voice" checked={prefs.use_my_voice} onChange={(v) => setPref('use_my_voice', v)} />
            <div>
              <button className="btn btn-danger" onClick={async () => onVoiceChanged(await api.deleteVoice())}>Delete my voice copy</button>
            </div>
          </>
        ) : (
          <div className="stack">
            <label className="file-pick">
              <span>{files.length ? `${files.length} recording${files.length > 1 ? 's' : ''} chosen` : 'Choose recordings'}</span>
              <input type="file" accept="audio/*,video/*" multiple onChange={(e) => setFiles([...e.target.files])} />
            </label>
            <div>
              <button className="btn btn-primary" disabled={!files.length || busy} onClick={clone}>
                {busy ? 'Making your voice…' : 'Make my voice'}
              </button>
            </div>
          </div>
        )}
        {msg && <p className="small">{msg}</p>}
      </section>
    </div>
  )
}

function PrivacyTab({ prefs, setPref, secrets, onSaveSecrets, onClearLog, onReset }) {
  const [key, setKey] = useState('')
  return (
    <div className="stack">
      <p className="muted">
        Your camera is read on this computer and the video is deleted straight away. It is never saved or uploaded.
      </p>
      <Toggle
        label="Blur earlier lines"
        hint="People walking past can’t read them. Point at or tap a line to see it."
        checked={prefs.privacy_blur}
        onChange={(v) => setPref('privacy_blur', v)}
      />
      <Toggle
        label="Keep a conversation history"
        hint="Saved only on this computer, so you or your care team can export it."
        checked={prefs.keep_history}
        onChange={(v) => setPref('keep_history', v)}
      />
      <Choice
        label="Clear the screen when I’m idle"
        value={String(prefs.auto_clear_minutes)}
        onChange={(v) => setPref('auto_clear_minutes', Number(v))}
        options={[
          ['0', 'Never'],
          ['2', 'After 2 minutes'],
          ['10', 'After 10 minutes'],
        ]}
      />
      <section className="sub">
        <h3>Smarter correction (optional)</h3>
        <p className="muted small">
          With a Groq key, an AI model uses the conversation to fix words that look the same on the lips, like
          “toffee” and “coffee”. Only the text guesses are sent, never video. Without a key everything stays offline.
        </p>
        {secrets.groq_api_key ? (
          <div className="inline">
            <span className="ok">On</span>
            <button className="btn btn-danger" onClick={() => onSaveSecrets({ groq_api_key: '' })}>Remove key</button>
          </div>
        ) : (
          <form className="inline" onSubmit={(e) => { e.preventDefault(); onSaveSecrets({ groq_api_key: key }); setKey('') }}>
            <label className="sr-only" htmlFor="groq-key">Groq API key</label>
            <input id="groq-key" className="input" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Groq API key" />
            <button className="btn" disabled={!key.trim()}>Turn on</button>
          </form>
        )}
      </section>
      <div className="inline">
        <button className="btn btn-danger" onClick={onClearLog}>Delete history</button>
        <button className="btn btn-danger" onClick={onReset}>Reset all settings</button>
      </div>
    </div>
  )
}

function PhrasesTab({ profile, onSaveProfile }) {
  const [text, setText] = useState('')
  const [category, setCategory] = useState('Mine')
  const [names, setNames] = useState((profile.names || []).join(', '))
  const cats = [...new Set(['Mine', ...profile.phrases.map((p) => p.category || 'Mine')])]
  const buttons = profile.quick_buttons || []
  const isShortcut = (t) => buttons.some((b) => b.text === t)
  const addShortcut = (t) => {
    const label = t.replace(/[.?!]$/, '')
    onSaveProfile({
      quick_buttons: [...buttons, { id: `s${Date.now()}`, label: label.length > 24 ? label.slice(0, 22) + '…' : label, text: t, urgent: false }],
    })
  }

  return (
    <div className="stack">
      <section className="sub">
        <h3>Shortcuts</h3>
        <p className="muted small">These sit at the top of the screen. Add more from your phrases below.</p>
        <ul className="phrase-admin">
          {buttons.map((b) => (
            <li key={b.id}>
              <span>{b.label}</span>
              <span className="muted small">{b.urgent ? 'Urgent' : ''}</span>
              <button className="text-btn" onClick={() => onSaveProfile({ quick_buttons: buttons.filter((x) => x.id !== b.id) })}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      </section>
      <label className="field">
        <span>Names SilentVoice should know</span>
        <input
          className="input"
          value={names}
          onChange={(e) => setNames(e.target.value)}
          onBlur={() => onSaveProfile({ names: names.split(',').map((n) => n.trim()).filter(Boolean) })}
          placeholder="Family, friends, nurses, separated by commas"
        />
        <span className="muted small">Names are hard to lip-read, so listing them helps a lot.</span>
      </label>
      <form
        className="inline"
        onSubmit={(e) => {
          e.preventDefault()
          if (!text.trim()) return
          onSaveProfile({ phrases: [...profile.phrases, { text: text.trim(), category, uses: 0 }] })
          setText('')
        }}
      >
        <label className="sr-only" htmlFor="new-phrase">New phrase</label>
        <input id="new-phrase" className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="A sentence you say often" />
        <label className="sr-only" htmlFor="new-cat">Group</label>
        <select id="new-cat" className="input input-auto" value={category} onChange={(e) => setCategory(e.target.value)}>
          {cats.map((c) => <option key={c}>{c}</option>)}
        </select>
        <button className="btn" disabled={!text.trim()}>Add</button>
      </form>
      <ul className="phrase-admin">
        {profile.phrases.map((p) => (
          <li key={p.text}>
            <span>{p.text}</span>
            <span className="muted small">{p.category}{p.uses ? `, used ${p.uses}×` : ''}</span>
            <span className="row-actions">
              {!isShortcut(p.text) && (
                <button className="text-btn" onClick={() => addShortcut(p.text)}>Make shortcut</button>
              )}
              <button className="text-btn" onClick={() => onSaveProfile({ phrases: profile.phrases.filter((x) => x.text !== p.text) })}>
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DisplayTab({ prefs, setPref }) {
  return (
    <div className="stack">
      <label className="field">
        <span>Text size</span>
        <input type="range" min="0.9" max="1.6" step="0.1" value={prefs.text_scale} onChange={(e) => setPref('text_scale', Number(e.target.value))} />
      </label>
      <Toggle label="High contrast" hint="Yellow on black. Easier to read, and gentler at night." checked={prefs.high_contrast} onChange={(v) => setPref('high_contrast', v)} />
      <Toggle label="Beep before urgent sentences" hint="For things like “I can’t breathe”, so someone looks up." checked={prefs.alert_sound} onChange={(v) => setPref('alert_sound', v)} />
    </div>
  )
}

export default function Settings(props) {
  const { profile, onPrefs, onClose, initialTab } = props
  const [tab, setTab] = useState(initialTab || TABS[0])
  const prefs = profile.preferences
  const setPref = (k, v) => onPrefs({ [k]: v })

  return (
    <Modal title="Settings" onClose={onClose} wide labelledBy="settings-title">
      <div className="settings">
        <div className="settings-tabs" role="tablist" aria-orientation="vertical">
          {TABS.map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        <div className="settings-panel">
          {tab === 'How you use it' && <UseTab prefs={prefs} onSetup={props.onSetup} />}
          {tab === 'Reading' && <ReadingTab prefs={prefs} setPref={setPref} />}
          {tab === 'Voice' && <VoiceTab prefs={prefs} setPref={setPref} {...props} />}
          {tab === 'Privacy' && <PrivacyTab prefs={prefs} setPref={setPref} {...props} />}
          {tab === 'Phrases and names' && <PhrasesTab profile={profile} onSaveProfile={props.onSaveProfile} />}
          {tab === 'Display' && <DisplayTab prefs={prefs} setPref={setPref} />}
        </div>
      </div>
    </Modal>
  )
}
