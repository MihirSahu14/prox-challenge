export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_status"; tool: string; state: string; summary: string }
  | { type: "image"; figure_id: string; url: string; caption: string; source: string; page: number }
  | { type: "artifact"; id: string; title: string; artifact_type: "html" | "react"; code: string }
  | {
      type: "video_moment";
      frame_id: string;
      url: string;
      caption: string;
      timestamp: string;
      t_seconds: number;
      video_id: string;
      youtube_url: string;
    }
  | { type: "error"; message: string };

export interface ChatMessage {
  role: "user" | "assistant";
  blocks: ContentBlock[];
}
