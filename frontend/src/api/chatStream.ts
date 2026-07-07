export interface StreamBlock {
  type: string;
  [key: string]: unknown;
}

export async function* chatStream(
  message: string,
  conversationId: string | null,
  voiceMeta?: object | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamBlock> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      voice_meta: voiceMeta ?? null,
    }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line) as StreamBlock;
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer) as StreamBlock;
}
