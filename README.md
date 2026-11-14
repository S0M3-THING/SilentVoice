# SilentVoice

SilentVoice is a web app that reads your lips through a webcam, for anyone who can't or shouldn't make sound:
a patient after a tracheostomy or laryngectomy, someone with vocal cord paralysis or early ALS, or a student in
a library who just needs to stay quiet.

Everyone uses the same screen: **mouth it, check it, choose where it goes**. A sentence can go
**out loud** on the computer's speakers or any connected Bluetooth speaker (in your own voice if you like),
or be shown **on screen** in large text. A single first-run question ("I can't use my voice right now" or "I can talk, but
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
| Lip reading is often wrong | A small **local text model** checks the guesses against the conversation ("coffee", not "toffee", after "Would you like a drink?"). Then it shows 3 guesses and **None of these**, which opens a phrase board, spelling keyboard or yes/no. You're never stuck. |
| Wrong guesses put words in your mouth | Asks **"Is this what you said?"** when unsure, flags AI-corrected words, and never asserts an urgent phrase from a weak match. |
| Needed Wi-Fi / a server | Lip reading and phrase matching run **offline** on the laptop. AI correction is optional. |
| Nobody nearby should see or hear it | Also for security: share a password, PIN or account number without being overheard. In quiet setups nothing is spoken or saved, earlier lines blur, the screen clears after 2 minutes, and the camera shows only your mouth (the "lip slot"). |
| Hard to use when very unwell | The lip window **follows your mouth**, so you can shift in bed. Tap (or Space) to start and stop, or press and hold, plus one-tap urgent buttons. |
| Urgent needs were slow | An always-visible bar: Nurse, Pain (0–10 scale + body area), Can't breathe, Suction, Bathroom, Water, Yes, No. Urgent messages beep first. |
| Generic robot voice | Speak in **your own voice**, cloned **on your computer** with the open Qwen3-TTS model from a short passage you read or from old voicemails and videos. Nothing is uploaded, consent is required, and phrases said once are cached. |
| Didn't know the context | Listens to the **partner's** question (or lets them type it) and uses it to pick the right answer. |
| Small screens, hard to read | Hyperlegible type, adjustable text size, high-contrast mode, and **On screen** large text with a flip for the person across the bed. |
| Nothing for the care team | A conversation log with **export** (TXT/CSV) for clinicians and family. |
| Same for everyone | Personal phrases, names it should know, and it learns which phrases you use most. **Only my saved phrases** mode gives the most reliable results. |

## Project structure

```
SilentVoice/
├── backend/                 FastAPI server (Python 3.11)
│   ├── app.py               API routes; model loads in the background
│   ├── vsr_service.py       Lip reading (Auto-AVSR via Chaplin), top-10 guesses
│   ├── context_selector.py  Picks the final sentence (word check, optional Groq LLM, offline fallback)
│   ├── word_check.py        Local text model (Qwen2.5 1.5B via mlx-lm) that ranks the lip-reading guesses
│   ├── mouth.py             Finds the mouth in a frame so the lip window can follow it (MediaPipe)
│   ├── system_voice.py      The Mac's voices (`say`) as audio, so speech can go to any speaker
│   ├── phrases.py           Phrase bank, look-alike-letter matcher, urgent detection
│   ├── store.py             Local profile, keys and conversation log (backend/data/)
│   ├── voice.py             Own voice: clean the sample, pick the best 6-15 s, transcript, cache
│   ├── voice_engine.py      Local voice-cloning engine (Qwen3-TTS + Whisper via mlx-audio)
│   ├── tests/               pytest suite (runs without the model)
│   └── vendor/chaplin/      Lip-reading model code (cloned by setup.sh, git-ignored)
├── frontend/                React + Vite app
│   ├── src/App.jsx          Main screen
│   ├── src/components/      Setup, shortcuts, lip slot camera, sentence, side panel, board, pain scale, settings
│   ├── src/lib/             API client, speech + speakers, capture, lip tracking, partner mic
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

The word check model (~0.9 GB, `mlx-community/Qwen2.5-1.5B-Instruct-4bit`) downloads on first start on
Apple Silicon Macs. It runs locally; turn it off in **Settings → Reading**, or with `SILENTVOICE_WORD_CHECK=0`.

An optional Groq key can be added in **Settings → Privacy**. It's stored in `backend/data/secrets.json` and is never
sent to the browser.
- `GROQ_API_KEY`: smarter correction of look-alike words using the conversation. Only text is sent, never video.

## Your own voice

SilentVoice can speak in a copy of your own voice, made entirely on your computer with
[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) (Alibaba, Apache 2.0) running on Apple Silicon through
[mlx-audio](https://github.com/Blaizzy/mlx-audio). Set it up in **Settings → Voice**:

- **Read a short passage** (about 10 seconds), useful for banking your voice before surgery, or
- **Use old recordings**: voicemails, videos or voice notes. SilentVoice removes rumble and background noise,
  keeps the clearest 6 to 15 seconds, and writes down what's said with a local Whisper model. Check that transcript:
  it must match the sample word for word.

You must confirm the voice is yours or that you have permission. The sample and generated sentences stay in
`backend/data/voice/` and are deleted with **Delete my voice**.

- Needs an Apple Silicon Mac (M1 or newer). On other machines the device voice is used instead.
- The first use downloads the voice model (~1.5 GB) and, for old recordings, Whisper (~1.6 GB).
- Bigger, better, slower model: set `SILENTVOICE_VOICE_MODEL=mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` in `backend/.env`.
- The engine is behind a small interface in `voice_engine.py`, so another open model (for example Chatterbox, MIT)
  can be swapped in later.

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
| GET/POST/PUT/DELETE | `/api/voice`, `/api/voice/reference`, `/api/voice/transcript` | Set up, check and delete your own voice |
| POST | `/api/tts` | A sentence in your own voice (WAV, cached) |

## Limits

SilentVoice is a communication aid, not a medical device. It is not a replacement for a nurse-call system.
Lip reading works best with good front lighting, a steady face and short sentences. English only for now.
