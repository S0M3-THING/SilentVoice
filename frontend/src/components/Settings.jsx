import { useEffect, useState } from 'react'
import Modal from './Modal.jsx'
import YourVoice from './YourVoice.jsx'
import { listBrowserVoices, listMacVoices, speak } from '../lib/speech.js'

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
      <dl className="use-compare">
        <dt>I can’t use my voice</dt>
        <dd>
          Your voice isn’t working right now: after surgery, with a breathing tube, after a stroke, or with a
          condition that affects speech. SilentVoice speaks for you out loud, with shortcuts for the nurse, pain and
          breathing.
        </dd>
        <dt>I need to stay quiet</dt>
        <dd>
          Your voice works, but speaking would disturb people or be overheard: a library, an open office, a train,
          or when you need to share something private, like a password, PIN, account number or medical detail,
          without anyone nearby hearing it. Sentences are shown on screen instead of spoken, earlier lines blur, and
          nothing is saved.
        </dd>
      </dl>
    </div>
  )
}

function wordCheckNote(wc) {
  if (!wc) return ''
  if (!wc.available) return wc.reason
  if (wc.state === 'loading') return 'Getting the word check ready. The first time downloads the model (Gemma 4, about 3.6 GB).'
  if (wc.state === 'error') return `The word check didn’t load: ${wc.reason}`
  if (wc.state === 'ready') return `Ready (${wc.model}). Runs on this computer; nothing is sent anywhere.`
  return ''
}

function ReadingTab({ prefs, setPref, health }) {
  const wc = health?.word_check
  return (
    <div className="stack">
      <p className="muted">
        SilentVoice reads your lips only while you hold the button or the Space bar, so it never picks up
        movement you didn’t mean.
      </p>
      <Toggle
        label="Check guesses with a text model"
        hint="A text model on this computer picks the guess that makes the most sense, using what the other person just said (“coffee”, not “toffee”, after “Would you like a drink?”). When the reading is unclear, it rewrites it into clear sentences that look the same on the lips. Whenever it changes what the lips showed, SilentVoice asks you first."
        checked={prefs.word_check !== false}
        onChange={(v) => setPref('word_check', v)}
      />
      {prefs.word_check !== false && wordCheckNote(wc) && <p className="muted small">{wordCheckNote(wc)}</p>}
      <Toggle
        label="Keep my mouth in the middle"
        hint="The lip window follows your mouth, so you can shift around in bed or in your chair."
        checked={prefs.follow_lips !== false}
        onChange={(v) => setPref('follow_lips', v)}
      />
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

function VoiceTab({ prefs, setPref, voiceStatus, onVoiceChanged, speakerId }) {
  const [voices, setVoices] = useState([])

  useEffect(() => {
    // The Mac's voices when the server runs on a Mac (they can play on any speaker),
    // otherwise the browser's own voices.
    let alive = true
    const fromBrowser = () => alive && setVoices(listBrowserVoices().map((v) => ({ name: v.name })))
    listMacVoices().then((mac) => {
      if (!alive) return
      if (mac.length) setVoices(mac)
      else {
        fromBrowser()
        window.speechSynthesis?.addEventListener?.('voiceschanged', fromBrowser)
      }
    })
    return () => {
      alive = false
      window.speechSynthesis?.removeEventListener?.('voiceschanged', fromBrowser)
    }
  }, [])

  return (
    <div className="stack">
      <YourVoice prefs={{ ...prefs, speaker_id: speakerId }} setPref={setPref} voiceStatus={voiceStatus} onVoiceChanged={onVoiceChanged} />
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
        <span>Computer voice, used when your own voice isn’t set up</span>
        <select className="input" value={prefs.voice_name} onChange={(e) => setPref('voice_name', e.target.value)}>
          <option value="">Default</option>
          {voices.map((v) => (
            <option key={v.name} value={v.name}>{v.name}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Speed of the computer voice</span>
        <input type="range" min="0.6" max="1.4" step="0.05" value={prefs.voice_rate} onChange={(e) => setPref('voice_rate', Number(e.target.value))} />
      </label>
      <div>
        <button className="btn" onClick={() => speak('Hello, this is how I sound.', { ...prefs, use_my_voice: false, speaker_id: speakerId }, voiceStatus)}>
          Play the computer voice
        </button>
      </div>
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
          {tab === 'Reading' && <ReadingTab prefs={prefs} setPref={setPref} health={props.health} />}
          {tab === 'Voice' && <VoiceTab prefs={prefs} setPref={setPref} {...props} />}
          {tab === 'Privacy' && <PrivacyTab prefs={prefs} setPref={setPref} {...props} />}
          {tab === 'Phrases and names' && <PhrasesTab profile={profile} onSaveProfile={props.onSaveProfile} />}
          {tab === 'Display' && <DisplayTab prefs={prefs} setPref={setPref} />}
        </div>
      </div>
    </Modal>
  )
}
