/**
 * Pins audit offense #4: the terminal-state decision for a chat stream.
 * A `done` frame is the only legitimate completion; a close without it is a
 * cut (failure, partial text preserved); an abort says nothing at all.
 */
import { describe, expect, test } from 'bun:test'
import { consumeChatStream, type StreamSink } from './consume-stream'

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

/** One pull per step: a string enqueues, a function runs (e.g. abort), 'crash' errors. */
function scriptedStream(steps: Array<string | (() => void) | 'crash'>): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let i = 0
  return new ReadableStream({
    pull(controller) {
      for (;;) {
        if (i >= steps.length) {
          controller.close()
          return
        }
        const step = steps[i++]
        if (step === 'crash') {
          controller.error(new Error('boom'))
          return
        }
        if (typeof step === 'function') {
          step()
          continue // an action produces no chunk; move to the next step
        }
        controller.enqueue(encoder.encode(step))
        return
      }
    },
  })
}

function sinkRecorder() {
  const patches: Array<Record<string, unknown>> = []
  let text = ''
  const sink: StreamSink = {
    patch: (fields) => patches.push(fields as Record<string, unknown>),
    delta: (t) => {
      text += t
    },
  }
  return { sink, patches, text: () => text }
}

const METADATA = frame('metadata', { session_id: 's1', message_id: 'm1', scope: null })
const DONE = frame('done', { message_id: 'm1', session_id: 's1' })

describe('consumeChatStream', () => {
  test('deltas then close with no done frame ⇒ cut, text preserved', async () => {
    const { sink, patches, text } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([
        METADATA,
        frame('delta', { text: 'Hello ' }),
        frame('delta', { text: 'world' }),
      ]),
      new AbortController().signal,
      sink,
    )
    expect(end).toEqual({ kind: 'cut' })
    expect(text()).toBe('Hello world')
    expect(patches[0]).toEqual({ sessionId: 's1', messageId: 'm1', scope: null })
  })

  test('the same stream with a done frame ⇒ done', async () => {
    const { sink, text } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([
        METADATA,
        frame('delta', { text: 'Hello ' }),
        frame('delta', { text: 'world' }),
        DONE,
      ]),
      new AbortController().signal,
      sink,
    )
    expect(end).toEqual({ kind: 'done' })
    expect(text()).toBe('Hello world')
  })

  test('abort mid-stream ⇒ aborted, even if a done frame follows', async () => {
    const ac = new AbortController()
    const { sink, text } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([
        METADATA,
        frame('delta', { text: 'Hello ' }),
        () => ac.abort(),
        frame('delta', { text: 'world' }),
        DONE,
      ]),
      ac.signal,
      sink,
    )
    expect(end).toEqual({ kind: 'aborted' })
    expect(text()).toBe('Hello ')
  })

  test('an explicit error frame ⇒ error with its problem payload', async () => {
    const problem = { type: '/problems/upstream-error', title: 'Backend error', status: 502 }
    const { sink } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([METADATA, frame('error', problem)]),
      new AbortController().signal,
      sink,
    )
    expect(end).toEqual({ kind: 'error', problem })
  })

  test('a stream that errors mid-read ⇒ cut, prior deltas kept', async () => {
    const { sink, text } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([frame('delta', { text: 'partial' }), 'crash']),
      new AbortController().signal,
      sink,
    )
    expect(end).toEqual({ kind: 'cut' })
    expect(text()).toBe('partial')
  })

  test('abort outranks a stream error', async () => {
    const ac = new AbortController()
    const { sink } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([frame('delta', { text: 'x' }), () => ac.abort(), 'crash']),
      ac.signal,
      sink,
    )
    expect(end).toEqual({ kind: 'aborted' })
  })

  test('frames after done are not consumed', async () => {
    const { sink, text } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([
        frame('delta', { text: 'answer' }),
        DONE,
        frame('delta', { text: ' trailing' }),
      ]),
      new AbortController().signal,
      sink,
    )
    expect(end).toEqual({ kind: 'done' })
    expect(text()).toBe('answer')
  })

  test('an error frame that is not a problem body ⇒ error with a catalogue problem', async () => {
    const { sink } = sinkRecorder()
    const end = await consumeChatStream(
      scriptedStream([METADATA, frame('error', { error: 'bad gateway' })]),
      new AbortController().signal,
      sink,
    )
    expect(end.kind).toBe('error')
    if (end.kind === 'error') expect(end.problem.type).toBe('/problems/upstream-error')
  })
})
