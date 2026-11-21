
const statusElement = document.getElementById("status");
const transcriptElement = document.getElementById("transcript");
const startButton = document.getElementById("startBtn");
const stopButton = document.getElementById("stopBtn");
const languageSelect = document.getElementById("language");

// Register the service worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      await navigator.serviceWorker.register("./sw.js");
      console.log("Service worker registered successfully");
    } catch (error) {
      console.error("Service worker registration failed:", error);
    }
  });
}

// Initial interface status
statusElement.textContent = "Ready to connect";

startButton.addEventListener("click", () => {
  statusElement.textContent = "Waiting for backend connection...";
});

stopButton.addEventListener("click", () => {
  statusElement.textContent = "Recording stopped";
});

console.log("Voice Field Register frontend loaded");
