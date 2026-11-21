
const statusElement = document.getElementById("status");
const transcriptElement = document.getElementById("transcript");
const startButton = document.getElementById("startBtn");
const stopButton = document.getElementById("stopBtn");
const languageSelect = document.getElementById("language");

let socket = null;

// Register the service worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      await navigator.serviceWorker.register("./sw.js");
      console.log("Service worker registered");
    } catch (error) {
      console.error("Service worker registration failed:", error);
    }
  });
}

// Initial status
statusElement.textContent = "Ready to connect";
stopButton.disabled = true;

// Connect to the backend
function startSession() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    return;
  }

  statusElement.textContent = "Connecting to backend...";

  socket = new WebSocket("ws://localhost:8000/ws");

  socket.onopen = () => {
    const sessionMessage = {
      type: "start",
      language: languageSelect.value,
      session_id: "demo-session"
    };

    socket.send(JSON.stringify(sessionMessage));
    statusElement.textContent = "Session request sent";
    startButton.disabled = true;
    stopButton.disabled = false;
  };

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    console.log("Backend message:", message);

    if (message.type === "ready") {
      statusElement.textContent = "Connected and ready";
    } else if (message.type === "transcript") {
      transcriptElement.textContent = message.text;
    } else if (message.type === "error") {
      statusElement.textContent = message.message || "Backend error";
    }
  };

  socket.onerror = () => {
    statusElement.textContent = "Connection error";
  };

  socket.onclose = () => {
    statusElement.textContent = "Disconnected";
    startButton.disabled = false;
    stopButton.disabled = true;
  };
}

// Stop the session
function stopSession() {
  if (socket) {
    socket.close();
    socket = null;
  }

  statusElement.textContent = "Session stopped";
  startButton.disabled = false;
  stopButton.disabled = true;
}

startButton.addEventListener("click", startSession);
stopButton.addEventListener("click", stopSession);

console.log("Voice Field Register frontend loaded");
