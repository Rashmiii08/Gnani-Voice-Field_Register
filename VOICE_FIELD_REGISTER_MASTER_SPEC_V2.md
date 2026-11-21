# VOICE FIELD REGISTER — SHARED MASTER SPEC v2.0
**Team:** Cookies | **Track:** PS1, Gnani Voice Hackathon | **Duration:** 24 hours | **Status:** implementation contract

## 0. Instructions for every AI coding agent
You are implementing ONE role of a four-person hackathon team. Treat this document as the single source of truth for shared interfaces and acceptance criteria. The official hackathon brief overrides any conflict. Ask the human for your role (A, B, C, or D) if not specified. Only edit files owned by that role unless the team lead approves changes. Never invent Gnani endpoints, authorization headers, WebSocket event schemas, model parameters, or public-health thresholds. Where vendor documentation is missing, create a clearly marked adapter interface and mock implementation; request official documentation before live integration. Return file-by-file code, setup commands, tests, assumptions, blockers and a short integration handoff. Never claim tests were run unless actually executed. Do not output or commit secrets.

## 1. Mission and success criteria
Build a browser-based, low-end-Android-friendly voice field register for ASHA workers. Worker speaks a synthetic home-visit note in a supported Indic language with English code-mixing; agent transcribes, extracts structured fields, reads them back, accepts voice corrections, confirms before saving, and generates a follow-up list. Detect specified danger signs, flag the record and speak a fixed PHC referral message in the user's language. Support household/street noise. No typing should be needed in the main visit workflow.

**Judge-priority weights:** live judge test 30; speech-layer depth 20; target-user fit 20; innovation 10; responsible AI 10; demo/docs 10. Test time-to-first-audio, numbers/IDs, code-mix, interruption and danger-sign recall. Measure and report actual performance, not aspirations.

## 2. Non-negotiable rules
- Gnani API Platform **Prisma v3.0** for streaming STT and **Timbre v3.0** for streaming TTS; WebSocket streaming only. No telephony, phone numbers, voice cloning, browser speech synthesis or record-then-upload as the core loop.
- LLM is open choice; default Gemini via google-genai for text extraction. Orchestration can be custom FastAPI or a verified framework, not a hosted end-to-end agent as core loop.
- First spoken turn discloses that the system is AI, in the selected language.
- Only synthetic beneficiary data. Never upload real patient records or call recordings. Encrypt persisted transcripts/forms; delete after judging. Keep secrets out of Git and client-side JavaScript.
- No diagnosis, treatment or dosage guidance. Danger-sign logic must use an identified, verified public-health guideline and fixed referral phrases. Unknown/ambiguous medical details should trigger clarification or safe referral, never fabricated medical advice.
- **Offline-resilient workflow**, not offline-first or on-device AI: static PWA caching and carefully limited local draft persistence; voice AI needs connectivity. Avoid claims of zero data loss or perfect offline operation.
- No unsupported claims: under 10 seconds, sub-second latency, 40% paperwork savings, WHO 47-item taxonomy, automatic SMS, ICD-10/SNOMED coding, CRDT sync or production readiness unless implemented and measured. Original slide deck contains aspirational claims that need revision.

## 3. Team ownership (one owner per file)
**A — Team lead, real-time pipeline:** `backend/main.py`, `backend/gnani_adapter.py`, `tests/test_streaming.py`. Own frontend/backend socket integration, STT/TTS streaming, cancellation, latency, error handling, final integration and releases. Start with mock provider; integrate real Gnani only from official docs.
**B — Dialogue and extraction:** `backend/dialogue.py`, `backend/llm.py`, `tests/test_dialogue.py`, `scripts/score_clips.py`, `assets/expected_cases.json`. Own state machine, structured extraction, correction/readback, follow-up list, scoring. Fake transcript fixtures for tests.
**C — Frontend/PWA:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/manifest.json`, `frontend/sw.js`, `frontend/audio-worklet.js`. Own microphone capture, actual resampling to 16k PCM16, streaming, playback, interruption detection, accessibility, reconnect UI and safe draft recovery.
**D — Safety, persistence, docs and pitch:** `backend/danger.py`, `backend/phrases.py`, `backend/db.py`, `tests/test_danger.py`, `scripts/delete_all_data.py`, `README.md`, `docs/demo_script.md`, `docs/pitch_outline.md`. Own verified danger-list citations, encrypted SQLite, deletion, safety testing, documentation, demo video/pitch coordination.
**Shared setup** (lead approves): `.env.example`, `.gitignore`, `requirements.txt`, `backend/__init__.py`, `tests/conftest.py`. Everyone works in own branch and raises PRs; avoid simultaneous edits to shared files.

### GitHub Collaboration Rules

1. Role A must work on the `role-a` branch.
2. Role B must work on the `role-b` branch.
3. Role C must work on the `role-c` branch.
4. Role D must work on the `role-d` branch.
5. No teammate should push code directly to `main`.
6. Each teammate must commit and push changes to their assigned branch.
7. After testing their code, teammates must create a Pull Request (PR) targeting `main`.
8. The Team Lead (Role A) reviews and merges Pull Requests.
9. Do not modify another teammate's files without permission.
10. All AI coding agents must follow these rules.



## 4. Canonical repo tree
```
voice-field-register/
  .env.example  .gitignore  requirements.txt  README.md
  backend/
    __init__.py  main.py  gnani_adapter.py  dialogue.py  llm.py
    danger.py  phrases.py  db.py
  frontend/
    index.html  app.js  styles.css  audio-worklet.js  manifest.json  sw.js
  tests/
    conftest.py  test_streaming.py  test_dialogue.py  test_danger.py
  scripts/
    score_clips.py  delete_all_data.py
  assets/
    expected_cases.json  noise_test_clips/   # synthetic/test-only audio, not committed by default
  docs/
    demo_script.md  pitch_outline.md
```

## 5. Architecture and responsibility boundaries
Microphone -> C browser AudioWorklet (mono PCM16 16 kHz) -> C WebSocket client -> A FastAPI `/ws` -> A Gnani Prisma streaming adapter -> final transcript -> B `handle_turn` (calls LLM and D danger checker) -> D encrypted persistence after explicit confirmation -> A Gnani Timbre streaming adapter -> C audio playback. A owns session lifecycle, message dispatch and cancellation; B owns state transitions; D owns safety and persistence; C owns user-facing UI and local draft. The first disclosure is a fixed phrase from D, spoken through Gnani TTS via A.

## 6. Shared contracts — freeze before coding
### 6.1 Frontend -> backend JSON text frames
```
{"type":"start","language":"hi","session_id":"demo-session"}
{"type":"audio","data":"<base64 PCM16 mono 16000 Hz>","seq":1}
{"type":"interrupt"}
{"type":"end_utterance"}
{"type":"resume","session_id":"demo-session","draft_version":1}
```
`start`, `end_utterance`, `resume`, and `seq` are **proposed additions to the old spec**; all four teammates must agree before implementation. Audio is ~100ms chunks, no WAV container. Only send audio after microphone permission. Browser capture sampleRate is not guaranteed; explicitly resample and test. `end_utterance` must be generated from user action or verified endpointing logic; do not rely on imaginary Gnani events.

### 6.2 Backend -> frontend JSON text frames
```
{"type":"ready","session_id":"demo-session"}
{"type":"transcript","text":"...","final":true}
{"type":"audio","data":"<base64 PCM16 mono 16000 Hz>","is_first_chunk":true,"turn_id":1}
{"type":"update","state":"LISTENING","form":{},"danger_flag":false,"latency_ms":null,"follow_ups":[]}
{"type":"error","code":"STT_UNAVAILABLE","message":"Please reconnect or retry"}
```
`audio` and `update` preserve the existing master spec's message types; `ready`, `transcript`, `error`, `turn_id`, `follow_ups` are proposed refinements. Confirm actual Timbre output encoding/rate; A must convert to the agreed frontend format, not mislabel audio. `latency_ms` may be null until first audio. The UI must not display an unverified latency value.

### 6.3 Internal canonical data
```
VisitForm = {
  "beneficiary_id": "string|null", "visit_type": "antenatal|postnatal|newborn|immunisation|other|null",
  "weight_kg": "number|null", "vaccinations_due": ["string"],
  "next_visit_date": "YYYY-MM-DD|null", "temperature_c": "number|null",
  "bp_systolic": "integer|null", "bp_diastolic": "integer|null"
}
LLMResult = {"intent":"provide_info|correction|confirm_yes|confirm_no|other",
             "patch":{},"danger_candidates":[]}
Session = {"session_id":"string","language":"hi|en","state":"LISTENING|CONFIRMING|SAVED",
           "form":VisitForm,"danger_flag":false,"follow_ups":[],"turn_id":0}
Say = {"text":"string","kind":"disclosure|prompt|readback|saved|referral"}
```
`Session` and `Say` are the **new complete proposed contract** because the previous document references undefined dataclasses. B implements actual Python dataclasses/types; A and D consume them. All unknown values stay null; never infer a value from missing speech. Date interpretation requires an explicit current date and timezone. Numbers/IDs should be clearly spoken in readback. Keep units explicit.

### 6.4 Backend interfaces
```
handle_turn(session: Session, text: str, llm_fn, danger_fn) -> list[Say]
check_danger(form: VisitForm, transcript_text: str, llm_candidates: list[str]) -> list[str]
extract_visit(text: str, state: str, form: VisitForm, today: str) -> LLMResult
save_confirmed_visit(session: Session, transcript: str) -> str
```
B owns `handle_turn` and `extract_visit`; D owns `check_danger` and `save_confirmed_visit`; A wires them together. The `handle_turn` function mutates the passed session consistently and returns utterances to synthesize. **No direct imports between B and D modules are required:** A injects dependencies, avoiding circular imports. B must never persist before explicit confirmation. Safety referral must override ordinary LLM output. Danger candidates must be validated against D's approved allowlist.

## 7. State machine and safety order
1. On start, say fixed AI disclosure in user's language.
2. LISTENING: accept final STT transcript, detect danger from text and structured fields before ordinary response; if flagged, show red warning and speak fixed PHC referral phrase, without diagnosis or treatment. Preserve flag for review.
3. Otherwise B extracts fields and asks for missing or ambiguous information; present a structured form and follow-up items.
4. Read back the proposed record aloud, including ID/numbers and visit date; enter CONFIRMING.
5. Voice correction changes only named fields, then repeat readback. Spoken yes saves exactly once through D's encrypted store; spoken no asks for correction. Never save silently.
6. SAVED: show confirmation and follow-up list. On reconnect, never duplicate saves; session IDs and save IDs must be idempotent.
7. LLM timeout or invalid JSON -> safe retry/clarification; don't crash WebSocket or fabricate fields. Danger checks must still run independently of LLM availability.

## 8. Role-specific AI prompts (append after this full master spec)
**A:** You are the backend streaming engineer and team lead. Implement only A-owned files. Start with a FastAPI `/ws` mock echo and fake transcript/TTS adapters, then add documented Gnani Prisma v3.0 and Timbre v3.0 WebSocket clients. Handle connection lifecycle, async queues, barge-in task cancellation and stale-chunk suppression, graceful timeouts, logging without secrets or patient data, and first-audio latency. Provide a frontend handshake test. Do not invent provider protocol.
**B:** You are the dialogue/state machine engineer. Implement only B-owned files using the exact shared dataclasses and injected interfaces. Validate LLM JSON, normalize Hindi/English yes/no/corrections, preserve fields not corrected, read back IDs/numbers unambiguously, require confirmation, output follow-up list, and implement synthetic noisy/code-mixed test fixtures. Do not give medical advice.
**C:** You are the browser audio/PWA engineer. Implement only C-owned files. Use AudioWorklet capture and real resampling, PCM16 base64 WebSocket frames, reliable playback and queue clearing, client VAD barge-in with false-trigger mitigation, reconnect status, minimal high-contrast Hindi/English UI, accessible large buttons and safe local drafts. Never put API keys in browser. Do not claim offline STT/TTS; protect sensitive draft data and clear it after submission/judging.
**D:** You are the safety/data/docs engineer and primary pitcher. Implement only D-owned files. Choose a real public guideline and document exact source and verified criteria before coding danger thresholds. Use rule-based danger detection plus validated LLM candidate IDs, fixed Hindi/English referral and disclosure phrases, Fernet encryption for stored data, secure deletion procedure, synthetic-data-only tests, README with architecture, setup, credits and limitations, and a 2–3 minute demo script and <=6-slide pitch outline. Do not invent health thresholds, impact statistics or test results.

## 9. 24-hour execution and gates
**0–1h:** team lead creates repo, `.env.example`, dependencies and branch rules; freeze contracts; confirm Gnani access and official docs. Each role posts a 3-sentence plan.
**1–4h:** A mock WebSocket; B pure state machine; C microphone/WebSocket skeleton; D fixed phrases, guideline selection and encrypted store. Gate: frontend can exchange one message with backend and B tests pass.
**4–8h:** A live Prisma STT; C actual PCM16 and transcript display; B extraction/readback; D danger checker. Gate: live speech -> accurate final transcript -> form draft.
**8–12h:** A Timbre streaming; B confirmation/corrections; C playback/interruption; D persistence. Gate: spoken note -> readback -> spoken correction -> confirmed encrypted save.
**12–16h:** integrate safety, interruption, follow-up and reconnect; test on low-end Android, noisy audio and mixed language. Gate: danger phrase overrides normal reply, no duplicate save.
**16–20h:** stabilize, test failures, score synthetic clips, verify deletion and security, write README and slides. No risky new features.
**20–24h:** freeze code, record real 2–3 minute demo, rehearse judge interaction, submit repo/hosted link, <=6-slide pitch and documentation. Keep time buffer for deployment failures.

## 10. Test matrix (must demonstrate)
- Spoken synthetic visit fills ID, visit type, weight, vaccines, date.
- Readback and voice correction change exactly one field; yes saves once, no does not save.
- Hindi/English code-mix and background noise; record exact field accuracy on test set.
- Danger mention: red banner + fixed PHC referral, never LLM medical advice; tests include missed/ambiguous signs.
- Interrupt while speaking: no stale TTS audio continues.
- STT/LLM/TTS outage: clear retry state, no crash, no fake success.
- Disconnect/reconnect: draft recovered without exposing real health data or duplicate save.
- First-audio latency measured from end of user speech **and** from final STT arrival (two distinct metrics; official rubric cares about the first).
- `.env` excluded from Git; encrypted SQLite contains no plaintext transcripts; deletion script verified.
- Run `pytest`; document pass/fail honestly and verify actual Android behavior.

## 11. Submission checklist
Working hosted link or runnable repo; public GitHub repository; README with installation steps, architecture and Gnani services; 2–3-minute video of live voice interaction; pitch deck maximum 6 slides; live judge demo; citations for danger-sign guideline; no patient data, secrets or false performance claims.

## 12. Team communication protocol
Every 60–90 minutes each member reports: completed, currently working, blocker, changed interfaces, ETA. Raise blockers after 15 minutes rather than silently waiting. Merge smallest working increments; integration happens throughout, not only at the end. Team lead owns final contract decisions and release freeze. If vendor docs are inaccessible, use mock adapters for local progress and escalate immediately; a mocked demonstration must never be represented as a live Gnani integration.

## 13. Questions to resolve now (do not silently assume)
1. Exact Gnani Prisma/Timbre WebSocket URLs, auth, events, sample rates, endpointing and cancellation semantics from official documentation.
2. Exact approved danger-sign guideline and its thresholds/phrase translations.
3. Whether Antigravity is mandatory or merely recommended by organizers.
4. Whether synthetic draft data may be stored in browser localStorage under event privacy rules; prefer minimizing retention and clear after judging.
5. Final supported Indic languages beyond the proposed Hindi/English initial UI.

**END OF SHARED SPEC.** Each teammate pastes the ENTIRE document into their AI agent and then appends only their role letter (A/B/C/D). Agents must not reinterpret other roles' ownership.
