// Errors as application/problem+json (RFC 9457), with the same members as the Python services:
// type, title, status, detail, and `errors` for the parameters that are wrong.
import type { FastifyError, FastifyReply, FastifyRequest } from "fastify";
import { STATUS_CODES } from "node:http";
import { clean } from "./logging.ts";

const INVALID = "The request has invalid or missing parameters.";

export function problem(reply: FastifyReply, status: number, detail: string, extra: object = {}) {
  return reply
    .code(status)
    .type("application/problem+json")
    .send({ type: "about:blank", title: STATUS_CODES[status] ?? "Error", status, detail, ...extra });
}

/** A 422 for a rule that a JSON schema cannot say (a range that is too long). */
export function invalidParameter(reply: FastifyReply, loc: string[], msg: string, type: string) {
  return problem(reply, 422, INVALID, { errors: [{ loc, msg, type }] });
}

export function errorHandler(error: FastifyError, request: FastifyRequest, reply: FastifyReply) {
  if (error.validation) {
    // As FastAPI says it: ["query", "pollutant"], ["path", "code"].
    const where = error.validationContext === "params" ? "path" : "query";
    const errors = error.validation.map((e) => {
      const missing = (e.params as { missingProperty?: string }).missingProperty;
      const name = e.instancePath.replace("/", "") || missing || "";
      return { loc: [where, name], msg: e.message ?? "invalid", type: e.keyword };
    });
    return problem(reply, 422, INVALID, { errors });
  }
  const status = error.statusCode ?? 500;
  if (status < 500) return problem(reply, status, STATUS_CODES[status] ?? "Error");
  // The reason only goes to the log: a message can name a table, a user or an address.
  request.log.error({ exception: clean(error.stack ?? String(error)) }, "request failed");
  return problem(reply, 500, "The service failed to answer.");
}

export function notFoundHandler(_request: FastifyRequest, reply: FastifyReply) {
  return problem(reply, 404, "Not Found");
}

// Errors of Fastify before the routes (a URL that cannot be read): its own answer would repeat the
// path and name the framework.
export function frameworkErrors(error: FastifyError, _request: unknown, reply: FastifyReply) {
  const status = error.statusCode && error.statusCode < 500 ? error.statusCode : 400;
  return problem(reply, status, STATUS_CODES[status] ?? "Error");
}

// How the OpenAPI document describes the errors of a route.
const problemSchema = {
  type: "object",
  properties: {
    type: { type: "string" },
    title: { type: "string" },
    status: { type: "integer" },
    detail: { type: "string" },
    errors: { type: "array" },
  },
} as const;

export const INVALID_REQUEST = {
  422: { description: INVALID, content: { "application/problem+json": { schema: problemSchema } } },
} as const;

export const NOT_FOUND = {
  404: {
    description: "What was asked for does not exist.",
    content: { "application/problem+json": { schema: problemSchema } },
  },
} as const;
