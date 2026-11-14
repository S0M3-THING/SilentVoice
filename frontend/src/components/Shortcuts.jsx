/** One-tap sentences. Urgent ones are red so a nurse can spot them; everything else stays quiet. */
export default function Shortcuts({ buttons, onPress, onEdit }) {
  return (
    <nav className="shortcuts" aria-label="Shortcuts">
      {buttons.map((b) => (
        <button key={b.id} className={`shortcut ${b.urgent ? 'is-urgent' : ''}`} onClick={() => onPress(b)} title={b.text}>
          {b.label}
        </button>
      ))}
      <button className="shortcut shortcut-edit" onClick={onEdit}>
        Edit shortcuts
      </button>
    </nav>
  )
}
