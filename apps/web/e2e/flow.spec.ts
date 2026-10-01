import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

// Context prepared by scripts/web_e2e.py against the real Compose stack: dev tokens and a
// fresh run whose results include an AMOUNT_MISMATCH. Model output is SIMULATED (scripted).
interface Context {
  analyst: string;
  dual: string;
  supervisor: string;
  auditor: string;
  run_id: string;
  payment_ref: string;
}
const ctx = JSON.parse(process.env.E2E_CONTEXT ?? "{}") as Context;

async function login(page: Page, token: string) {
  await page.goto("/#/batches");
  const logout = page.getByRole("button", { name: "Cerrar sesión" });
  if (await logout.isVisible()) await logout.click();
  await page.getByLabel("Token JWT").fill(token);
  await page.getByRole("button", { name: "Usar token" }).click();
  await expect(logout).toBeVisible();
}

async function seriousA11yViolations(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  return result.violations
    .filter((v) => v.impact === "critical" || v.impact === "serious")
    .map((v) => v.id);
}

test("analyst investigates and proposes; supervisor decides; auditor reconstructs", async ({ page }) => {
  test.skip(!ctx.run_id, "E2E_CONTEXT not provided (run scripts/web_e2e.py)");

  // Analyst: open the result with the keyboard and request a read-only investigation.
  await login(page, ctx.analyst);
  await page.goto(`/#/runs/${ctx.run_id}`);
  const detail = page.getByRole("button", { name: `Ver detalle de ${ctx.payment_ref}` });
  await detail.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Solicitar investigación" }).click();
  await expect(page.getByRole("heading", { name: "Investigación" })).toBeVisible();
  await expect(page.getByText("DRAFTED", { exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("region", { name: "Hechos (FACT)" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Inferencias (INFERENCE)" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Hipótesis (HYPOTHESIS)" })).toBeVisible();
  await expect(page.getByText("SIMULATED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("uncalibrated")).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  // Analyst: open the case adopting the reviewed draft and propose a non-operational action.
  await page.getByRole("button", { name: "Abrir caso con este borrador" }).click();
  await expect(page.getByRole("heading", { name: "Caso", exact: true })).toBeVisible();
  await page.getByLabel("Fundamento").fill("adoptar el borrador revisado y pedir el reporte corregido");
  await page.getByRole("button", { name: "Proponer" }).click();
  await expect(page.getByRole("status")).toContainText("pendiente");
  const caseId = /#\/cases\/([^?]+)/.exec(page.url())?.[1] ?? "";
  expect(caseId).not.toBe("");

  // The proposer, even with the supervisor role, cannot decide (segregation of duties).
  await login(page, ctx.dual);
  await page.goto(`/#/cases/${caseId}`);
  await page.getByLabel("Motivo (obligatorio)").fill("intento de autoaprobación");
  await page.getByRole("button", { name: "Registrar decisión" }).click();
  await expect(page.getByRole("alert")).toContainText("propusiste");

  // Supervisor: decides with the keyboard on the current version; nothing moves money.
  await login(page, ctx.supervisor);
  await page.goto(`/#/cases/${caseId}`);
  await expect(page.getByText(/^Vigente/)).toBeVisible();
  await expect(page.getByText(/no ejecuta reembolsos, ajustes ni movimientos de dinero/)).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await page.getByLabel("Motivo (obligatorio)").fill("aprobado: pedir el reporte corregido al proveedor");
  await page.getByRole("button", { name: "Registrar decisión" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("Decisión APPROVE registrada");
  await expect(page.getByRole("status")).toContainText("no money movement");

  // Auditor: reconstructs the case, including the refused attempt.
  await login(page, ctx.auditor);
  await page.goto(`/#/cases/${caseId}/audit`);
  await expect(page.getByRole("cell", { name: "decision.record" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "decision.denied" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "investigation.finish" })).toBeVisible();
});
