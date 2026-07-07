export interface StreamBlock {
  type: string;
  [key: string]: unknown;
}

export function accessCodeHeader(): Record<string, string> {
  const code = localStorage.getItem("access_code");
  return code ? { "X-Access-Code": code } : {};
}

export async function* chatStream(
  message: string,
  conversationId: string | null,
  voiceMeta?: object | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamBlock> {
  const request = () =>
    fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...accessCodeHeader(),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        voice_meta: voiceMeta ?? null,
      }),
      signal,
    });

  let res = await request();
  // Hosted deployments may be gated: ask once, remember locally, retry.
  if (res.status === 401) {
    const code = window.prompt("This hosted demo is access-protected. Enter the access code:");
    if (code) {
      localStorage.setItem("access_code", code.trim());
      res = await request();
    }
  }
  if (res.status === 401) {
    localStorage.removeItem("access_code");
    throw new Error("Access code required (or incorrect) — send a message to try again.");
  }
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
