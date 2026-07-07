// Builds the srcDoc for the sandboxed artifact iframe. Mirrors the
// reverse-engineered Claude Artifacts stack: sandboxed iframe, React 18 UMD +
// Babel standalone for JSX, Tailwind Play CDN, Chart.js UMD; a postMessage
// handshake reports rendered height and runtime errors to the parent.

const CDN_SCRIPTS = `
  <script src="https://cdn.tailwindcss.com"></script>
  <script crossorigin src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone@7.26.4/babel.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
`;

const HANDSHAKE = `
  <script>
    window.onerror = function (msg) {
      parent.postMessage({ type: "artifact-error", message: String(msg) }, "*");
    };
    new ResizeObserver(function () {
      parent.postMessage({ type: "resize", height: document.documentElement.scrollHeight }, "*");
    }).observe(document.body);
  </script>
`;

export function buildSrcDoc(artifactType: "html" | "react", code: string): string {
  // A literal "</script>" inside generated code would terminate the script tag.
  const safeCode = code.replace(/<\/script/gi, "<\\/script");
  // Only auto-mount if the generated code didn't already render itself.
  const mount = /createRoot|ReactDOM\.render/.test(code)
    ? ""
    : `ReactDOM.createRoot(document.getElementById("root")).render(<App />);`;
  const body =
    artifactType === "react"
      ? `<div id="root"></div>
         <script type="text/babel" data-presets="react">
           try {
             ${safeCode}
             ${mount}
             parent.postMessage({ type: "artifact-ready" }, "*");
           } catch (e) {
             parent.postMessage({ type: "artifact-error", message: String(e) }, "*");
           }
         </script>`
      : `${code}
         <script>parent.postMessage({ type: "artifact-ready" }, "*");</script>`;

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  ${CDN_SCRIPTS}
  <style>body { margin: 0; padding: 12px; font-family: system-ui, sans-serif; }</style>
</head>
<body>
  ${HANDSHAKE}
  ${body}
</body>
</html>`;
}
