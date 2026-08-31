/**
 * Emits OUR SSE contract: `id:`-sequenced frames, single-line JSON data,
 * `: ping` heartbeat comments every 15 s (keeps proxies and Gorouter's idle
 * timeout from cutting long generations). Safe against late writes after
 * close/abort.
 */

export class SseWriter {
  private seq = 0
  private closed = false
  private heartbeat: ReturnType<typeof setInterval> | null = null
  private readonly encoder = new TextEncoder()

  constructor(private readonly controller: ReadableStreamDefaultController<Uint8Array>) {}

  frame(event: string, data: unknown): void {
    this.write(`id: ${++this.seq}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  }

  comment(text: string): void {
    this.write(`: ${text}\n\n`)
  }

  startHeartbeat(ms = 15_000): void {
    this.heartbeat = setInterval(() => this.comment(`ping ${new Date().toISOString()}`), ms)
  }

  close(): void {
    if (this.closed) return
    this.closed = true
    if (this.heartbeat) clearInterval(this.heartbeat)
    try {
      this.controller.close()
    } catch {
      // Already errored/cancelled.
    }
  }

  private write(text: string): void {
    if (this.closed) return
    try {
      this.controller.enqueue(this.encoder.encode(text))
    } catch {
      this.closed = true
      if (this.heartbeat) clearInterval(this.heartbeat)
    }
  }
}
