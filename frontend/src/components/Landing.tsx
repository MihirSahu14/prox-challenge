import { useEffect, useState } from "react";

interface Props {
  onHelp: () => void;
}

const VIDEO_ID = "kxGDoGcnhBw";

const SPECS = [
  { value: "4-in-1", label: "MIG · Flux-Cored · TIG · Stick" },
  { value: "120/240V", label: "dual voltage input" },
  { value: "30–220A", label: "welding current range" },
  { value: "LCD", label: "synergic control system" },
];

const PROCESSES = [
  {
    name: "MIG",
    desc: "Fast, clean welds on steel and stainless. Easiest to learn — great for sheet metal and auto body.",
  },
  {
    name: "FLUX-CORED",
    desc: "No gas bottle needed. Ideal outdoors and forgiving on rusty or dirty steel.",
  },
  {
    name: "TIG",
    desc: "Highest quality, extremely clean welds with precise control. Bike frames, thin tube, metal art.",
  },
  {
    name: "STICK",
    desc: "Deep penetration for thicker material. Works outdoors, forgiving on dirty steel.",
  },
];

function VideoOverlay({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="video-overlay" onClick={onClose}>
      <div className="video-frame" onClick={(e) => e.stopPropagation()}>
        <button className="video-close" onClick={onClose} title="Close (Esc)">
          ✕
        </button>
        <iframe
          src={`https://www.youtube.com/embed/${VIDEO_ID}?autoplay=1&rel=0`}
          title="Vulcan OmniPro 220 — video overview"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    </div>
  );
}

export function Landing({ onHelp }: Props) {
  const [showVideo, setShowVideo] = useState(false);

  return (
    <div className="landing">
      <div className="hazard-stripe" />

      <nav className="landing-nav">
        <span className="brand">
          VULCAN <span className="brand-model">OMNIPRO 220</span>
        </span>
        <button className="help-btn" onClick={onHelp}>
          🔧 Expert Help
        </button>
      </nav>

      <section className="hero">
        <div className="hero-text">
          <p className="hero-kicker">INDUSTRIAL MULTIPROCESS WELDER</p>
          <h1>
            One machine.
            <br />
            <span className="accent">Every weld.</span>
          </h1>
          <p className="hero-sub">
            The Vulcan OmniPro 220 runs MIG, Flux-Cored, TIG, and Stick off 120V or 240V —
            with an LCD synergic control system that sets itself up around your material.
          </p>
          <div className="hero-actions">
            <button className="cta" onClick={onHelp}>
              Ask the Expert
            </button>
            <button className="cta-secondary" onClick={() => setShowVideo(true)}>
              ▶ Watch it in action
            </button>
          </div>
          <p className="cta-hint">
            Setup, settings, troubleshooting — answers straight from the manual, with the actual
            diagrams. Type it or say it.
          </p>
          <div className="spec-row">
            {SPECS.map((s) => (
              <div className="spec" key={s.value}>
                <span className="spec-value">{s.value}</span>
                <span className="spec-label">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="hero-image">
          <div className="hero-glow" />
          <img src="/product.webp" alt="Vulcan OmniPro 220 multiprocess welder" />
        </div>
      </section>

      <section className="processes">
        <h2>
          FOUR PROCESSES. <span className="accent">ZERO GUESSWORK.</span>
        </h2>
        <div className="process-grid">
          {PROCESSES.map((p) => (
            <div className="process-card" key={p.name}>
              <h3>{p.name}</h3>
              <p>{p.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="expert-banner">
        <div className="expert-banner-inner">
          <img src="/product-inside.webp" alt="OmniPro 220 wire feed compartment" />
          <div>
            <h2>
              STUCK? <span className="accent">THE EXPERT KNOWS THIS MACHINE.</span>
            </h2>
            <p>
              Duty cycles, polarity setups, wire tension, weld diagnosis — the built-in AI expert
              has read all 48 pages of the manual so you don't have to. It shows you the real
              diagrams, draws interactive calculators, and even listens when you'd rather talk
              than type.
            </p>
            <button className="cta" onClick={onHelp}>
              🔧 Get Expert Help
            </button>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="hazard-stripe" />
        <p>
          Vulcan OmniPro 220 · Item 57812 · Built for the Prox founding-engineer challenge —
          powered by the Claude Agent SDK
        </p>
      </footer>

      {showVideo && <VideoOverlay onClose={() => setShowVideo(false)} />}
    </div>
  );
}
