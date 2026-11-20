import { DEMO_IDENTITIES, describeIdentity, useIdentity } from "../state/identity";

export function IdentityPicker({ compact = false }: { compact?: boolean }) {
  const identity = useIdentity();
  const current = describeIdentity(identity);
  const initials = current.name
    .split(" ")
    .map((part) => part.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <label className="relative flex min-h-12 items-center gap-3 rounded-lg px-2 hover:bg-surface-container">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-primary font-mono text-xs font-bold text-on-primary"
        aria-hidden="true"
      >
        {initials}
      </span>
      {!compact && (
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-bold text-on-surface">{current.name}</span>
          <span className="block truncate font-mono text-[10px] text-on-surface-variant">
            {current.company} · {current.role} · demo
          </span>
        </span>
      )}
      <select
        aria-label="Demo identity"
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        value={`${identity.tenantId}|${identity.userId}`}
        onChange={(event) => {
          const [tenantId, userId] = event.target.value.split("|");
          if (tenantId && userId) identity.setIdentity(tenantId, userId);
        }}
      >
        {DEMO_IDENTITIES.map((item) => (
          <option key={item.userId} value={`${item.tenantId}|${item.userId}`}>
            {item.name} ({item.company})
          </option>
        ))}
      </select>
      {!compact && (
        <span className="icon text-[18px] text-on-surface-variant" aria-hidden="true">
          unfold_more
        </span>
      )}
    </label>
  );
}
