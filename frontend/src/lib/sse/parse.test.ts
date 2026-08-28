import { describe, expect, test } from 'bun:test'
import { parseSse, type SseFrame } from './parse'

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect(chunks: string[]): Promise<SseFrame[]> {
  const frames: SseFrame[] = []
  for await (const frame of parseSse(streamOf(chunks))) frames.push(frame)
  return frames
}

// Django's exact framing: `event: <name>\ndata: <json>\n\n`.
describe('parseSse', () => {
  test("parses Django's frames", async () => {
    const frames = await collect([
      'event: metadata\ndata: {"message_id": "m1", "session_id": "s1", "status": "processing"}\n\n',
      'event: delta\ndata: {"delta": "Hello"}\n\n',
      'event: done\ndata: {"status": "completed", "message_id": "m1"}\n\n',
    ])
    expect(frames.map((f) => f.event)).toEqual(['metadata', 'delta', 'done'])
    expect(JSON.parse(frames[1].data)).toEqual({ delta: 'Hello' })
  })

  test('frames split across chunks', async () => {
    const frames = await collect(['event: del', 'ta\ndata: {"delta": "a', 'b"}\n', '\n'])
    expect(frames).toEqual([{ event: 'delta', data: '{"delta": "ab"}', id: undefined }])
  })

  test('CRLF line endings, including a split \\r\\n', async () => {
    const frames = await collect(['event: delta\r', '\ndata: x\r\n\r\n'])
    expect(frames).toEqual([{ event: 'delta', data: 'x', id: undefined }])
  })

  test('comment lines are ignored', async () => {
    const frames = await collect([': ping\n\nevent: delta\ndata: y\n\n: ping\n'])
    expect(frames).toEqual([{ event: 'delta', data: 'y', id: undefined }])
  })

  test('multi-line data joins with newline', async () => {
    const frames = await collect(['data: one\ndata: two\n\n'])
    expect(frames[0].data).toBe('one\ntwo')
  })

  test('id lines are carried', async () => {
    const frames = await collect(['id: 4\nevent: delta\ndata: z\n\n'])
    expect(frames[0].id).toBe('4')
  })

  test('default event name is message', async () => {
    const frames = await collect(['data: bare\n\n'])
    expect(frames[0].event).toBe('message')
  })

  test('unterminated final frame is dispatched at EOF (forgiving)', async () => {
    const frames = await collect(['event: error\ndata: {"error": "cut off"}'])
    expect(frames).toEqual([{ event: 'error', data: '{"error": "cut off"}', id: undefined }])
  })

  test('field with no colon is a name with empty value', async () => {
    const frames = await collect(['data\n\n'])
    expect(frames[0].data).toBe('')
  })
})
