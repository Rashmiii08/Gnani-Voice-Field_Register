
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
  }

  process(inputs, outputs) {
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
        this.nextSamplePosition = 0;
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

        this.nextSamplePosition += step;
      }

      this.previousSample = currentSample;
      this.inputPosition++;

      if (this.outputSamples.length >= this.chunkSize) {
        const chunk = new Int16Array(this.outputSamples);

        this.port.postMessage(chunk.buffer, [chunk.buffer]);

        this.outputSamples = [];
      }
    }

    return true;
  }
}

registerProcessor("audio-processor", AudioProcessor);
