# SilentVoice

SilentVoice is a hackathon prototype for people who can mouth words but cannot
reliably voice them. The MVP aims to turn a short, silently mouthed reply into
editable suggestions and speak the user's confirmed message. For example, after a
partner asks “Would you like tea?”, the partner's words can help rank “Tea, please”
among plausible replies.

## What runs today

The React demo sends three labeled sample hypotheses and typed partner context
to FastAPI. The API returns up to three ranked candidates. The user can pick,
edit, or type a reply and explicitly press **Speak message** to use browser
text-to-speech (TTS). The starter requires no camera, microphone, model weights,
or API keys. Webcam lip-reading, Whisper, learned reranking, and personal voice
synthesis are planned integrations.

## MVP architecture

| Stage | Design |
| --- | --- |
| Capture | React, Vite, and TypeScript provide push-to-record webcam capture, framing feedback, and separate opt-in partner audio capture. Send one short video clip per turn with no audio track. |
| Visual speech recognition | FastAPI calls a local [Chaplin](https://github.com/amanvirparhar/chaplin) / [Auto-AVSR](https://github.com/mpc001/auto_avsr) adapter. Crop and align the mouth region using the model's preprocessing and expose up to ten decoded hypotheses with normalized scores. Check whether the decoder exposes an n-best list before committing to reranking. |
| Partner transcription | Use [Whisper](https://github.com/openai/whisper) on the partner's audible speech. Keep only the last confirmed prompt in session memory and allow manual entry and correction. |
| Context reranking | Combine visual scores, the recent partner prompt, and optional user-supplied phrases. The starter adds small token-overlap and phrase-match bonuses. A later language model can reorder existing candidate IDs while preserving their text and the original visual-only ranking for comparison. |
| Confirmation and speech | Show up to three large, keyboard-accessible choices and an editable text field. Speak only on an explicit user action. Use browser TTS first and consider a consented personal voice as a separate opt-in. |

`GET /health` checks whether the API is running. `POST /api/rerank` accepts
`candidates` (objects with `text` and `visual_score` from 0 to 1), optional
`partner_text`, and optional `personal_phrases`. It returns the highest-ranked
candidates in the same shape. Visual scores are preserved and should be treated
as relative scores until calibrated on held-out clips.

## Local setup

Use Python 3.10+ and Node.js 22.12+ with npm. Run these commands from the
repository root in two terminals.

**API**

```sh
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Frontend**

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Select **Rank sample replies** and confirm that
“Tea, please.” ranks first with the default prompt. Pick a reply, edit it if
needed, and press **Speak message**. Try a typed reply with the API stopped
to verify the fallback. Browser speech playback depends on available voices.

API docs are at http://127.0.0.1:8000/docs. Check the API with
`curl -fsS http://127.0.0.1:8000/health` and run `npm run build` in
`frontend/` to type-check and build the client.

## Environment variables

| Variable | Location | Default |
| --- | --- | --- |
| `FRONTEND_ORIGIN` | Root `.env` | `http://localhost:5173` |
| `VITE_API_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` |

Use the exact origin displayed in the browser, including its port. Vite exposes
`VITE_*` values to browsers. Store any future provider keys in a server-side
environment file and document the variable names without adding real values.

## Project layout

```text
.
├── .env.example
├── .gitignore
├── README.md
├── backend/
│   ├── main.py
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        └── style.css
```

## Hackathon milestones

1. **30-minute feasibility check.** Try the visual-only checkpoint with two
   consenting teammates, five short phrases each, and one unfamiliar prompt.
   Record top-1 and top-3 phrase matches and clip-to-suggestion latency. Agree on
   a demo threshold before testing. If it misses the threshold, narrow the
   phrase set and label any fixture-based demo clearly.
2. **Connect the model.** Get reliable mouth crops, handle missing faces and
   unsupported clips, and pass decoder candidates to the existing API shape.
   Keep heavy model dependencies separate from the starter requirements.
3. **Add partner context.** Wire opt-in Whisper and compare top-1/top-3 accuracy
   with and without context on the same clips, including misleading prompts.
4. **Rehearse the user flow.** Test keyboard navigation, edits, retries, no
   audio output, and the manual fallback. Measure median and p95 response time
   on the machine used for the demo.

## Limitations and ethics

Many sounds look identical on the lips. Lighting, camera angle, occlusion,
language, and differences in articulation can affect results. Benchmark
performance does not establish accuracy for people with laryngectomy or
tracheostomy. This prototype is intended for low-stakes demos and has no
clinical validation or emergency-use evaluation.

Keep the user in control of the final words. Make recording visible and
opt-in, get the partner's consent before transcribing, and provide a usable
typed fallback. Process clips locally where feasible and discard recordings
after inference by default. Review and disclose any external service's data
handling before routing media to it. Some browser voices use network services.
Keep recordings, model weights, and voice samples out of Git. For personal
voice synthesis, obtain explicit authorization from the voice owner and
provide a way to revoke consent and delete the source samples.
