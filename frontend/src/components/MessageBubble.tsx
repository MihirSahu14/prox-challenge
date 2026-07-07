import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types";
import { ArtifactBlock } from "./blocks/ArtifactBlock";
import { VideoMomentBlock } from "./blocks/VideoMomentBlock";

export function MessageBubble({ message }: { message: ChatMessage }) {
  return (
    <div className={`bubble ${message.role}`}>
      {message.blocks.map((b, i) => {
        switch (b.type) {
          case "text":
            return (
              <div className="md" key={i}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{b.text}</ReactMarkdown>
              </div>
            );
          case "tool_status":
            return (
              <div className="tool-status" key={i}>
                🔍 {b.summary}
              </div>
            );
          case "image":
            return <ManualImage key={i} url={b.url} caption={b.caption} source={b.source} page={b.page} />;
          case "artifact":
            return (
              <ArtifactBlock key={i} title={b.title} artifactType={b.artifact_type} code={b.code} />
            );
          case "video_moment":
            return (
              <VideoMomentBlock
                key={i}
                url={b.url}
                caption={b.caption}
                timestamp={b.timestamp}
                tSeconds={b.t_seconds}
                videoId={b.video_id}
                youtubeUrl={b.youtube_url}
              />
            );
          case "error":
            return (
              <div className="error-block" key={i}>
                ⚠ {b.message}
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

function ManualImage({
  url, caption, source, page,
}: { url: string; caption: string; source: string; page: number }) {
  const [zoomed, setZoomed] = useState(false);
  return (
    <figure className={`manual-image ${zoomed ? "zoomed" : ""}`} onClick={() => setZoomed(!zoomed)}>
      <img src={url} alt={caption} loading="lazy" />
      <figcaption>
        {caption} <span className="image-source">({source}, p.{page})</span>
      </figcaption>
    </figure>
  );
}
