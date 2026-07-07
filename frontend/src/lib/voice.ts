// Voice capture with prosody analysis.
//
// Runs SpeechRecognition (transcript) and Web Audio analysis (how it was said)
// in parallel. The prosody features — energy, speech rate, pitch statistics,
// pauses — are what let the agent respond to tone/frustration/urgency rather
// than just words. All browser-native: no second API key.

export interface VoiceMeta {
  duration_s: number;
  words_per_min: number;
  mean_volume: number; // 0..1 RMS, rough
  peak_volume: number;
  pitch_hz_mean: number;
  pitch_variability: number; // coefficient of variation of f0
  long_pauses: number; // pauses > 500ms mid-utterance
  hints: string; // derived, human-readable, e.g. "loud, fast, agitated"
}

export interface VoiceResult {
  transcript: string;
  meta: VoiceMeta;
}

type SpeechRecognitionCtor = new () => any;

export function speechSupported(): boolean {
  return Boolean(
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition,
  );
}

/** Autocorrelation pitch estimate; returns 0 when no clear pitch. */
function estimatePitch(buf: Float32Array, sampleRate: number): number {
  let rms = 0;
  for (let i = 0; i < buf.length; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / buf.length);
  if (rms < 0.015) return 0; // silence

  const minLag = Math.floor(sampleRate / 400); // 400 Hz max
  const maxLag = Math.floor(sampleRate / 70); // 70 Hz min
  let bestLag = 0;
  let bestCorr = 0;
  for (let lag = minLag; lag <= maxLag; lag++) {
    let corr = 0;
    for (let i = 0; i < buf.length - lag; i++) corr += buf[i] * buf[i + lag];
    if (corr > bestCorr) {
      bestCorr = corr;
      bestLag = lag;
    }
  }
  return bestLag ? sampleRate / bestLag : 0;
}

function deriveHints(m: Omit<VoiceMeta, "hints">): string {
  const hints: string[] = [];
  if (m.mean_volume > 0.09) hints.push("noticeably loud");
  else if (m.mean_volume < 0.025) hints.push("quiet/hesitant");
  if (m.words_per_min > 175) hints.push("speaking fast");
  else if (m.words_per_min > 0 && m.words_per_min < 100) hints.push("speaking slowly");
  if (m.pitch_variability > 0.28) hints.push("agitated/expressive pitch");
  else if (m.pitch_variability < 0.1 && m.pitch_hz_mean > 0) hints.push("flat/tired tone");
  if (m.long_pauses >= 2) hints.push("frequent pauses (possibly unsure)");
  return hints.length ? hints.join(", ") : "calm/neutral delivery";
}

// Auto-stop: once the user has spoken, this much continuous silence means the
// question is finished — no stop button needed. Long enough to survive natural
// mid-sentence pauses, short enough to feel responsive.
const AUTO_STOP_SILENCE_MS = 1800;
// If nothing is said at all, give up instead of listening forever.
const NO_SPEECH_TIMEOUT_MS = 10000;
// Barge-in: sustained voice at this level while the assistant is speaking
// interrupts it. Higher threshold + duration gate so the assistant's own
// audio (already reduced by echoCancellation) and ambient noise don't trigger.
const BARGE_IN_RMS = 0.022;
const BARGE_IN_SUSTAIN_MS = 250;

/**
 * Watches the mic while the assistant is speaking; fires onSpeech once when
 * the user starts talking over it (barge-in). echoCancellation keeps the
 * assistant's own voice out of the signal.
 */
export function monitorForSpeech(onSpeech: () => void): { stop: () => void } {
  let stopped = false;
  let stream: MediaStream | null = null;
  let ctx: AudioContext | null = null;
  let rafId = 0;

  const stop = () => {
    stopped = true;
    cancelAnimationFrame(rafId);
    stream?.getTracks().forEach((t) => t.stop());
    ctx?.close().catch(() => {});
  };

  navigator.mediaDevices
    .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    .then(async (s) => {
      if (stopped) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream = s;
      ctx = new AudioContext();
      // Created outside a user-gesture call stack, Chrome may start the
      // context suspended — the analyser would read silence forever and
      // barge-in would never fire.
      if (ctx.state === "suspended") await ctx.resume().catch(() => {});
      const source = ctx.createMediaStreamSource(s);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      let voicedMs = 0;
      let last = performance.now();

      const sample = () => {
        if (stopped) return;
        analyser.getFloatTimeDomainData(buf);
        let rms = 0;
        for (let i = 0; i < buf.length; i++) rms += buf[i] * buf[i];
        rms = Math.sqrt(rms / buf.length);
        const now = performance.now();
        const dt = now - last;
        last = now;
        if (rms > BARGE_IN_RMS) {
          voicedMs += dt;
          if (voicedMs > BARGE_IN_SUSTAIN_MS) {
            stop();
            onSpeech();
            return;
          }
        } else {
          voicedMs = Math.max(0, voicedMs - dt * 2); // decay, don't hard-reset
        }
        rafId = requestAnimationFrame(sample);
      };
      rafId = requestAnimationFrame(sample);
    })
    .catch(() => {}); // no mic monitor -> no barge-in, speaking still works

  return { stop };
}

export function startVoiceCapture(
  onInterim: (text: string) => void,
): { stop: () => void; result: Promise<VoiceResult | null> } {
  const Ctor: SpeechRecognitionCtor =
    (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  const recognition = new Ctor();
  recognition.lang = "en-US";
  recognition.interimResults = true;
  recognition.continuous = true;

  let transcript = "";
  let stopped = false;
  let audioCtx: AudioContext | null = null;
  let stream: MediaStream | null = null;
  let rafId = 0;

  // Prosody accumulators
  const volumes: number[] = [];
  const pitches: number[] = [];
  let longPauses = 0;
  let silenceMs = 0;
  let sawSpeech = false;
  let autoStopSilenceMs = 0; // separate counter: never reset to -Infinity
  const startedAt = performance.now();
  let lastSample = startedAt;

  const audioReady = navigator.mediaDevices
    .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    .then(async (s) => {
      stream = s;
      audioCtx = new AudioContext();
      // Later hands-free turns start outside a user-gesture call stack;
      // Chrome may suspend the context (silent analyser = broken endpointing).
      if (audioCtx.state === "suspended") await audioCtx.resume().catch(() => {});
      const source = audioCtx.createMediaStreamSource(s);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const buf = new Float32Array(analyser.fftSize);

      const sample = () => {
        if (stopped) return;
        analyser.getFloatTimeDomainData(buf);
        let rms = 0;
        for (let i = 0; i < buf.length; i++) rms += buf[i] * buf[i];
        rms = Math.sqrt(rms / buf.length);
        volumes.push(rms);

        const now = performance.now();
        const dt = now - lastSample;
        lastSample = now;
        if (rms < 0.012) {
          if (sawSpeech) {
            silenceMs += dt;
            autoStopSilenceMs += dt;
            if (silenceMs > 500) {
              longPauses++;
              silenceMs = -Infinity; // count each pause once
            }
            // Hands-free endpointing: the user finished their question.
            if (autoStopSilenceMs > AUTO_STOP_SILENCE_MS) {
              recognition.stop();
              return;
            }
          } else if (now - startedAt > NO_SPEECH_TIMEOUT_MS) {
            recognition.stop();
            return;
          }
        } else {
          sawSpeech = true;
          silenceMs = 0;
          autoStopSilenceMs = 0;
          const pitch = estimatePitch(buf, audioCtx!.sampleRate);
          if (pitch > 0) pitches.push(pitch);
        }
        rafId = requestAnimationFrame(sample);
      };
      rafId = requestAnimationFrame(sample);
    })
    .catch(() => {
      // No analyser => no silence-based endpointing. Safety net so hands-free
      // mode can't listen forever: hard-stop after the no-speech timeout.
      setTimeout(() => {
        if (!stopped) recognition.stop();
      }, NO_SPEECH_TIMEOUT_MS + 5000);
    });

  const result = new Promise<VoiceResult | null>((resolve) => {
    recognition.onresult = (event: any) => {
      let interim = "";
      transcript = "";
      for (const r of event.results) {
        if (r.isFinal) transcript += r[0].transcript;
        else interim += r[0].transcript;
      }
      onInterim(transcript + interim);
    };
    recognition.onerror = () => finish();
    recognition.onend = () => finish();

    async function finish() {
      if (stopped) return;
      stopped = true;
      cancelAnimationFrame(rafId);
      await audioReady;
      stream?.getTracks().forEach((t) => t.stop());
      audioCtx?.close().catch(() => {});

      const text = transcript.trim();
      if (!text) return resolve(null);

      const duration = (performance.now() - startedAt) / 1000;
      const voiced = volumes.filter((v) => v > 0.012);
      const meanVol = voiced.length
        ? voiced.reduce((a, b) => a + b, 0) / voiced.length
        : 0;
      const pitchMean = pitches.length
        ? pitches.reduce((a, b) => a + b, 0) / pitches.length
        : 0;
      const pitchStd = pitches.length
        ? Math.sqrt(
            pitches.reduce((a, p) => a + (p - pitchMean) ** 2, 0) / pitches.length,
          )
        : 0;
      const base = {
        duration_s: Math.round(duration * 10) / 10,
        words_per_min: duration > 0.5
          ? Math.round(text.split(/\s+/).length / (duration / 60))
          : 0,
        mean_volume: Math.round(meanVol * 1000) / 1000,
        peak_volume: Math.round(Math.max(0, ...volumes) * 1000) / 1000,
        pitch_hz_mean: Math.round(pitchMean),
        pitch_variability: pitchMean
          ? Math.round((pitchStd / pitchMean) * 100) / 100
          : 0,
        long_pauses: longPauses,
      };
      resolve({ transcript: text, meta: { ...base, hints: deriveHints(base) } });
    }
  });

  recognition.start();
  return { stop: () => recognition.stop(), result };
}
