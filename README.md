# Vulcan OmniPro 220 Expert

A multimodal reasoning agent for the [Vulcan OmniPro 220](https://www.harborfreight.com/omnipro-220-industrial-multiprocess-welder-with-120240v-input-57812.html)
multiprocess welder, built on the **Claude Agent SDK**. Ask it anything a new owner would ask —
by text **or by voice** — and it answers with grounded facts from the 48-page manual, the actual
diagrams and photos from the documentation, and **interactive artifacts it generates on the fly**
(calculators, configurators, flowcharts) when words aren't the best medium.

> Built for the Prox founding-engineer challenge. Original challenge brief:
> [`CHALLENGE.md`](CHALLENGE.md).

## Quick start

```bash
git clone <this-repo>
cd prox-challenge
cp .env.example .env   # put your Anthropic API key in .env
npm install            # installs frontend (npm) + backend (pip) deps
npm run dev            # starts backend :3002 + frontend :3001
```

Open **http://localhost:3001**. First startup downloads a small (~80 MB) local embedding model;
after that it's instant. Requirements: Node 18+, Python 3.11+, and the
[Claude Code CLI](https://claude.com/claude-code) (`npm install -g @anthropic-ai/claude-code`) —
the Agent SDK uses it as its transport.

Try these:

- *"What's the duty cycle for MIG welding at 200A on 240V?"* → exact answer + the spec table image
- *"What polarity setup do I need for TIG welding?"* → the actual cable-connection diagram
- *"I'm getting porosity in my flux-cored welds"* → knowledge-graph-backed cause→fix walkthrough
- *"Build me a duty cycle calculator"* → a live interactive React widget, generated on the spot
- 🎤 Click the mic and *say* it — frustrated voices get calmer, shorter, step-at-a-time answers

## What makes it multimodal

**1. It surfaces the manual's own visuals.** 23 figures — wiring/polarity diagrams, the wire feed
mechanism, front panel controls, weld diagnosis photo charts, the process selection chart, the
parts diagram — were extracted from the PDFs at ingestion time, vision-captioned for retrieval,
and embedded in the same vector index as the text. When the manual's own diagram *is* the answer,
the agent shows it instead of describing it.

**2. It draws what doesn't exist.** A `render_artifact` tool lets the agent generate
self-contained HTML/SVG diagrams or interactive React components (duty-cycle calculators,
settings configurators, troubleshooting flowcharts), rendered live in a sandboxed iframe — the
same mechanism as Claude.ai Artifacts, reverse-engineered: the **tool call's input is the
artifact**; the backend forwards the generated code straight to the frontend, which renders it
with React 18 + Tailwind + Chart.js inside `sandbox="allow-scripts"`, with a postMessage
handshake for resizing and graceful error fallback.

**3. It knows the product video, down to the second.** The official overview video was ingested
too: frames sampled every 4s, near-duplicates dropped, 58 distinct moments vision-captioned with
timestamps and embedded in the same index. Ask "show me it in action" and the agent surfaces the
exact screenshot with a **▶ Play from 3:48** button that plays the video from that moment, right
in the chat (`scripts/ingest_video.py` + the `get_video_moment` tool).

**4. It hears how you say it, not just what you say.** Hitting the mic starts a **hands-free
conversation**: it detects when you've finished your question (silence endpointing via the Web
Audio analyser — no buttons), answers out loud, then listens again for your follow-up. Prosody
features (volume, speech rate, pitch variability, pauses) travel with each transcript, so the
agent adapts — frustrated users get calm, one-step-at-a-time answers; urgent ones get the fix
first — and it chooses a speaking register (`[[register:calm]]` etc., stripped server-side) that
shapes the voice delivery. Works with zero extra setup via browser speech; add an optional
`ELEVENLABS_API_KEY` to `.env` (free tier is fine) and replies come back in a natural human
voice with register-tuned expressiveness.

## Architecture

```
files/*.pdf ──► scripts/ingest.py ─────────────► backend/data/kb/  (committed)
                 │ pymupdf text + rasterize        ├ chunks.jsonl      141 text+caption chunks
                 │ Claude-vision transcription     ├ embeddings.npy    local MiniLM vectors
                 │   (26 table/infographic pages)  ├ images/*.png      23 cropped figures
                 │ Claude-vision figure captions   ├ figures.json      captions + metadata
                 └ scripts/build_graph.py ───────► ├ graph_nodes.json  254 nodes
                                                   └ graph_edges.json  343 edges

Browser (React/Vite :3001)          FastAPI (:3002)              Claude Agent SDK
┌──────────────────────┐  NDJSON   ┌──────────────────┐         ┌─────────────────────┐
│ chat / mic / TTS     │◄──stream──│ /api/chat        │◄─query──│ agent (Haiku)       │
│ image lightbox       │           │ /kb-images/*.png │         │  search_knowledge   │
│ sandboxed artifact   │           │ turn.py:         │         │  get_image          │
│   iframe             │           │  SDK msgs → typed│         │  render_artifact    │
└──────────────────────┘           │  content blocks  │         └─────────────────────┘
                                   └──────────────────┘
```

### Knowledge extraction (the part that matters most)

The manual is hostile to naive parsing: multi-column spec tables interleave when text-extracted,
five pages contain 100K+ characters of hidden duplicate text layers, and the most valuable
content (weld diagnosis photos, cable diagrams, the selection chart) is vector art or photos with
**zero** extractable text. The pipeline (`scripts/ingest.py`) handles this in layers:

1. **Text**: `pymupdf` extraction with unicode + whitespace normalization for prose pages.
2. **Vision transcription**: the 26 structurally complex pages (spec tables, troubleshooting
   matrices, infographics) are rasterized and transcribed to clean Markdown by Claude vision —
   the raw garbled text is included in the prompt so nothing is hallucinated, and the image
   resolves column order. Responses are content-hash cached so re-runs are free.
3. **Figures**: a hand-authored manifest (`figure_manifest.json`) defines 23 crops — hand-authored
   because automatic detection is unreliable here (vector-art diagrams have no embedded images to
   find). Each figure gets a Claude-vision retrieval caption naming every labeled component.
4. **One index for everything**: text chunks and figure captions are embedded together
   (`sentence-transformers/all-MiniLM-L6-v2`, locally — no second API key) so a single semantic
   search returns both relevant passages *and* relevant images. Brute-force numpy cosine over a
   few hundred vectors — a vector DB would be pure overhead here.
5. **Knowledge graph**: Claude structured-outputs extraction turns the troubleshooting matrices
   and spec/polarity facts into 254 typed nodes (symptom/cause/fix/setting/process/spec) with
   343 edges (`causes`, `fixed_by`, `applies_to`). `search_knowledge` keyword-matches node labels
   and expands one hop, so "porosity in flux-cored welds" pulls the complete cause→fix subgraph
   even where embedding similarity alone would miss it.

The ingested KB is **committed to git** — evaluators don't re-run ingestion, the demo is
deterministic, and clone-to-running stays under two minutes. The pipeline itself is fully
re-runnable (`python scripts/ingest.py`, `python scripts/build_graph.py`).

### The agent

Three custom MCP tools, registered via the SDK's `create_sdk_mcp_server`; all built-in tools
disabled (`tools=[]`, `strict_mcp_config=True`) — this agent has no business touching a
filesystem or shell:

| Tool | What it does |
|---|---|
| `search_knowledge` | Embeds the query, cosine search over text+caption chunks, plus knowledge-graph expansion. Results tell the agent which `figure_id`s are relevant. |
| `get_image` | Returns the figure to the agent as an image block (so it can reference details) while the streaming layer emits a static-URL image block to the UI. |
| `render_artifact` | Validates and acknowledges — the artifact code itself travels as the tool *input*, forwarded to the frontend for sandboxed rendering. |

The system prompt encodes the persona (competent garage owner, not a pro welder), a hard
"show, don't tell" policy, safety-critical polarity/duty-cycle facts (DCEN/DCEP per process —
the one place a small model slipped in testing), voice affect adaptation, and when to ask
clarifying questions instead of guessing.

Multi-turn state uses the SDK's session resume — the server keeps only a
`conversation_id → session_id` map. Responses stream as newline-delimited JSON blocks
(`text_delta` / `tool_status` / `image` / `artifact` / `voice_register` / `error` / `done`)
over a chunked POST — SSE can't carry a request body.

### Design decisions worth defending

- **Committed KB over ingest-at-startup**: determinism and the 2-minute rule beat purity.
- **Local embeddings over API embeddings**: the whole app runs on one `ANTHROPIC_API_KEY`.
- **numpy over FAISS/Chroma**: ~140 chunks. Sub-millisecond brute force, zero native-build risk.
- **Hand-authored figure manifest over automatic detection**: 23 curated crops beat heuristics
  on a corpus this small; the failure mode of missing a figure is silent and unacceptable.
- **Artifact-as-tool-input over artifact-as-tool-output**: mirrors how Claude.ai actually does
  it; the model generates code as arguments, nothing executes server-side.
- **Chart.js over Recharts in artifacts**: Recharts has no reliable UMD build for a
  script-tag-only sandbox.
- **Browser-native voice over hosted STT/TTS**: emotional intelligence comes from prosody
  features + prompt policy, not from a premium voice API — and setup stays friction-free.

## Model

Runs on `claude-haiku-4-5` by default (fast, cheap). Set `AGENT_MODEL=claude-sonnet-5` in `.env`
for noticeably stronger artifact generation and reasoning if cost isn't a concern.

## Project layout

```
scripts/ingest.py           PDF → knowledge base (text, figures, captions, embeddings)
scripts/build_graph.py      manual → knowledge graph (structured outputs)
scripts/render_pages.py     page PNGs for manifest authoring
backend/app/
  agent/system_prompt.md    persona, tool policy, safety facts, voice adaptation
  agent/tools/              search_knowledge · get_image · render_artifact
  agent/turn.py             SDK message stream → typed NDJSON content blocks
  retrieval/                embeddings index + knowledge graph lookup
  routes/                   /api/chat · /api/examples · /api/health
backend/data/kb/            the committed knowledge base
frontend/src/
  lib/artifactTemplate.ts   sandboxed-iframe srcDoc builder (React/Tailwind/Chart.js CDN)
  lib/voice.ts              mic capture + prosody analysis (Web Audio)
  lib/tts.ts                register-adaptive speech synthesis
  components/               chat thread, image lightbox, artifact iframe
```

## Verified against

The three challenge questions (duty cycle → exact spec + table image; porosity → graph-backed
cause/fix list; TIG polarity → correct sockets + the actual diagram), ambiguous questions
(clarifies instead of guessing), cross-referencing questions (process selection + setup spanning
three documents), artifact generation, and the voice affect test (same question asked frustrated
vs. neutral produces measurably different responses — shorter, calmer, one step at a time).
