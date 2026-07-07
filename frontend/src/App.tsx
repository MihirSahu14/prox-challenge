import { FormEvent, useEffect, useRef, useState } from "react";
import { chatStream } from "./api/chatStream";
import { Landing } from "./components/Landing";
import { MessageBubble } from "./components/MessageBubble";
import { monitorForSpeech, speechSupported, startVoiceCapture, VoiceMeta } from "./lib/voice";
import { Register, speak, stopSpeaking } from "./lib/tts";
import type { ChatMessage, ContentBlock } from "./types";

export default function App() {
  const [view, setView] = useState<"landing" | "chat">("landing");
  if (view === "landing") {
    return <Landing onHelp={() => setView("chat")} />;
  }
  return <ChatView onBack={() => setView("landing")} />;
}

function ChatView({ onBack }: { onBack: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [examples, setExamples] = useState<string[]>([]);
  // Hands-free voice conversation: idle -> listening -> thinking -> speaking -> listening...
  const [voiceState, setVoiceState] = useState<"off" | "listening" | "thinking" | "speaking">("off");
  const conversationId = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const captureRef = useRef<{ stop: () => void } | null>(null);
  const voiceOn = useRef(false); // ref twin of voiceState for async loops
  const micSupported = useRef(speechSupported());

  useEffect(() => {
    fetch("/api/examples")
      .then((r) => r.json())
      .then((d) => setExamples(d.examples))
      .catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string, voiceMeta: VoiceMeta | null = null) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setInput("");
    stopSpeaking();
    setMessages((m) => [
      ...m,
      { role: "user", blocks: [{ type: "text", text }] },
      { role: "assistant", blocks: [] },
    ]);

    const appendBlock = (block: ContentBlock) =>
      setMessages((m) => {
        const copy = [...m];
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = { ...last, blocks: [...last.blocks, block] };
        return copy;
      });

    const appendText = (text: string) =>
      setMessages((m) => {
        const copy = [...m];
        const last = copy[copy.length - 1];
        const blocks = [...last.blocks];
        const tail = blocks[blocks.length - 1];
        if (tail?.type === "text") {
          blocks[blocks.length - 1] = { type: "text", text: tail.text + text };
        } else {
          blocks.push({ type: "text", text });
        }
        copy[copy.length - 1] = { ...last, blocks };
        return copy;
      });

    let spokenText = "";
    let register: Register = "neutral";

    try {
      for await (const block of chatStream(text, conversationId.current, voiceMeta)) {
        switch (block.type) {
          case "session":
            conversationId.current = block.conversation_id as string;
            break;
          case "voice_register":
            register = block.register as Register;
            break;
          case "text_delta":
            appendText(block.text as string);
            spokenText += block.text as string;
            break;
          case "tool_status":
          case "image":
          case "artifact":
          case "video_moment":
          case "error":
            appendBlock(block as unknown as ContentBlock);
            break;
        }
      }
      if (voiceMeta && spokenText && voiceOn.current) {
        setVoiceState("speaking");
        // Barge-in: if the user starts talking over the answer, cut the audio
        // and fall straight through to the next listening turn.
        const monitor = monitorForSpeech(() => stopSpeaking());
        try {
          await speak(spokenText, register); // resolves on finish OR interrupt
        } finally {
          monitor.stop();
        }
      }
    } catch (err) {
      appendBlock({ type: "error", message: String(err) });
    } finally {
      setBusy(false);
    }
  }

  /** One hands-free cycle: listen -> send -> speak -> (loop). */
  async function voiceCycle() {
    while (voiceOn.current) {
      setVoiceState("listening");
      setInput("");
      const capture = startVoiceCapture((interim) => setInput(interim));
      captureRef.current = capture;
      const res = await capture.result.catch(() => null);
      if (!voiceOn.current) break;
      if (!res) {
        // Heard nothing — exit hands-free rather than looping forever.
        stopVoiceMode();
        break;
      }
      setInput("");
      setVoiceState("thinking");
      await send(res.transcript, res.meta);
      // send() handled the speaking phase; loop back to listening.
    }
    if (!voiceOn.current) setVoiceState("off");
  }

  function stopVoiceMode() {
    voiceOn.current = false;
    captureRef.current?.stop();
    stopSpeaking();
    setVoiceState("off");
    setInput("");
  }

  function toggleVoiceMode() {
    if (voiceOn.current) {
      stopVoiceMode();
      return;
    }
    stopSpeaking();
    voiceOn.current = true;
    void voiceCycle();
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="chat-page">
      <div className="hazard-stripe" />

      <nav className="chat-nav">
        <div className="chat-nav-left">
          <button className="back-btn" onClick={onBack} title="Back to product page">
            ←
          </button>
          <div>
            <span className="brand">
              VULCAN OMNIPRO 220 <span className="brand-model">EXPERT</span>
            </span>
            <p className="chat-nav-sub">MIG · Flux-Cored · TIG · Stick — answers from the manual</p>
          </div>
        </div>
        {voiceState !== "off" && (
          <button className="voice-status" onClick={stopVoiceMode} title="Exit voice mode">
            {voiceState === "listening" && <>🎙 listening… <span className="voice-exit">✕</span></>}
            {voiceState === "thinking" && <>⚙ thinking… <span className="voice-exit">✕</span></>}
            {voiceState === "speaking" && <>🔊 speaking… <span className="voice-exit">✕</span></>}
          </button>
        )}
      </nav>

      <div className="app">
        <div className="chat" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="empty-state">
              <p className="hero-kicker">EXPERT SUPPORT</p>
              <h2>
                WHAT'S STOPPING <span className="accent">YOUR WELD?</span>
              </h2>
              <p className="empty-sub">
                Setup, settings, troubleshooting — type it or hit the mic and say it. The expert
                answers with the manual's own diagrams and builds interactive tools when it helps.
              </p>
              <div className="examples">
                {examples.map((ex) => (
                  <button key={ex} onClick={() => send(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
          ))}
          {busy && (
            <div className="typing">
              <span className="spark" /> working on it…
            </div>
          )}
        </div>

        <form className="composer" onSubmit={onSubmit}>
          {micSupported.current && (
            <button
              type="button"
              className={`mic ${voiceState === "listening" ? "listening" : ""} ${
                voiceState !== "off" ? "active" : ""
              }`}
              onClick={toggleVoiceMode}
              title={
                voiceState === "off"
                  ? "Start hands-free voice conversation"
                  : "Exit voice mode"
              }
            >
              {voiceState === "off" ? "🎤" : "◼"}
            </button>
          )}
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              voiceState === "listening"
                ? "Listening — just talk, it sends when you pause…"
                : voiceState === "thinking"
                  ? "Thinking…"
                  : voiceState === "speaking"
                    ? "Speaking — it'll listen again when done"
                    : "e.g. What polarity do I need for flux-cored welding?"
            }
            disabled={busy || voiceState !== "off"}
          />
          <button type="submit" disabled={busy || voiceState !== "off" || !input.trim()}>
            SEND
          </button>
        </form>
      </div>
    </div>
  );
}
