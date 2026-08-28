#!/usr/bin/env bun
/**
 * Generates the OpenAPI 3.1 contracts from the zod schemas:
 *
 * - contract/openapi.json      — the Django endpoints we are ASKING FOR
 *                                (kind: 'desired'), the backend team's artifact.
 * - contract/bff.openapi.json  — our own /bff HTTP face (face: 'bff').
 *
 * OpenAPI 3.1 schema objects are JSON Schema 2020-12 — zod v4's default
 * target — so no conversion library is needed. Run: `bun run contract:spec`;
 * `--check` verifies the committed files are up to date (wired into lint).
 */
import { allOperations } from '@/lib/bff/contract'
import type { Operation } from '@/lib/bff/core/contract-types'
// Imported for its registry side effect (components.schemas).
import '@/lib/bff/core/problem-schema'
import * as z from 'zod'

const OUT: Record<string, { file: string; title: string; ops: Operation[] }> = {
  django: {
    file: 'contract/openapi.json',
    title: 'Research Intelligence backend — endpoints requested by the frontend',
    ops: allOperations.filter((op) => op.face === 'django' && op.kind === 'desired'),
  },
  bff: {
    file: 'contract/bff.openapi.json',
    title: 'Research Intelligence frontend — BFF HTTP face',
    ops: allOperations.filter((op) => op.face === 'bff'),
  },
}

type Json = Record<string, unknown>

// `uri` is honoured for schema conversion at runtime but only typed on the
// registry overload — hence the cast.
const SCHEMA_PARAMS = {
  metadata: z.globalRegistry,
  uri: (id: string) => `#/components/schemas/${id}`,
  unrepresentable: 'throw',
  io: 'output',
} as unknown as Parameters<typeof z.toJSONSchema>[1]

function toJson(schema: z.ZodType): Json {
  const js = z.toJSONSchema(schema, SCHEMA_PARAMS) as Json
  delete js.$schema
  delete js.$defs
  delete js.id
  return js
}

function pathParameters(path: string): Json[] {
  return [...path.matchAll(/\{([a-z_]+)\}/g)].map((m) => ({
    name: m[1],
    in: 'path',
    required: true,
    schema: { type: 'string', format: 'uuid' },
  }))
}

function queryParameters(query: z.ZodType | undefined): Json[] {
  if (!query) return []
  const js = toJson(query)
  const props = (js.properties ?? {}) as Record<string, Json>
  const required = (js.required ?? []) as string[]
  return Object.entries(props).map(([name, schema]) => {
    // A default means the caller may omit it, whatever the output type says.
    const hasDefault = typeof schema === 'object' && schema !== null && 'default' in schema
    if (typeof schema === 'object' && schema !== null && schema.maximum === 9007199254740991) {
      delete schema.maximum
    }
    return { name, in: 'query', required: required.includes(name) && !hasDefault, schema }
  })
}

function operationObject(op: Operation): Json {
  const responses: Json = {}
  for (const [status, schema] of Object.entries(op.responses)) {
    responses[status] = {
      description: 'Success',
      content: op.sse
        ? { 'text/event-stream': { schema: toJson(schema) } }
        : { 'application/json': { schema: toJson(schema) } },
    }
  }
  responses.default = {
    description: 'Error (RFC 9457)',
    content: {
      'application/problem+json': { schema: { $ref: '#/components/schemas/Problem' } },
    },
  }
  const [purePath] = op.path.split('?')
  const object: Json = {
    operationId: op.id,
    summary: op.summary,
    tags: [op.resource],
    parameters: [...pathParameters(op.path), ...queryParameters(op.query)],
    responses,
  }
  if (op.body) {
    object.requestBody = {
      required: true,
      content: { 'application/json': { schema: toJson(op.body) } },
    }
  }
  void purePath
  return object
}

function buildDocument(title: string, ops: Operation[]): Json {
  const paths: Record<string, Json> = {}
  for (const op of ops) {
    const [purePath] = op.path.split('?')
    const entry = (paths[purePath] ??= {})
    entry[op.method.toLowerCase()] = operationObject(op)
  }
  // Components from every registered (`.meta({id})`) schema.
  const registry = z.toJSONSchema(z.globalRegistry, {
    uri: (id) => `#/components/schemas/${id}`,
    unrepresentable: 'throw',
    io: 'output',
  }) as { schemas: Record<string, Json> }
  const schemas: Record<string, Json> = {}
  for (const [id, schema] of Object.entries(registry.schemas).sort(([a], [b]) =>
    a.localeCompare(b),
  )) {
    const clean = { ...schema }
    delete clean.$schema
    delete clean.id
    schemas[id] = clean
  }
  return {
    openapi: '3.1.0',
    info: {
      title,
      version: '0.1.0',
      description:
        'Generated from the zod contract schemas (src/lib/bff/*/schema.ts) by scripts/contract-spec.ts. Do not edit by hand.',
    },
    paths,
    components: { schemas },
  }
}

const check = process.argv.includes('--check')
let dirty = false
for (const { file, title, ops } of Object.values(OUT)) {
  const next = JSON.stringify(buildDocument(title, ops), null, 2) + '\n'
  const current = await Bun.file(file)
    .text()
    .catch(() => '')
  if (check) {
    if (current !== next) {
      console.error(`✗ ${file} is out of date — run: bun run contract:spec`)
      dirty = true
    } else {
      console.log(`✓ ${file} up to date`)
    }
  } else {
    await Bun.write(file, next)
    console.log(`wrote ${file} (${ops.length} operations)`)
  }
}
if (dirty) process.exit(1)
