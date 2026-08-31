/**
 * Minimal WHATWG-compatible Server-Sent-Events parser. Isomorphic and pure:
 * the BFF re-framer uses it against Django's stream, and the browser hook
 * uses it against ours.
 */

export interface SseFrame {
  event: string
  /** Multi-line `data:` fields joined with `\n`; always a string. */
  data: string
  id?: string
}

export async function* parseSse(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let event = ''
  let data: string[] = []
  let id: string | undefined

  const pending = (): SseFrame | null => {
    if (data.length === 0) return null
    const frame: SseFrame = { event: event || 'message', data: data.join('\n'), id }
    event = ''
    data = []
    return frame
  }

  const handleLine = (line: string): SseFrame | null => {
    if (line === '') return pending()
    if (line.startsWith(':')) return null
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
    else if (field === 'id' && !value.includes('\0')) id = value
    // Other fields (`retry`, unknown) are ignored.
    return null
  }

  try {
    while (true) {
      if (signal?.aborted) return
      const { done, value } = await reader.read()
      if (value) buffer += decoder.decode(value, { stream: true })
      if (done) buffer += decoder.decode()

      let index: number
      while ((index = buffer.search(/\r\n|\r|\n/)) !== -1) {
        // A lone `\r` at the end of the buffer may be half of a `\r\n`.
        if (buffer[index] === '\r' && index === buffer.length - 1 && !done) break
        const line = buffer.slice(0, index)
        buffer = buffer.slice(index + (buffer[index] === '\r' && buffer[index + 1] === '\n' ? 2 : 1))
        const frame = handleLine(line)
        if (frame) yield frame
      }

      if (done) {
        // Forgiving EOF: dispatch a trailing line/frame the server never terminated.
        if (buffer !== '') handleLine(buffer)
        const frame = pending()
        if (frame) yield frame
        return
      }
    }
  } finally {
    reader.releaseLock()
  }
}
