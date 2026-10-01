// Development session: a JWT issued by scripts/dev_auth.py, kept in sessionStorage.
// The payload is decoded only to show who is signed in; the API verifies everything.

const KEY = "recon.token";

export interface Session {
  subject: string;
  tenant: string;
  roles: string[];
  expiresAt: Date | null;
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (token) sessionStorage.setItem(KEY, token.trim());
  else sessionStorage.removeItem(KEY);
}

function decodeSegment(segment: string): Record<string, unknown> {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  return JSON.parse(atob(padded)) as Record<string, unknown>;
}

export function decode(token: string | null): Session | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) return null;
  try {
    const claims = decodeSegment(parts[1]);
    const roles = Array.isArray(claims.roles) ? claims.roles.map(String) : [];
    return {
      subject: String(claims.sub ?? ""),
      tenant: String(claims.tenant_id ?? ""),
      roles,
      expiresAt: typeof claims.exp === "number" ? new Date(claims.exp * 1000) : null,
    };
  } catch {
    return null;
  }
}

export function hasRole(session: Session | null, role: string): boolean {
  return session?.roles.includes(role) ?? false;
}
