import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { createApiClient, type ApiClient, type Identity } from "../api/client";

export interface DemoIdentity extends Identity {
  name: string;
  role: string;
  company: string;
}

export const DEMO_IDENTITIES: readonly DemoIdentity[] = [
  { tenantId: "company-a", userId: "user-a-tech", name: "Avery Technician", role: "Technician", company: "Company A" },
  { tenantId: "company-a", userId: "user-a-manager", name: "Alex Manager", role: "Manager", company: "Company A" },
  { tenantId: "company-b", userId: "user-b-tech", name: "Bailey Technician", role: "Technician", company: "Company B" },
  { tenantId: "company-b", userId: "user-b-manager", name: "Blair Manager", role: "Manager", company: "Company B" },
];

export function describeIdentity(identity: Identity): DemoIdentity {
  return (
    DEMO_IDENTITIES.find(
      (item) => item.tenantId === identity.tenantId && item.userId === identity.userId,
    ) ?? { ...identity, name: identity.userId, role: "User", company: identity.tenantId }
  );
}

interface IdentityValue extends Identity {
  setIdentity(tenantId: string, userId: string): void;
  client: ApiClient;
}

const IdentityContext = createContext<IdentityValue | null>(null);

function defaultIdentity(): Identity {
  return {
    tenantId: import.meta.env.VITE_DEMO_TENANT_ID || "company-a",
    userId: import.meta.env.VITE_DEMO_USER_ID || "user-a-tech",
  };
}

export function IdentityProvider({
  children,
  initial,
  clientFactory = createApiClient,
}: {
  children: ReactNode;
  initial?: Identity;
  clientFactory?: (identity: Identity) => ApiClient;
}) {
  const [identity, setState] = useState<Identity>(() => initial ?? defaultIdentity());
  const setIdentity = useCallback((tenantId: string, userId: string) => {
    setState({ tenantId, userId });
  }, []);
  const value = useMemo<IdentityValue>(
    () => ({ ...identity, setIdentity, client: clientFactory(identity) }),
    [identity, setIdentity, clientFactory],
  );
  return <IdentityContext.Provider value={value}>{children}</IdentityContext.Provider>;
}

export function useIdentity(): IdentityValue {
  const value = useContext(IdentityContext);
  if (!value) throw new Error("useIdentity must be used inside IdentityProvider");
  return value;
}
