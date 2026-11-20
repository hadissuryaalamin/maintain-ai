import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import type { MachineSummary } from "../api/types";
import { MachineSelector } from "./MachineSelector";

export const DISCLAIMER = "AI suggestions are preliminary. Verify with the OEM manual and site procedures.";
export const QUICK_PROMPTS = [
  "Show recent sensor readings",
  "Similar past incidents",
  "Relevant manual section",
  "Downtime cost if stopped",
] as const;
export const MAX_MESSAGE = 10_000;
const MIN_MESSAGE = 3;

export interface ComposerHandle {
  focus(): void;
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
}

type SpeechCtor = new () => SpeechRecognitionLike;

function speechRecognition(): SpeechCtor | null {
  const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface ComposerProps {
  onSend(text: string): void;
  sending: boolean;
  machines: MachineSummary[];
  selected: MachineSummary | null;
  onSelectMachine(id: string): void;
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer(
  { onSend, sending, machines, selected, onSelectMachine },
  ref,
) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const recognizer = useRef<SpeechRecognitionLike | null>(null);
  const Speech = speechRecognition();

  useImperativeHandle(ref, () => ({ focus: () => textarea.current?.focus() }), []);

  const canSend = !sending && text.trim().length >= MIN_MESSAGE;

  function submit() {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  }

  function insert(prompt: string) {
    setText((current) => (current.trim() ? `${current.trimEnd()} ${prompt}` : prompt));
    textarea.current?.focus();
  }

  function toggleDictation() {
    if (!Speech) return;
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const recognition = new Speech();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (transcript) setText((current) => (current ? `${current} ${transcript}` : transcript).slice(0, MAX_MESSAGE));
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognizer.current = recognition;
    setListening(true);
    recognition.start();
  }

  return (
    <div className="border-t border-outline/40 bg-surface/95 px-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-2 backdrop-blur md:px-6">
      <div className="mx-auto flex max-w-[860px] flex-col gap-2">
        <div className="no-scrollbar flex items-center gap-2 overflow-x-auto">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => insert(prompt)}
              className="h-12 shrink-0 rounded-full bg-surface-container px-3 font-mono text-[11px] text-on-surface hover:bg-surface-container-high"
            >
              <span className="text-primary" aria-hidden="true">
                +{" "}
              </span>
              {prompt}
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-2 rounded-xl border border-outline/40 bg-surface-container p-2">
          <div className="flex items-center justify-between px-1">
            <MachineSelector machines={machines} selected={selected} onSelect={onSelectMachine} />
            {listening && <span className="font-mono text-[10px] text-primary">Listening…</span>}
          </div>
          <div className="flex items-end gap-2">
            <textarea
              ref={textarea}
              aria-label="Message"
              rows={1}
              maxLength={MAX_MESSAGE}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="Describe the symptom, alarm code, or ask a question…"
              className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-2 py-3 text-sm text-on-surface placeholder:text-on-surface-variant/70 focus:outline-none"
            />
            {Speech && (
              <button
                type="button"
                onClick={toggleDictation}
                aria-pressed={listening}
                aria-label={listening ? "Stop dictation" : "Dictate message"}
                className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl ${
                  listening ? "bg-primary text-on-primary" : "bg-primary-container text-on-primary-container"
                }`}
              >
                <span className="icon text-[28px]" aria-hidden="true">
                  mic
                </span>
              </button>
            )}
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              aria-label="Send"
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-primary text-on-primary disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="icon text-[24px]" aria-hidden="true">
                send
              </span>
            </button>
          </div>
        </div>
        <p className="text-center font-mono text-[10px] text-on-surface-variant">{DISCLAIMER}</p>
      </div>
    </div>
  );
});
