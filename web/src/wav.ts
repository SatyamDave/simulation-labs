// Client-side WAV encoding for the spoken-question flow (/ask-audio).
// MediaRecorder yields webm/opus, which the backend's STT can't ingest — so we
// decode it with the Web Audio API and re-encode as mono PCM16 WAV here.
// No dependencies: the RIFF header is 44 bytes of DataView writes.

/** Decode any browser-recorded audio blob (webm/opus, ogg, mp4…) and re-encode
 * it as a mono 16-bit PCM WAV blob ready for `POST /runs/{id}/ask-audio`. */
export async function blobToWav(blob: Blob): Promise<Blob> {
  const bytes = await blob.arrayBuffer();
  const ctx = new AudioContext();
  try {
    const audio = await ctx.decodeAudioData(bytes);
    return encodeWavPcm16(audio);
  } finally {
    void ctx.close();
  }
}

/** Encode an AudioBuffer as mono PCM16 WAV (channels averaged down). */
export function encodeWavPcm16(audio: AudioBuffer): Blob {
  const { numberOfChannels, length, sampleRate } = audio;

  // Downmix to mono: average every channel per sample.
  const mono = new Float32Array(length);
  for (let ch = 0; ch < numberOfChannels; ch++) {
    const data = audio.getChannelData(ch);
    for (let i = 0; i < length; i++) mono[i] += data[i] / numberOfChannels;
  }

  const bytesPerSample = 2;
  const dataSize = mono.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };

  // RIFF/WAVE header — PCM, 1 channel, 16-bit.
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // audio format: PCM
  view.setUint16(22, 1, true); // channels: mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, dataSize, true);

  // Samples: clamp to [-1, 1] and scale to int16.
  let offset = 44;
  for (let i = 0; i < mono.length; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: "audio/wav" });
}
