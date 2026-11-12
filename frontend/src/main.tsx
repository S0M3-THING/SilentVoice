import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Candidate = { text: string; visual_score: number }

const demoCandidates: Candidate[] = [
  { text: 'Coffee, please.', visual_score: 0.71 },
  { text: 'Tea, please.', visual_score: 0.69 },
  { text: 'Yes, please.', visual_score: 0.59 },
]
const apiUrl = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

function App() {
  const [context, setContext] = useState('Would you like tea?')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  async function rankDemo() {
    setPending(true)
    setError('')
    setCandidates([])
    try {
      const response = await fetch(`${apiUrl}/api/rerank`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidates: demoCandidates, partner_text: context }),
      })
      if (!response.ok) throw new Error('Ranking request failed')
      setCandidates(await response.json())
    } catch {
      setError('Could not rank suggestions. Check that the FastAPI server is running.')
    } finally {
      setPending(false)
    }
  }

  function speak() {
    setError('')
    if (!('speechSynthesis' in window)) {
      setError('Speech playback is unavailable in this browser.')
      return
    }
    const utterance = new SpeechSynthesisUtterance(message.trim())
    utterance.onerror = ({ error }) => {
      if (error !== 'canceled' && error !== 'interrupted') {
        setError('Speech playback failed. Try again or show your message on screen.')
      }
    }
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utterance)
  }

  return (
    <main>
      <h1>SilentVoice</h1>
      <p>Prototype using sample lip-reading candidates and your browser’s speech voice.</p>
      <label htmlFor="context">Conversation partner’s words</label>
      <input id="context" value={context} maxLength={1000} onChange={event => setContext(event.target.value)} />
      <button type="button" onClick={rankDemo} disabled={pending}>
        {pending ? 'Ranking…' : 'Rank sample replies'}
      </button>
      <div aria-live="polite">
        {candidates.map(candidate => (
          <button type="button" key={candidate.text} onClick={() => setMessage(candidate.text)}>
            {candidate.text}
          </button>
        ))}
      </div>
      <label htmlFor="message">Your message</label>
      <textarea id="message" value={message} onChange={event => setMessage(event.target.value)} rows={3} />
      <button type="button" onClick={speak} disabled={!message.trim()}>Speak message</button>
      {error && <p role="alert">{error}</p>}
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
