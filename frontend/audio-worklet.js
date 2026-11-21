class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.inputBuffer = [];
        this.outputBuffer = [];
        this.targetRate = 16000;
        this.outputFrameSize = 512;
        this.ratio = sampleRate / this.targetRate;
        this.position = 0;
    }

    process(inputs) {
        const input = inputs[0];

        if (!input || !input[0]) {
            return true;
        }

        const samples = input[0];

        for (let i = 0; i < samples.length; i++) {
            this.inputBuffer.push(samples[i]);
        }

        while (this.position + 1 < this.inputBuffer.length) {
            const index = Math.floor(this.position);
            const fraction = this.position - index;

            const sample =
                this.inputBuffer[index] * (1 - fraction) +
                this.inputBuffer[index + 1] * fraction;

            const clamped = Math.max(-1, Math.min(1, sample));

            this.outputBuffer.push(
                clamped < 0
                    ? Math.round(clamped * 32768)
                    : Math.round(clamped * 32767)
            );

            this.position += this.ratio;
        }

        const consumed = Math.floor(this.position);

        if (consumed > 0) {
            this.inputBuffer.splice(0, consumed);
            this.position -= consumed;
        }

        while (this.outputBuffer.length >= this.outputFrameSize) {
            const frame = this.outputBuffer.splice(
                0,
                this.outputFrameSize
            );

            const pcm = new Int16Array(frame);

            this.port.postMessage(pcm.buffer, [pcm.buffer]);
        }

        return true;
    }
}

registerProcessor("pcm-processor", PCMProcessor);
