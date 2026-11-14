import { useMemo, useState } from 'react'
import Modal from './Modal.jsx'

const ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
const COMMON =
  'i you the my me is am are can please need want help thank yes no not what when where why how doctor nurse family home water pain feel tired hot cold sleep eat drink bathroom phone today tomorrow now later okay good more again stop wait sorry love seat outside message call minute'.split(
    ' ',
  )

const TABS = [
  ['spell', 'Spell'],
  ['phrases', 'Phrases'],
  ['yesno', 'Yes / No'],
]

function Spell({ phrases, names, onSay }) {
  const [text, setText] = useState('')
  const vocab = useMemo(() => {
    const words = new Set(COMMON)
    for (const p of phrases) for (const w of p.text.toLowerCase().match(/[a-z']+/g) || []) words.add(w)
    for (const n of names) words.add(n)
    return [...words]
  }, [phrases, names])

  const parts = text.split(' ')
  const last = parts[parts.length - 1].toLowerCase()
  const words = last ? vocab.filter((w) => w.toLowerCase().startsWith(last) && w.toLowerCase() !== last).slice(0, 4) : []
  const whole =
    text.trim().length >= 2
      ? phrases.filter((p) => p.text.toLowerCase().startsWith(text.trim().toLowerCase())).slice(0, 2)
      : []
  const add = (ch) => setText((t) => t + (t === '' ? ch.toUpperCase() : ch))
  const complete = (w) => setText(parts.slice(0, -1).concat(w).join(' ') + ' ')

  return (
    <div className="spell">
      <output className="spell-out" aria-live="polite">
        {text || <span className="muted">Tap letters to spell it</span>}
        <span className="caret" aria-hidden="true" />
      </output>
      <div className="suggest">
        {whole.map((p) => (
          <button key={p.text} className="suggest-phrase" onClick={() => onSay(p.text, 'phrase')}>
            {p.text}
          </button>
        ))}
        {words.map((w) => (
          <button key={w} className="suggest-word" onClick={() => complete(w)}>
            {w}
          </button>
        ))}
      </div>
      <div className="keys">
        {ROWS.map((r) => (
          <div className="key-row" key={r}>
            {r.split('').map((k) => (
              <button key={k} className="key" onClick={() => add(k)}>
                {k}
              </button>
            ))}
          </div>
        ))}
        <div className="key-row">
          <button className="key key-wide" onClick={() => setText((t) => t.slice(0, -1))}>Delete</button>
          <button className="key key-space" onClick={() => setText((t) => t + ' ')}>space</button>
          <button className="key key-wide" onClick={() => add('?')}>?</button>
          <button className="key key-wide" onClick={() => setText('')}>Clear</button>
        </div>
      </div>
      <button className="btn btn-primary btn-lg btn-block" disabled={!text.trim()} onClick={() => onSay(text.trim(), 'spell')}>
        Use this sentence
      </button>
    </div>
  )
}

function Phrases({ phrases, onSay }) {
  const used = phrases.filter((p) => p.uses > 0).sort((a, b) => b.uses - a.uses).slice(0, 6)
  const groups = []
  if (used.length) groups.push(['Most used', used])
  const cats = [...new Set(phrases.map((p) => p.category || 'Mine'))]
  for (const c of cats) groups.push([c, phrases.filter((p) => (p.category || 'Mine') === c)])
  return (
    <div className="phrase-groups">
      {groups.map(([name, items]) => (
        <section key={name} className="phrase-group">
          <h3>{name}</h3>
          {items.map((p) => (
            <button key={name + p.text} className="guess" onClick={() => onSay(p.text, 'phrase')}>
              {p.text}
            </button>
          ))}
        </section>
      ))}
    </div>
  )
}

function YesNo({ onSay }) {
  return (
    <div className="yesno">
      <button className="yn yn-yes" onClick={() => onSay('Yes.', 'yesno')}>Yes</button>
      <button className="yn yn-no" onClick={() => onSay('No.', 'yesno')}>No</button>
      <button className="yn yn-soft" onClick={() => onSay('Maybe.', 'yesno')}>Maybe</button>
      <button className="yn yn-soft" onClick={() => onSay("I don't know.", 'yesno')}>I don’t know</button>
    </div>
  )
}

/** "None of these": never leave someone stuck when lip reading gets it wrong. */
export default function Board({ initialTab = 'spell', phrases, names, onSay, onClose }) {
  const [tab, setTab] = useState(initialTab)
  return (
    <Modal title="Say it another way" onClose={onClose} wide labelledBy="board-title">
      <div className="seg seg-lg" role="tablist" aria-label="Ways to say it">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} aria-pressed={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      <div className="board-body">
        {tab === 'spell' && <Spell phrases={phrases} names={names} onSay={onSay} />}
        {tab === 'phrases' && <Phrases phrases={phrases} onSay={onSay} />}
        {tab === 'yesno' && <YesNo onSay={onSay} />}
      </div>
    </Modal>
  )
}
