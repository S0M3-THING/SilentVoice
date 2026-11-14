import { useState } from 'react'
import Modal from './Modal.jsx'

const PLACES = ['Head', 'Throat', 'Chest', 'Stomach', 'Back', 'Arms', 'Legs', 'Where the tube is']

export default function PainScale({ onSay, onClose }) {
  const [score, setScore] = useState(null)
  const [place, setPlace] = useState('')

  const where = place ? (place === 'Where the tube is' ? ' in my neck, where the tube is' : ` in my ${place.toLowerCase()}`) : ''
  const sentence = score == null ? 'I am in pain.' : `My pain is ${score} out of 10${where}.`

  return (
    <Modal title="How bad is the pain?" onClose={onClose} wide labelledBy="pain-title">
      <div className="pain-scale" role="radiogroup" aria-label="Pain from 0 to 10">
        {Array.from({ length: 11 }, (_, n) => (
          <button
            key={n}
            role="radio"
            aria-checked={score === n}
            className="pain-n"
            style={{ '--heat': n / 10 }}
            onClick={() => setScore(n)}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="pain-ends" aria-hidden="true">
        <span>No pain</span>
        <span>Worst pain</span>
      </div>
      <fieldset className="choice">
        <legend>Where? (optional)</legend>
        <div className="chips">
          {PLACES.map((p) => (
            <button key={p} className="chip" aria-pressed={place === p} onClick={() => setPlace(place === p ? '' : p)}>
              {p}
            </button>
          ))}
        </div>
      </fieldset>
      <button className="btn btn-urgent btn-lg btn-block" onClick={() => onSay(sentence)}>
        Say “{sentence}”
      </button>
    </Modal>
  )
}
