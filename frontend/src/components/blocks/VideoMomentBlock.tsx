import { useState } from "react";

interface Props {
  url: string;
  caption: string;
  timestamp: string;
  tSeconds: number;
  videoId: string;
  youtubeUrl: string;
}

export function VideoMomentBlock({ url, caption, timestamp, tSeconds, videoId, youtubeUrl }: Props) {
  const [playing, setPlaying] = useState(false);

  return (
    <div className="video-moment">
      {playing ? (
        <div className="video-moment-player">
          <iframe
            src={`https://www.youtube.com/embed/${videoId}?start=${tSeconds}&autoplay=1&rel=0`}
            title={`Product video from ${timestamp}`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      ) : (
        <button className="video-moment-still" onClick={() => setPlaying(true)}>
          <img src={url} alt={caption} loading="lazy" />
          <span className="video-moment-play">
            ▶ Play from {timestamp}
          </span>
        </button>
      )}
      <figcaption>
        📹 {timestamp} — {caption}{" "}
        <a href={youtubeUrl} target="_blank" rel="noreferrer">
          open on YouTube ↗
        </a>
      </figcaption>
    </div>
  );
}
