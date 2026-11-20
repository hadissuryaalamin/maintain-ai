import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

function Placeholder() {
  return <main className="p-6 font-mono text-sm">Maintain AI</main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Placeholder />
  </StrictMode>,
);
