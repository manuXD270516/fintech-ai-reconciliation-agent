import { describe, expect, it } from "vitest";

import { decode } from "../auth";
import { type DemoFixture, answer, demoToken } from "../demo";

const data: DemoFixture = {
  generated_utc: "2026-10-02T00:00:00+00:00",
  tenant: "demo-test",
  subjects: { analyst: "ana-demo" },
  get: {
    "/v1/batches": [{ batch_id: "b-1" }],
    "/v1/runs/r1/results": {
      items: [
        { ordinal: 1, match_status: "EXACT" },
        { ordinal: 2, match_status: "UNMATCHED" },
      ],
      next_after: null,
    },
    "/v1/cases": [
      { case_id: "c1", status: "APPROVED" },
      { case_id: "c2", status: "HUMAN_REVIEW" },
    ],
    "/v1/cases/c1/audit": { audit: [] },
  },
  existing: { "POST /v1/runs/r1/results/2/cases": { case_id: "c2", created: false } },
};

const url = (path: string) => new URL(`https://example.invalid/repo/api${path}`);

describe("static demo mode", () => {
  it("serves captured GETs and filters like the API", async () => {
    expect(await answer(data, "GET", url("/v1/batches"), ["analyst"]).json()).toEqual([
      { batch_id: "b-1" },
    ]);
    const page = await answer(data, "GET", url("/v1/runs/r1/results?match_status=EXACT&limit=100"), [
      "analyst",
    ]).json();
    expect(page.items).toEqual([{ ordinal: 1, match_status: "EXACT" }]);
    const queue = await answer(data, "GET", url("/v1/cases?status=HUMAN_REVIEW"), ["analyst"]).json();
    expect(queue).toEqual([{ case_id: "c2", status: "HUMAN_REVIEW" }]);
    expect(answer(data, "GET", url("/v1/runs/unknown"), ["analyst"]).status).toBe(404);
  });

  it("is read-only except for idempotent re-opens captured from the real run", async () => {
    const refused = answer(data, "POST", url("/v1/cases/c2/decisions"), ["supervisor"]);
    expect(refused.status).toBe(403);
    expect(await refused.json()).toEqual({ detail: { code: "demo_read_only" } });
    const reopened = answer(data, "POST", url("/v1/runs/r1/results/2/cases"), ["analyst"]);
    expect(await reopened.json()).toEqual({ case_id: "c2", created: false });
  });

  it("keeps the audit trail restricted to auditor and supervisor", () => {
    expect(answer(data, "GET", url("/v1/cases/c1/audit"), ["analyst"]).status).toBe(403);
    expect(answer(data, "GET", url("/v1/cases/c1/audit"), ["auditor"]).status).toBe(200);
  });

  it("issues unsigned display-only sessions", () => {
    const token = demoToken("auditor", "aud-demo", "demo-test");
    expect(token.endsWith(".demo")).toBe(true);
    expect(decode(token)).toMatchObject({ subject: "aud-demo", tenant: "demo-test", roles: ["auditor"] });
  });
});
