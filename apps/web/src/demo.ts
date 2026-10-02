// Static demo mode (GitHub Pages): no backend. Built with VITE_DEMO_MODE=1, the API client
// answers GET requests from a fixture captured from a real local run on synthetic data
// (scripts/capture_demo_fixtures.py) and refuses every mutation as read-only. Sessions are
// unsigned display-only tokens generated in the browser; nothing is sent anywhere.
import type { Middleware } from "openapi-fetch";

import { decode, getToken } from "./auth";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "1";

export interface DemoFixture {
  generated_utc: string;
  tenant: string;
  subjects: Record<string, string>;
  get: Record<string, unknown>;
  existing: Record<string, unknown>;
}

let fixture: Promise<DemoFixture> | null = null;

export function loadFixture(): Promise<DemoFixture> {
  fixture ??= fetch(`${import.meta.env.BASE_URL}demo/fixtures.json`).then(
    (r) => r.json() as Promise<DemoFixture>,
  );
  return fixture;
}

function base64url(text: string): string {
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Display-only session for the static demo (unsigned; never leaves the browser). */
export function demoToken(role: string, subject: string, tenant: string): string {
  const header = base64url(JSON.stringify({ alg: "none", typ: "demo" }));
  const payload = base64url(JSON.stringify({ sub: subject, tenant_id: tenant, roles: [role] }));
  return `${header}.${payload}.demo`;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const AUDIT_ROLES = ["auditor", "supervisor"];

/** Resolve one request against the fixture (exported for tests). */
export function answer(data: DemoFixture, method: string, url: URL, roles: string[]): Response {
  const path = url.pathname.replace(/^.*?\/api(?=\/v1\/)/, "");
  if (method !== "GET") {
    const existing = data.existing[`${method} ${path}`];
    if (existing !== undefined) return json(200, existing);
    return json(403, { detail: { code: "demo_read_only" } });
  }
  if (path.endsWith("/audit") && !roles.some((r) => AUDIT_ROLES.includes(r))) {
    return json(403, { detail: "insufficient role" }); // same body as the real API
  }
  const body = data.get[path];
  if (body === undefined) return json(404, { detail: { code: "not_found" } });
  const status = url.searchParams.get("match_status") ?? url.searchParams.get("status");
  if (status && path.endsWith("/results")) {
    const page = body as { items: { match_status: string }[] };
    return json(200, { ...page, items: page.items.filter((i) => i.match_status === status) });
  }
  if (status && path === "/v1/cases") {
    return json(200, (body as { status: string }[]).filter((c) => c.status === status));
  }
  return json(200, body);
}

export const demoMiddleware: Middleware = {
  async onRequest({ request }) {
    const data = await loadFixture();
    const roles = decode(getToken())?.roles ?? [];
    return answer(data, request.method, new URL(request.url), roles);
  },
};
