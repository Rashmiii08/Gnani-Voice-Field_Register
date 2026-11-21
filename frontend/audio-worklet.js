
class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    this.targetRate = 16000;
    this.nextSamplePosition = 0;
    this.inputPosition = 0;
    this.previousSample = 0;
    this.hasPreviousSample = false;

    this.outputSamples = [];
    this.chunkSize = 1600;
    this.active = true;
    this.port.onmessage = ({data}) => {
      if (data === "flush") {
        this.active = false;
        if (this.outputSamples.length) this.sendChunk();
        this.port.postMessage("flushed");
      }
    };
  }

  sendChunk() {
    const buffer = new ArrayBuffer(this.outputSamples.length * 2);
    const pcm = new DataView(buffer);
    this.outputSamples.forEach((value, index) => pcm.setInt16(index * 2, value, true));
    this.port.postMessage(buffer, [buffer]);
    this.outputSamples = [];
  }

  process(inputs) {
    if (!this.active) return true;
    const input = inputs[0];

    if (!input || !input[0]) {
      return true;
    }

    const channel = input[0];
    const step = sampleRate / this.targetRate;

    for (let i = 0; i < channel.length; i++) {
      const currentSample = channel[i];
      const currentPosition = this.inputPosition;

      if (!this.hasPreviousSample) {
        this.previousSample = currentSample;
        this.hasPreviousSample = true;
        this.inputPosition++;
        const clipped = Math.max(-1, Math.min(1, currentSample));
        this.outputSamples.push(Math.round(clipped * (clipped < 0 ? 32768 : 32767)));
        this.nextSamplePosition = step;
        continue;
      }

      while (this.nextSamplePosition <= currentPosition) {
        const fraction =
          this.nextSamplePosition - (currentPosition - 1);

        const sample =
          this.previousSample +
          (currentSample - this.previousSample) * fraction;

        const clipped = Math.max(-1, Math.min(1, sample));

        const pcmSample =
          clipped < 0
            ? clipped * 32768
            : clipped * 32767;

        this.outputSamples.push(Math.round(pcmSample));
        if (this.outputSamples.length === this.chunkSize) this.sendChunk();
        this.nextSamplePosition += step;
      }

      this.previousSample = currentSample;
      this.inputPosition++;

    }

    return true;
  }
}

registerProcessor("audio-processor", AudioProcessor);
