import { useEffect, useRef, useState } from "react";
import { buildSrcDoc } from "../../lib/artifactTemplate";

interface Props {
  title: string;
  artifactType: "html" | "react";
  code: string;
}

export function ArtifactBlock({ title, artifactType, code }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(220);
  const [error, setError] = useState<string | null>(null);
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source !== iframeRef.current?.contentWindow) return;
      if (e.data?.type === "resize") {
        setHeight(Math.min(Math.max(120, e.data.height + 24), 900));
      } else if (e.data?.type === "artifact-error") {
        setError(String(e.data.message));
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  return (
    <div className="artifact">
      <div className="artifact-header">
        <span className="artifact-title">⚡ {title}</span>
        <button className="artifact-code-toggle" onClick={() => setShowCode(!showCode)}>
          {showCode ? "hide code" : "view code"}
        </button>
      </div>
      {error ? (
        <div className="artifact-error">
          This artifact hit an error while rendering: <code>{error}</code>
        </div>
      ) : (
        <iframe
          ref={iframeRef}
          sandbox="allow-scripts"
          srcDoc={buildSrcDoc(artifactType, code)}
          style={{ height }}
          title={title}
        />
      )}
      {showCode && <pre className="artifact-source">{code}</pre>}
    </div>
  );
}
