// Errors as application/problem+json (RFC 9457), with the members of the Python services:
// type, title, status, detail (and `errors` for invalid parameters).
import type { FastifyError, FastifyReply, FastifyRequest } from "fastify";
import { STATUS_CODES } from "node:http";
import { MAX_EXCEPTION, clean } from "./logging.js";

export function problem(reply: FastifyReply, status: number, detail: string, extra: object = {}) {
  return reply
    .code(status)
    .type("application/problem+json")
    .send({ type: "about:blank", title: STATUS_CODES[status] ?? "Error", status, detail, ...extra });
}

// Where each part of the request is called in the errors, as FastAPI calls it.
const WHERE: Record<string, string> = {
  querystring: "query",
  params: "path",
  headers: "header",
  body: "body",
};

function invalidRequest(error: FastifyError, reply: FastifyReply) {
  const where = WHERE[error.validationContext ?? ""] ?? "query";
  const errors = (error.validation ?? []).map((e) => {
    const params = e.params as { missingProperty?: string } | undefined;
    const name = (e.instancePath || "").split("/").filter(Boolean);
    if (e.keyword === "required" && params?.missingProperty) name.push(params.missingProperty);
    return { loc: [where, ...name], msg: e.message ?? "invalid", type: e.keyword };
  });
  return problem(reply, 422, "The request has invalid or missing parameters.", { errors });
}

export function errorHandler(error: FastifyError, request: FastifyRequest, reply: FastifyReply) {
  if (error.validation) return invalidRequest(error, reply);
  const status = error.statusCode ?? 500;
  if (status < 500) return problem(reply, status, STATUS_CODES[status] ?? "Error");
  // The reason is only for the log: a message can name a table, a user or an address.
  request.log.error({ exception: clean(error.stack ?? String(error), MAX_EXCEPTION) }, "request failed");
  return problem(reply, 500, "The service failed to answer.");
}

export function notFoundHandler(_request: FastifyRequest, reply: FastifyReply) {
  return problem(reply, 404, "Not Found");
}

// Errors that Fastify raises before the routes and the handlers (a URL that cannot be read, a
// parameter that is too long): left alone it answers with its own JSON, that repeats the path and
// names the framework.
export function frameworkErrors(error: FastifyError, _request: unknown, reply: FastifyReply) {
  const status = error.statusCode && error.statusCode < 500 ? error.statusCode : 400;
  return problem(reply, status, STATUS_CODES[status] ?? "Error");
}

// How the OpenAPI document describes the errors: as problem documents, which is what is sent.
const problemMembers = {
  type: { type: "string" },
  title: { type: "string" },
  status: { type: "integer" },
  detail: { type: "string" },
} as const;

const validationProblem = {
  type: "object",
  required: ["type", "title", "status", "detail", "errors"],
  properties: {
    ...problemMembers,
    errors: {
      type: "array",
      items: {
        type: "object",
        required: ["loc", "msg", "type"],
        properties: {
          loc: { type: "array", items: { type: ["string", "integer"] } },
          msg: { type: "string" },
          type: { type: "string" },
        },
      },
    },
  },
} as const;

/** For the routes that take parameters: the 422 that they can answer. */
export const INVALID_REQUEST = {
  422: {
    description: "The request has invalid or missing parameters.",
    content: { "application/problem+json": { schema: validationProblem } },
  },
} as const;
