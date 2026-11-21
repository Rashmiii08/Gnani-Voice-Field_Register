const connectBtn = document.getElementById("connectBtn");
const micBtn = document.getElementById("micBtn");
const stopBtn = document.getElementById("stopBtn");
const languageSelect = document.getElementById("language");
const statusText = document.getElementById("status");
const conversation = document.getElementById("conversation");
const visitDetails = document.getElementById("visitDetails");
const dangerStatus = document.getElementById("dangerStatus");

let socket = null;
let micStream = null;
let micContext = null;
let micSource = null;
let workletNode = null;
let playbackContext = null;
let nextPlayTime = 0;
let activeSources = [];
let isRecording = false;

function addMessage(label, message) {
    const paragraph = document.createElement("p");
    paragraph.textContent = `${label}: ${message}`;
    conversation.appendChild(paragraph);
}

function setStatus(message) {
    statusText.textContent = message;
}

function sendAudioFrame(buffer) {
    if (!socket || socket.readyState !== WebSocket.OPEN || !isRecording) {
        return;
    }

    const bytes = new Uint8Array(buffer);
    let binary = "";

    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }

    socket.send(JSON.stringify({
        type: "audio",
        data: btoa(binary)
    }));
}

async function startMicrophone() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        setStatus("Connect first.");
        return;
    }

    try {
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        micContext = new AudioContext();
        await micContext.audioWorklet.addModule("/audio-worklet.js");

        micSource = micContext.createMediaStreamSource(micStream);
        workletNode = new AudioWorkletNode(micContext, "pcm-processor");

        workletNode.port.onmessage = (event) => {
            sendAudioFrame(event.data);
        };

        micSource.connect(workletNode);
        workletNode.connect(micContext.destination);

        isRecording = true;
        micBtn.disabled = true;
        stopBtn.disabled = false;
        setStatus("Listening... Speak now.");

    } catch (error) {
        console.error(error);
        setStatus("Microphone could not start. Check browser permission.");
        await stopMicrophone();
    }
}

async function stopMicrophone() {
    isRecording = false;

    if (workletNode) {
        workletNode.port.onmessage = null;
        workletNode.disconnect();
        workletNode = null;
    }

    if (micSource) {
        micSource.disconnect();
        micSource = null;
    }

    if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
        micStream = null;
    }

    if (micContext) {
        await micContext.close();
        micContext = null;
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "end_utterance" }));
    }

    micBtn.disabled = !socket || socket.readyState !== WebSocket.OPEN;
    stopBtn.disabled = true;
    setStatus("Processing your speech...");
}

async function playAudio(base64Audio) {
    try {
        if (!playbackContext) {
            playbackContext = new AudioContext({ sampleRate: 24000 });
        }

        await playbackContext.resume();

        const binary = atob(base64Audio);
        const samples = new Int16Array(binary.length / 2);

        for (let i = 0; i < samples.length; i++) {
            const low = binary.charCodeAt(i * 2);
            const high = binary.charCodeAt(i * 2 + 1);
            let value = (high << 8) | low;

            if (value >= 32768) {
                value -= 65536;
            }

            samples[i] = value;
        }

        const audioBuffer = playbackContext.createBuffer(
            1,
            samples.length,
            24000
        );

        const channel = audioBuffer.getChannelData(0);

        for (let i = 0; i < samples.length; i++) {
            channel[i] = samples[i] / 32768;
        }

        const source = playbackContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(playbackContext.destination);

        const startAt = Math.max(
            playbackContext.currentTime,
            nextPlayTime
        );

        source.start(startAt);
        nextPlayTime = startAt + audioBuffer.duration;

        activeSources.push(source);

        source.onended = () => {
            activeSources = activeSources.filter(item => item !== source);
        };

    } catch (error) {
        console.error("Audio playback error:", error);
    }
}

function stopPlayback() {
    for (const source of activeSources) {
        try {
            source.stop();
        } catch {}
    }

    activeSources = [];

    if (playbackContext) {
        nextPlayTime = playbackContext.currentTime;
    }
}

connectBtn.addEventListener("click", () => {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/ws/voice`);

    setStatus("Connecting...");

    socket.onopen = () => {
        socket.send(JSON.stringify({
            type: "start",
            language: languageSelect.value
        }));
    };

    socket.onmessage = async (event) => {
        if (typeof event.data !== "string") return;

        let message;

        try {
            message = JSON.parse(event.data);
        } catch {
            return;
        }

        if (message.type === "ready") {
            setStatus("Connected and ready.");
            micBtn.disabled = false;
            connectBtn.disabled = true;
        }

        if (message.type === "transcript") {
            if (message.final) {
                addMessage("You", message.text || "");
            }
        }

        if (message.type === "response_text" || message.type === "say") {
            addMessage("Gnani", message.text || "");
        }

        if (message.type === "audio") {
            await playAudio(message.data || "");
        }

        if (message.type === "update") {
            visitDetails.textContent = JSON.stringify(
                message.form || {},
                null,
                2
            );

            dangerStatus.textContent = message.danger_flag
                ? "Safety alert: Please follow the referral guidance."
                : "No safety alert reported.";

            if (!isRecording) {
                micBtn.disabled = false;
                stopBtn.disabled = true;
                setStatus("Ready for the next response.");
            }
        }

        if (message.type === "interrupted") {
            stopPlayback();
            setStatus("Audio interrupted.");
        }

        if (message.type === "error") {
            setStatus(message.message || "Connection error");
        }
    };

    socket.onclose = async () => {
        await stopMicrophone();
        setStatus("Disconnected.");
        micBtn.disabled = true;
        stopBtn.disabled = true;
        connectBtn.disabled = false;
    };

    socket.onerror = () => {
        setStatus("Connection error.");
    };
});

micBtn.addEventListener("click", startMicrophone);

stopBtn.addEventListener("click", stopMicrophone);

if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js").catch(() => {});
    });
}
