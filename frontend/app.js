"use strict";

const byId = (id) => document.getElementById(id);
const statusElement = byId("status");
const transcriptElement = byId("transcript");
const startButton = byId("startBtn");
const stopButton = byId("stopBtn");
const interruptButton = byId("interruptBtn");
const resetButton = byId("resetBtn");
const languageSelect = byId("language");
const storageKey = "voice-register-workflow";
const sampleRate = 16000;

const copy = {
  en: {
    title: "Voice Field Register", intro: "Use synthetic patient information only.",
    demo: "Simulation. Recording triggers a scripted transcript and test tones. Visits are previews only.",
    language: "Language", start: "Start Recording", stop: "Stop Recording",
    interrupt: "Interrupt playback", reset: "New visit", visit: "Visit details",
    transcript: "Transcript", danger: "Possible danger sign. Follow the approved local referral protocol.",
    idle: "Ready to connect", connecting: "Connecting…", ready: "Connected and ready",
    recording: "Recording…", processing: "Processing recording…", reconnecting: "Reconnecting…",
    offline: "Offline. Recording requires a connection.", disconnected: "Disconnected. Select Start Recording to retry.",
    microphone: "Microphone unavailable. Check permission and your input device.",
    playback: "Playback unavailable. Select Start Recording to enable audio.",
    retry: "Please reconnect or retry.", stt: "Speech recognition unavailable. Check the connection and Gnani access.", tts: "Voice playback from Gnani is unavailable. You can still read the transcript.", expired: "The previous session expired. Start a new visit.",
    lostRecording: "The interrupted recording was discarded. Please record it again.",
    pending: "Awaiting confirmation. Review the beneficiary ID and visit details.",
    saved: "Visit saved", listening: "Listening for visit details",
    noSpeech: "No speech was recognized. Please try again.",
    fields: ["Beneficiary ID", "Visit type", "Weight (kg)", "Vaccinations due", "Next visit", "Temperature (°C)", "Systolic BP", "Diastolic BP"],
  },
  hi: {
    title: "वॉइस फ़ील्ड रजिस्टर", intro: "केवल काल्पनिक मरीज़ की जानकारी इस्तेमाल करें।",
    demo: "सिमुलेशन। रिकॉर्डिंग पर पहले से तय पाठ और परीक्षण ध्वनि मिलती है। विज़िट केवल पूर्वावलोकन हैं।",
    language: "भाषा", start: "रिकॉर्डिंग शुरू करें", stop: "रिकॉर्डिंग रोकें",
    interrupt: "ऑडियो रोकें", reset: "नई विज़िट", visit: "विज़िट का विवरण",
    transcript: "बातचीत का पाठ", danger: "संभावित खतरे का संकेत। स्वीकृत स्थानीय रेफरल प्रक्रिया का पालन करें।",
    idle: "कनेक्ट करने के लिए तैयार", connecting: "कनेक्ट हो रहा है…", ready: "कनेक्ट हो गया",
    recording: "रिकॉर्डिंग जारी है…", processing: "रिकॉर्डिंग संसाधित हो रही है…", reconnecting: "फिर से कनेक्ट हो रहा है…",
    offline: "ऑफ़लाइन। रिकॉर्डिंग के लिए कनेक्शन चाहिए।", disconnected: "कनेक्शन टूट गया। दोबारा रिकॉर्डिंग शुरू करें।",
    microphone: "माइक्रोफ़ोन उपलब्ध नहीं है। अनुमति और डिवाइस की जाँच करें।",
    playback: "ऑडियो सुनने के लिए रिकॉर्डिंग शुरू करें चुनें।",
    retry: "फिर से कनेक्ट करें या दोबारा कोशिश करें।", stt: "बोली पहचान उपलब्ध नहीं है। कनेक्शन और Gnani की पहुँच जाँचें।", tts: "Gnani ऑडियो उपलब्ध नहीं है। आप बातचीत का पाठ पढ़ सकते हैं।", expired: "पिछला सत्र समाप्त हो गया। नई विज़िट शुरू करें।",
    lostRecording: "बीच में रुकी रिकॉर्डिंग हटा दी गई। फिर से रिकॉर्ड करें।",
    pending: "पुष्टि बाकी है। लाभार्थी आईडी और विज़िट का विवरण जाँचें।",
    saved: "विज़िट सहेजी गई", listening: "विज़िट का विवरण सुनने के लिए तैयार",
    noSpeech: "बोली पहचान में नहीं आई। दोबारा कोशिश करें।",
    fields: ["लाभार्थी आईडी", "विज़िट का प्रकार", "वज़न (किग्रा)", "बाकी टीके", "अगली विज़िट", "तापमान (°C)", "सिस्टोलिक बीपी", "डायस्टोलिक बीपी"],
  },
};
const fieldNames = [
  "beneficiary_id", "visit_type", "weight_kg", "vaccinations_due",
  "next_visit_date", "temperature_c", "bp_systolic", "bp_diastolic",
];

let workflow;
try {
  const stored = JSON.parse(sessionStorage.getItem(storageKey));
  if (/^[0-9a-f-]{36}$/i.test(stored?.session_id) && copy[stored.language]) workflow = stored;
} catch { /* The app can run with browser storage disabled. */ }
let socket;
let ready = false;
let sequence = 0;
let reconnectAttempts = 0;
let reconnectTimer;
let handshakeTimer;
let wasReady = Boolean(workflow);
let started = false;
let capture;
let starting = false;
let waiting = false;
let statusKey = navigator.onLine ? "idle" : "offline";
let errorKey = "";
let visit;
let audioContext;
let workletSession;
let turn = -1;
let mutedTurn = -1;
let nextPlayback = 0;
const playing = new Set();

const strings = () => copy[languageSelect.value] || copy.en;
if (workflow) languageSelect.value = workflow.language;

function render() {
  document.documentElement.lang = languageSelect.value;
  document.querySelectorAll("[data-label]").forEach((element) => {
    element.textContent = strings()[element.dataset.label];
  });
  statusElement.textContent = strings()[statusKey];
  byId("error").textContent = strings()[errorKey] || "";
  byId("error").hidden = !errorKey;
  startButton.disabled = starting || Boolean(capture) || waiting || Boolean(socket && !ready) || !navigator.onLine;
  stopButton.disabled = !capture || capture.stopping;
  interruptButton.disabled = playing.size === 0;
  resetButton.disabled = !workflow && !starting;
  languageSelect.disabled = Boolean(workflow) || starting;
}

function setStatus(key) {
  statusKey = key;
  render();
}

function showError(key) {
  errorKey = key;
  render();
}

function renderVisit() {
  const details = byId("visitDetails");
  details.replaceChildren();
  byId("followUps").replaceChildren();
  byId("danger").hidden = !visit?.danger_flag;
  byId("visitState").textContent = visit
    ? strings()[{LISTENING: "listening", CONFIRMING: "pending", SAVED: "saved"}[visit.state]] || ""
    : "";
  fieldNames.forEach((field, index) => {
    const value = visit?.form?.[field];
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) return;
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = strings().fields[index];
    description.textContent = Array.isArray(value) ? value.join(", ") : String(value);
    details.append(term, description);
  });
  for (const value of visit?.follow_ups || []) {
    const item = document.createElement("li");
    item.textContent = typeof value === "string" ? value : "";
    if (item.textContent) byId("followUps").append(item);
  }
}

function storeWorkflow() {
  try {
    if (workflow) sessionStorage.setItem(storageKey, JSON.stringify(workflow));
    else sessionStorage.removeItem(storageKey);
  } catch { /* In-memory workflow remains available. */ }
}

function send(message) {
  if (!ready || socket?.readyState !== WebSocket.OPEN) return false;
  if (message.type === "audio" && socket.bufferedAmount > 64 * 1024) {
    socket.close(4002, "Audio backlog");
    return false;
  }
  socket.send(JSON.stringify(message));
  return true;
}

function clearPlayback() {
  for (const source of playing) source.stop();
  playing.clear();
  nextPlayback = 0;
  render();
}

function interruptPlayback() {
  mutedTurn = Math.max(mutedTurn, turn);
  clearPlayback();
  send({type: "interrupt"});
}

function playAudio(message) {
  if (!Number.isInteger(message.turn_id) || message.turn_id <= mutedTurn ||
      message.turn_id < turn) return;
  if (!audioContext || audioContext.state !== "running") {
    showError("playback");
    return;
  }
  if (message.is_first_chunk) {
    clearPlayback();
    turn = message.turn_id;
  }
  if (message.turn_id !== turn) return;
  try {
    const raw = Uint8Array.from(atob(message.data), (byte) => byte.charCodeAt(0));
    if (!raw.length || raw.length % 2) return;
    const buffer = audioContext.createBuffer(1, raw.length / 2, sampleRate);
    const samples = buffer.getChannelData(0);
    const pcm = new DataView(raw.buffer);
    for (let i = 0; i < samples.length; i++) samples[i] = pcm.getInt16(i * 2, true) / 32768;
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    playing.add(source);
    source.onended = () => {
      source.disconnect();
      playing.delete(source);
      render();
    };
    const when = Math.max(audioContext.currentTime + 0.02, nextPlayback);
    source.start(when);
    nextPlayback = when + buffer.duration;
    render();
  } catch { showError("playback"); }
}

function onMessage(message) {
  if (message.type === "audio") playAudio(message);
  if (message.type === "transcript") {
    const line = document.createElement("li");
    line.textContent = message.text;
    transcriptElement.append(line);
    if (message.final) {
      waiting = false;
      if (capture) releaseCapture();
      setStatus("ready");
    }
  }
  if (message.type === "update") {
    visit = message;
    renderVisit();
  }
  if (message.type === "error") {
    if (message.code !== "TTS_UNAVAILABLE") {
      waiting = false;
      releaseCapture();
    }
    const errors = {
      NO_SPEECH: "noSpeech", SESSION_NOT_RESUMABLE: "expired",
      STT_UNAVAILABLE: "stt", TTS_UNAVAILABLE: "tts",
    };
    showError(errors[message.code] || "retry");
    if (ready) setStatus(capture ? "recording" : waiting ? "processing" : "ready");
  }
}

function connect() {
  if (ready) return Promise.resolve();
  return new Promise((resolve, reject) => {
    if (!navigator.onLine) {
      setStatus("offline");
      reject(new Error("offline"));
      return;
    }
    const url = new URL("/ws", location.href);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const current = new WebSocket(url);
    socket = current;
    let expired = false;
    setStatus(wasReady ? "reconnecting" : "connecting");
    handshakeTimer = setTimeout(() => current.close(), 8000);
    current.onopen = () => {
      current.send(JSON.stringify(wasReady ?
        {type: "resume", session_id: workflow.session_id, draft_version: 1} :
        {type: "start", language: workflow.language, session_id: workflow.session_id}));
    };
    current.onmessage = ({data}) => {
      if (socket !== current) return;
      let message;
      try { message = JSON.parse(data); } catch { showError("retry"); return; }
      if (message.type === "ready" && message.session_id === workflow.session_id) {
        clearTimeout(handshakeTimer);
        ready = wasReady = true;
        sequence = 0;
        reconnectAttempts = 0;
        storeWorkflow();
        setStatus("ready");
        resolve();
      } else if (message.type === "error") {
        expired = !ready && message.code === "SESSION_NOT_RESUMABLE";
        if (!ready && message.code === "SESSION_EXISTS") wasReady = true;
        onMessage(message);
      } else if (ready) {
        onMessage(message);
      }
    };
    current.onclose = () => {
      reject(new Error("connection closed"));
      if (socket !== current) return;
      clearTimeout(handshakeTimer);
      socket = null;
      ready = false;
      if (capture || waiting) showError("lostRecording");
      releaseCapture();
      waiting = false;
      clearPlayback();
      turn = mutedTurn = -1;
      if (expired) {
        // A recent disconnect can briefly overlap server cleanup, so retry once.
        if (reconnectAttempts < 2) {
          scheduleReconnect();
          return;
        }
        resetVisit();
        showError("expired");
        return;
      }
      scheduleReconnect();
    };
  });
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  if (!workflow || !started) return;
  if (!navigator.onLine) { setStatus("offline"); return; }
  if (reconnectAttempts >= 6) { setStatus("disconnected"); return; }
  setStatus("reconnecting");
  const delay = Math.min(1000 * 2 ** reconnectAttempts++, 8000);
  reconnectTimer = setTimeout(() => connect().catch(() => {}), delay);
}

function releaseCapture() {
  if (!capture) return;
  clearTimeout(capture.flushTimer);
  capture.node?.disconnect();
  capture.source?.disconnect();
  capture.silence?.disconnect();
  capture.stream?.getTracks().forEach((track) => track.stop());
  capture = null;
  render();
}

function streamChunk(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return send({type: "audio", data: btoa(binary), seq: ++sequence});
}

function captureChunk(active, buffer) {
  const pcm = new DataView(buffer);
  let squares = 0;
  for (let i = 0; i < pcm.byteLength; i += 2) {
    const sample = Math.abs(pcm.getInt16(i, true)) / 32768;
    squares += sample ** 2;
    active.peak = Math.max(active.peak, sample);
  }
  active.chunks += 1;
  active.bytes += pcm.byteLength;
  active.sumSquares += squares;
  if (!playing.size) {
    for (const recent of active.voiceFrames) streamChunk(recent);
    active.voiceFrames = [];
    streamChunk(buffer);
    return;
  }
  // Require three consecutive loud frames while playback overlaps capture.
  const rms = Math.sqrt(squares / (pcm.byteLength / 2));
  if (rms < 0.075) {
    active.suppressedChunks += active.voiceFrames.length + 1;
    active.voiceFrames = [];
    return;
  }
  active.voiceFrames.push(buffer);
  if (active.voiceFrames.length === 3) {
    interruptPlayback();
    for (const recent of active.voiceFrames) streamChunk(recent);
    active.voiceFrames = [];
  }
}

async function startRecording() {
  if (starting || capture || waiting) return;
  if (socket && !ready) return;
  starting = true;
  errorKey = "";
  clearTimeout(reconnectTimer);
  const active = {
    voiceFrames: [], stopping: false, chunks: 0, bytes: 0,
    sumSquares: 0, peak: 0, suppressedChunks: 0,
  };
  capture = active;
  render();
  try {
    audioContext ||= new AudioContext();
    await audioContext.resume();
    if (capture !== active) return;
    if (!workflow) workflow = {session_id: crypto.randomUUID(), language: languageSelect.value};
    started = true;
    reconnectAttempts = 0;
    if (playing.size) interruptPlayback();
    try { await connect(); } catch { return; }
    if (capture !== active) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true},
    });
    if (capture !== active || !ready) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    active.stream = stream;
    const track = stream.getAudioTracks()[0];
    const settings = track.getSettings();
    active.input = {
      trackSampleRate: settings.sampleRate, trackChannels: settings.channelCount,
      contextSampleRate: audioContext.sampleRate, muted: track.muted,
    };
    active.startSequence = sequence;
    workletSession ||= audioContext.audioWorklet.addModule("./audio-worklet.js").catch((error) => {
      workletSession = null;
      throw error;
    });
    await workletSession;
    if (capture !== active) return;
    active.source = audioContext.createMediaStreamSource(stream);
    active.node = new AudioWorkletNode(audioContext, "audio-processor");
    active.silence = audioContext.createGain();
    active.silence.gain.value = 0;
    active.source.connect(active.node).connect(active.silence).connect(audioContext.destination);
    active.node.port.onmessage = ({data}) => {
      if (capture !== active) return;
      if (data === "flushed") finishRecording(active);
      else if (data instanceof ArrayBuffer) captureChunk(active, data);
    };
    setStatus("recording");
  } catch {
    if (capture === active) {
      showError("microphone");
      setStatus(ready ? "ready" : "idle");
    }
  } finally {
    if (capture === active && !active.node) releaseCapture();
    starting = false;
    render();
  }
}

function finishRecording(active) {
  if (capture !== active) return;
  console.info("Microphone capture", {
    ...active.input, outputSampleRate: sampleRate, outputChannels: 1,
    chunks: active.chunks, bytes: active.bytes, sentChunks: sequence - active.startSequence,
    suppressedChunks: active.suppressedChunks + active.voiceFrames.length,
    rms: Math.sqrt(active.sumSquares / Math.max(1, active.bytes / 2)), peak: active.peak,
  });
  releaseCapture();
  if (sequence > active.startSequence && send({type: "end_utterance"})) {
    waiting = true;
    setStatus("processing");
  } else {
    setStatus(ready ? "ready" : "disconnected");
    if (ready) showError("noSpeech");
  }
}

function stopRecording() {
  if (!capture || capture.stopping) return;
  const active = capture;
  if (!active.node) { releaseCapture(); return; }
  active.stopping = true;
  active.node.port.postMessage("flush");
  active.flushTimer = setTimeout(() => finishRecording(active), 400);
  render();
}

function resetVisit() {
  clearTimeout(reconnectTimer);
  clearTimeout(handshakeTimer);
  const previous = socket;
  socket = null;
  previous?.close();
  releaseCapture();
  clearPlayback();
  transcriptElement.replaceChildren();
  visit = workflow = undefined;
  ready = wasReady = waiting = started = false;
  turn = mutedTurn = -1;
  errorKey = "";
  storeWorkflow();
  renderVisit();
  setStatus("idle");
}

startButton.addEventListener("click", startRecording);
stopButton.addEventListener("click", stopRecording);
interruptButton.addEventListener("click", interruptPlayback);
resetButton.addEventListener("click", resetVisit);
languageSelect.addEventListener("change", render);
window.addEventListener("online", () => {
  reconnectAttempts = 0;
  if (!ready && !socket && started) scheduleReconnect();
  else render();
});
window.addEventListener("offline", () => {
  if (capture || waiting) showError("lostRecording");
  releaseCapture();
  clearPlayback();
  waiting = false;
  socket?.close();
  setStatus("offline");
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
fetch("/runtime-mode", {cache: "no-store"}).then((response) => response.json())
  .then(({demo}) => { byId("demoMode").hidden = demo !== true; }).catch(() => {});
render();
// A reload restores the connection and draft. Audio needs a fresh user gesture.
if (workflow) {
  started = true;
  connect().catch(() => {});
}
