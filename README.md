# SilentVoice

SilentVoice is a web app that reads your lips through a webcam, for anyone who can't or shouldn't make sound:
a patient after a tracheostomy or laryngectomy, someone with vocal cord paralysis or early ALS, or a student in
a library who just needs to stay quiet.

Everyone uses the same screen: **mouth it, check it, choose where it goes**. A sentence can go
**out loud** (in your own voice if you like), be **copied**, **shared** through the device's share menu, or shown
**on screen** in large text. A single first-run question ("I can't use my voice right now" or "I can talk, but
need to stay quiet") picks sensible starting settings: shortcuts, default destination, confirmation, privacy blur
and history. Everything can be changed later.

Everything runs on your computer. The camera video is read and deleted straight away. It is never saved or uploaded.

## Why it's built this way

The closest earlier product, SRAVI (an ICU lip-reading app), reached only 22–35% accuracy in a 2023–24
hospital study. Patients found it hard to use, and it depended on hospital Wi-Fi. Its maker, Liopa, has since been liquidated.
Patients who suddenly lose their voice most often need to talk about pain, breathing/suction, the bathroom, and their
treatment plans, and many report anxiety and frustration when they can't. SilentVoice is designed around those lessons:

| Problem with earlier tools | What SilentVoice does |
| --- | --- |
| Lip reading is often wrong | Shows 3 guesses and **None of these**, which opens a phrase board, spelling keyboard or yes/no. You're never stuck. |
| Wrong guesses put words in your mouth | Asks **"Is this what you said?"** when unsure, flags AI-corrected words, and never asserts an urgent phrase from a weak match. |
| Needed Wi-Fi / a server | Lip reading and phrase matching run **offline** on the laptop. AI correction is optional. |
| Nobody nearby should see or hear it | In quiet setups nothing is spoken or saved, earlier lines blur, the screen clears after 2 minutes, and the camera shows only your mouth (the "lip slot"). |
| Hard to use when very unwell | **Hands-free** mode starts when your lips move and stops when you pause. Tap and hold modes are also available, plus one-tap urgent buttons. |
| Urgent needs were slow | An always-visible bar: Nurse, Pain (0–10 scale + body area), Can't breathe, Suction, Bathroom, Water, Yes, No. Urgent messages beep first. |
| Generic robot voice | Speak in **your own voice** (from ~1 min of old recordings via ElevenLabs), cached so common phrases work offline. |
| Didn't know the context | Listens to the **partner's** question (or lets them type it) and uses it to pick the right answer. |
| Small screens, hard to read | Hyperlegible type, adjustable text size, high-contrast mode, and **Show large** with a flip for the person across the bed. |
| Nothing for the care team | A conversation log with **export** (TXT/CSV) for clinicians and family. |
| Same for everyone | Personal phrases, names it should know, and it learns which phrases you use most. **Only my saved phrases** mode gives the most reliable results. |

## Project structure

```
SilentVoice/
├── backend/                 FastAPI server (Python 3.11)
│   ├── app.py               API routes; model loads in the background
│   ├── vsr_service.py       Lip reading (Auto-AVSR via Chaplin), top-10 guesses
│   ├── context_selector.py  Picks the final sentence (optional Groq LLM, offline fallback)
│   ├── phrases.py           Phrase bank, look-alike-letter matcher, urgent detection
│   ├── store.py             Local profile, keys and conversation log (backend/data/)
│   ├── voice.py             Own-voice cloning + cached speech (ElevenLabs)
│   ├── tests/               pytest suite (runs without the model)
│   └── vendor/chaplin/      Lip-reading model code (cloned by setup.sh, git-ignored)
├── frontend/                React + Vite app
│   ├── src/App.jsx          Main screen
│   ├── src/components/      Setup, shortcuts, lip slot camera, sentence, side panel, board, pain scale, settings
│   ├── src/lib/             API client, speech, hands-free capture, partner mic
│   └── public/fonts/        Atkinson Hyperlegible (bundled for offline use)
├── setup.sh                 One-time install
└── start.sh                 Runs backend + frontend
```

## Run it

Needs macOS or Linux, Python 3.11, Node 18+, ffmpeg (`brew install ffmpeg`) and Chrome.

```bash
./setup.sh      # once
./start.sh      # then open http://localhost:5173 in Chrome
```

On first start the lip-reading weights (~1 GB, `Amanvir/LRS3_V_WER19.1`) download from Hugging Face.
While the model loads, the phrase board, spelling, quick buttons and partner view already work.

Optional keys can be added in **Settings → AI and privacy / Voice**. They're stored in `backend/data/secrets.json`
and are never sent to the browser.
- `GROQ_API_KEY`: smarter correction of look-alike words using the conversation. Only text is sent, never video.
- `ELEVENLABS_API_KEY`: speak in your own cloned voice.

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests
cd frontend && npm run build
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Server, model and voice status |
| GET/PUT | `/api/profile` | Phrases, names, quick buttons, preferences |
| POST | `/api/lipread` | Video clip → sentence, confidence, 3 guesses, `needs_confirmation`, `urgent` |
| GET/POST/DELETE | `/api/log` | Conversation log |
| GET | `/api/log/export?format=txt\|csv` | Export for the care team |
| GET/PUT | `/api/settings/secrets` | Set keys (only shows whether they're set) |
| POST | `/api/voice/clone`, `/api/tts` | Own voice |

## Limits

SilentVoice is a communication aid, not a medical device. It is not a replacement for a nurse-call system.
Lip reading works best with good front lighting, a steady face and short sentences. English only for now.
