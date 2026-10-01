// Typed client generated from apps/web/openapi.json (openapi-typescript + openapi-fetch).
import createClient, { type Middleware } from "openapi-fetch";

import { getToken } from "../auth";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type ResultRow = Schemas["ResultOut"];
export type CaseOut = Schemas["CaseOut"];
export type Recommendation = Schemas["RecommendationOut"];
export type Investigation = Schemas["InvestigationOut"];
export type AuditTrail = Schemas["AuditTrailOut"];

export const api = createClient<paths>({ baseUrl: "/api" });

const auth: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
};
api.use(auth);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const CODE_MESSAGES: Record<string, string> = {
  segregation_of_duties:
    "No podés decidir sobre una recomendación que propusiste o cuya investigación pediste.",
  role_not_allowed: "Tu rol no permite registrar decisiones.",
  version_conflict: "El caso cambió desde que lo abriste: recargá y revisá la versión vigente.",
  recommendation_obsolete:
    "La recomendación es obsoleta: existe un run más nuevo del lote. No es aprobable.",
  recommendation_expired: "La recomendación expiró; hace falta una nueva propuesta.",
  recommendation_not_pending: "La recomendación ya no está pendiente.",
  case_status_not_allowed: "El estado del caso no permite esta acción.",
  idempotency_conflict: "La clave de idempotencia ya se usó con otro contenido.",
  reason_required: "El motivo es obligatorio (mínimo 10 caracteres).",
  not_found: "No encontrado.",
  ai_disabled:
    "La investigación con IA está desactivada (kill switch). La conciliación determinística, los casos y las decisiones siguen disponibles.",
};

/** Human message for an API failure; never shows raw server internals. */
export function explain(status: number, detail: unknown): ApiError {
  const code =
    typeof detail === "object" && detail !== null && "code" in detail
      ? String((detail as { code: unknown }).code)
      : "";
  if (code && CODE_MESSAGES[code]) return new ApiError(status, code, CODE_MESSAGES[code]);
  const generic: Record<number, string> = {
    401: "Sesión inválida o vencida: ingresá un token nuevo.",
    403: "Tu rol no permite esta acción.",
    404: "No encontrado.",
    409: "Conflicto con el estado actual: recargá.",
    422: "Datos inválidos.",
    503: "Servicio no disponible.",
  };
  return new ApiError(status, code || String(status), generic[status] ?? `Error ${status}.`);
}

/** Unwrap an openapi-fetch response or throw an ApiError with a readable message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    const detail =
      typeof result.error === "object" && result.error !== null && "detail" in result.error
        ? (result.error as { detail: unknown }).detail
        : undefined;
    throw explain(result.response.status, detail);
  }
  return result.data;
}
