// Expressive speech output. The agent picks a register ([[register:x]] tag,
// stripped server-side into a voice_register block); delivery adapts to it.
//
// Engine selection: if the backend has an ELEVENLABS_API_KEY, /api/voice-config
// says "elevenlabs" and replies are spoken with a natural human voice via
// /api/tts. Otherwise (and on any failure) we fall back to the browser's
// speechSynthesis with the best available system voice.
//
// speak() resolves when playback finishes — the hands-free loop uses that to
// re-open the microphone.

export type Register = "calm" | "warm" | "brisk" | "neutral";

const DELIVERY: Record<Register, { rate: number; pitch: number }> = {
  calm: { rate: 0.9, pitch: 0.95 },
  warm: { rate: 0.98, pitch: 1.05 },
  brisk: { rate: 1.14, pitch: 1.0 },
  neutral: { rate: 1.0, pitch: 1.0 },
};

let engine: "elevenlabs" | "browser" | null = null;
let currentAudio: HTMLAudioElement | null = null;
let cancelled = false;
let cancelCurrent: (() => void) | null = null;

async function getEngine(): Promise<"elevenlabs" | "browser"> {
  if (engine) return engine;
  try {
    const res = await fetch("/api/voice-config");
    engine = (await res.json()).tts === "elevenlabs" ? "elevenlabs" : "browser";
  } catch {
    engine = "browser";
  }
  return engine;
}

/** Best available system voice, strongly preferring the natural-sounding ones. */
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = speechSynthesis.getVoices();
  const en = voices.filter((v) => v.lang.startsWith("en"));
  return (
    en.find((v) => /natural|neural/i.test(v.name)) ??
    en.find((v) => v.name === "Google US English") ??
    en.find((v) => /Google/i.test(v.name)) ??
    en.find((v) => /Aria|Jenny|Ryan|Sonia/i.test(v.name)) ??
    en.find((v) => v.lang === "en-US") ??
    en[0] ??
    null
  );
}

/** Strip markdown/emoji so the utterance doesn't read syntax aloud. */
function toSpeakable(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " (code shown on screen) ")
    .replace(/\|.*\|/g, " ")            // table rows
    .replace(/[#*_`>]/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

async function speakElevenLabs(text: string, register: Register): Promise<boolean> {
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, register }),
    });
    if (!res.ok) return false;
    const url = URL.createObjectURL(await res.blob());
    if (cancelled) {
      URL.revokeObjectURL(url);
      return true;
    }
    return await new Promise<boolean>((resolve) => {
      const audio = new Audio(url);
      currentAudio = audio;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        resolve(true);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(false);
      };
      audio.play().catch(() => resolve(false));
    });
  } catch {
    return false;
  }
}

function speakBrowser(text: string, register: Register): Promise<void> {
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    const delivery = DELIVERY[register];
    utterance.rate = delivery.rate;
    utterance.pitch = delivery.pitch;
    const voice = pickVoice();
    if (voice) utterance.voice = voice;
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    speechSynthesis.speak(utterance);
  });
}

/** Speak text; resolves when playback completes, fails, or is interrupted
 * (stopSpeaking — e.g. barge-in — resolves the pending promise immediately). */
export async function speak(text: string, register: Register = "neutral"): Promise<void> {
  stopSpeaking();
  cancelled = false;
  const clean = toSpeakable(text);
  if (!clean) return;
  const interrupted = new Promise<true>((resolve) => {
    cancelCurrent = () => resolve(true);
  });
  try {
    if ((await getEngine()) === "elevenlabs") {
      const done = await Promise.race([speakElevenLabs(clean, register), interrupted]);
      if (done || cancelled) return;
    }
    await Promise.race([speakBrowser(clean, register).then(() => true), interrupted]);
  } finally {
    cancelCurrent = null;
  }
}

export function stopSpeaking(): void {
  cancelled = true;
  cancelCurrent?.();
  cancelCurrent = null;
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  speechSynthesis.cancel();
}

// Voice list loads async in some browsers; warm it.
if (typeof speechSynthesis !== "undefined") {
  speechSynthesis.onvoiceschanged = () => pickVoice();
}
