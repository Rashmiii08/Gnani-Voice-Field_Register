/* Run with the scripted FastAPI entry point and Chromium's fake microphone. */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { mkdtempSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");

function writeSyntheticMicrophone(path) {
  const rate = 48000;
  const bytes = rate * 3 * 2;
  const wav = Buffer.alloc(44 + bytes);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24);
  wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(bytes, 40);
  for (let sample = 0; sample < bytes / 2; sample++) {
    wav.writeInt16LE(Math.round(2400 * Math.sin(2 * Math.PI * 440 * sample / rate)), 44 + sample * 2);
  }
  writeFileSync(path, wav);
}

async function main() {
  const baseURL = process.env.FIELD_REGISTER_URL || "http://127.0.0.1:8765";
  const temp = mkdtempSync(join(tmpdir(), "voice-register-"));
  const microphone = join(temp, "synthetic-mic.wav");
  let browser;
  try {
    writeSyntheticMicrophone(microphone);
    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        `--use-file-for-fake-audio-capture=${microphone}`,
      ],
    });
    const context = await browser.newContext({
      viewport: { width: 360, height: 780 }, permissions: ["microphone"],
    });
    const page = await context.newPage();
    await page.addInitScript(() => {
      window.audioCalls = { start: 0, stop: 0 };
      const originalStart = AudioBufferSourceNode.prototype.start;
      const originalStop = AudioBufferSourceNode.prototype.stop;
      AudioBufferSourceNode.prototype.start = function (...args) {
        window.audioCalls.start++;
        return originalStart.apply(this, args);
      };
      AudioBufferSourceNode.prototype.stop = function (...args) {
        window.audioCalls.stop++;
        return originalStop.apply(this, args);
      };
      const NativeSocket = WebSocket;
      window.WebSocket = class extends NativeSocket {
        constructor(...args) { super(...args); window.testSocket = this; }
      };
    });
    const sent = [];
    const received = [];
    const browserErrors = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("websocket", (socket) => {
      socket.on("framesent", ({payload}) => sent.push(JSON.parse(payload)));
      socket.on("framereceived", ({payload}) => received.push(JSON.parse(payload)));
    });

    await page.goto(baseURL);
    await page.getByRole("heading", { name: "Voice Field Register" }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByText("Simulation.", {exact: false}).waitFor();
    await page.getByRole("button", { name: "Start Recording" }).click();
    await page.waitForFunction(() => document.querySelector("#status").textContent === "Recording…");
    await page.waitForFunction(() => window.audioCalls.start > 0 && document.querySelector("#interruptBtn").disabled);
    await page.waitForTimeout(350);
    await page.getByRole("button", { name: "Stop Recording" }).click();
    const firstVisitId = page.getByText(/^DEMO-00[12]$/);
    await firstVisitId.waitFor();
    const firstIdentifier = await firstVisitId.textContent();
    const secondIdentifier = firstIdentifier === "DEMO-001" ? "DEMO-002" : "DEMO-001";
    await page.getByText("[Synthetic fixture] Asha Sharma").waitFor();
    assert.equal(sent[0].type, "start");
    assert.equal(sent[0].language, "en");
    assert.match(sent[0].session_id, /^[0-9a-f-]{36}$/i);
    assert.deepEqual(received[0], { type: "ready", session_id: sent[0].session_id });
    assert(sent.some((frame) => frame.type === "end_utterance"));
    const audio = sent.filter((frame) => frame.type === "audio");
    assert(audio.length >= 2);
    audio.forEach((frame, index) => assert.equal(frame.seq, index + 1));
    const pcm = Buffer.from(audio[0].data, "base64");
    assert.equal(pcm.length, 3200);
    assert.notEqual(pcm.toString("ascii", 0, 4), "RIFF");
    let zeroCrossings = 0;
    for (let i = 2; i < pcm.length; i += 2) {
      if (pcm.readInt16LE(i - 2) <= 0 && pcm.readInt16LE(i) > 0) zeroCrossings++;
    }
    assert(zeroCrossings >= 40 && zeroCrossings <= 48, `Unexpected 440 Hz PCM crossings: ${zeroCrossings}`);

    await page.getByRole("button", { name: "Interrupt playback" }).click();
    assert(sent.some((frame) => frame.type === "interrupt"));
    assert(await page.evaluate(() => window.audioCalls.stop > 0));
    await page.evaluate(() => window.testSocket.close(4000, "Test reconnect"));
    await page.waitForFunction(() => document.querySelector("#status").textContent === "Reconnecting…");
    await page.getByText("Connected and ready", { exact: true }).waitFor();
    const resume = sent.find((frame) => frame.type === "resume");
    assert.deepEqual(resume, {type: "resume", session_id: sent[0].session_id, draft_version: 1});
    assert(await page.getByText(firstIdentifier, { exact: true }).isVisible());

    const store = await page.evaluate(() => ({
      local: {...localStorage}, workflow: JSON.parse(sessionStorage.getItem("voice-register-workflow")),
    }));
    assert.deepEqual(store.local, {});
    assert.deepEqual(Object.keys(store.workflow).sort(), ["language", "session_id"]);
    assert(!JSON.stringify(store).includes("Asha Sharma"));

    await page.getByRole("button", { name: "New visit" }).click();
    assert.equal(await page.getByText(firstIdentifier, { exact: true }).count(), 0);
    await page.getByRole("button", { name: "Start Recording" }).click();
    await page.getByText("Recording…", { exact: true }).waitFor();
    await page.waitForTimeout(1100);
    await page.getByRole("button", { name: "Stop Recording" }).click();
    await page.getByText(secondIdentifier, { exact: true }).waitFor();
    await page.getByText("[Synthetic fixture] Asha Sharma", { exact: true }).waitFor();
    assert.equal(await page.getByText(firstIdentifier, { exact: true }).count(), 0);
    assert.notEqual(sent.filter((frame) => frame.type === "start")[1].session_id, sent[0].session_id);
    assert(await page.getByText("Awaiting confirmation.", { exact: false }).isVisible());

    await page.getByRole("button", { name: "New visit" }).click();
    await page.selectOption("#language", "hi");
    await page.getByRole("button", { name: "रिकॉर्डिंग शुरू करें" }).click();
    await page.getByText("रिकॉर्डिंग जारी है…", {exact: true}).waitFor();
    await page.waitForTimeout(1100);
    await page.getByRole("button", { name: "रिकॉर्डिंग रोकें" }).click();
    await page.getByText("[Synthetic fixture] आशा शर्मा").waitFor();
    assert.equal(sent.filter((frame) => frame.type === "start").at(-1).language, "hi");
    await page.getByRole("button", { name: "नई विज़िट" }).click();
    assert.equal(await page.evaluate(() => sessionStorage.getItem("voice-register-workflow")), null);
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
    await context.setOffline(true);
    await page.reload({ waitUntil: "load" });
    await page.getByRole("heading", { name: "Voice Field Register" }).waitFor();
    assert(await page.getByText("Offline. Recording requires a connection.", { exact: true }).isVisible());
    assert(await page.getByRole("button", { name: "Start Recording" }).isDisabled());
    assert.deepEqual(browserErrors, []);

    const denied = await browser.newPage();
    await denied.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = async () => { throw new DOMException("Denied", "NotAllowedError"); };
    });
    await denied.goto(baseURL);
    await denied.getByRole("button", {name: "Start Recording"}).click();
    await denied.getByText("Microphone unavailable.", {exact: false}).waitFor();
    assert(await denied.getByRole("button", {name: "Start Recording"}).isEnabled());
    console.log("PASS: localhost Chromium, PCM capture, transcript, playback, interruption, reconnect, patient separation, Hindi UI, offline shell");
  } finally {
    await browser?.close();
    rmSync(temp, {recursive: true, force: true});
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
