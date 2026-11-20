import { describeIdentity, useIdentity } from "../state/identity";

export function UserBubble({ text, at }: { text: string; at: string }) {
  const identity = describeIdentity(useIdentity());
  return (
    <div className="flex w-full flex-col items-end">
      <span className="mb-1 text-xs font-bold text-on-surface">{identity.name}</span>
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-xl rounded-tr-none bg-surface-container-high p-4 text-sm leading-relaxed text-on-surface">
        {text}
      </div>
      <time className="mt-1 font-mono text-[10px] text-on-surface-variant" dateTime={at}>
        {new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
      </time>
    </div>
  );
}
