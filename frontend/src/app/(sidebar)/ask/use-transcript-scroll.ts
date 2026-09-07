'use client'

/**
 * The transcript's scroll model. The last turn reserves the viewport, so a
 * fresh question can sit at the top with its answer streaming into the open
 * space beneath it. While an answer streams the view follows the text on a
 * spring; a scroll-up from the reader releases it and offers a way back.
 *
 * Every position we write is remembered. A scroll event (or a spring frame)
 * that finds the container *above* that position can only be the reader's
 * doing — that is the release signal, with no debounce and no wheel listener.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const DAMPING = 0.72
const STIFFNESS = 0.14
const ANCHOR_MS = 380
const NEAR_BOTTOM_PX = 48
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4)

export function useTranscriptScroll(reduceMotion: boolean) {
  const ref = useRef<HTMLDivElement>(null)
  const [jump, setJump] = useState(false)
  const pinned = useRef(true)
  const busy = useRef(false)
  const sc = useRef({ raf: 0, vel: 0, lastWrite: -1, anchoring: 0 })

  const write = useCallback((top: number) => {
    const el = ref.current
    if (!el) return
    sc.current.lastWrite = Math.max(0, Math.min(top, el.scrollHeight - el.clientHeight))
    el.scrollTop = sc.current.lastWrite
  }, [])

  const readerScrolledUp = () => {
    const el = ref.current
    return !!el && sc.current.lastWrite >= 0 && el.scrollTop < sc.current.lastWrite - 1
  }

  const atBottom = () => {
    const el = ref.current
    return !!el && el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
  }

  const release = useCallback(() => {
    if (!pinned.current) return
    pinned.current = false
    sc.current.vel = 0
    setJump(true)
  }, [])

  /** An eased glide to a position, written by us frame by frame. */
  const anchorTo = useCallback(
    (top: number) => {
      const el = ref.current
      if (!el) return
      cancelAnimationFrame(sc.current.raf)
      sc.current.raf = 0
      sc.current.vel = 0
      const from = el.scrollTop
      const dist = top - from
      if (reduceMotion || Math.abs(dist) < 2) {
        write(top)
        return
      }
      const t0 = performance.now()
      sc.current.anchoring += 1
      const frame = (now: number) => {
        const t = Math.min(1, (now - t0) / ANCHOR_MS)
        write(from + dist * easeOut(t))
        if (t < 1) sc.current.raf = requestAnimationFrame(frame)
        else {
          sc.current.raf = 0
          sc.current.anchoring -= 1
        }
      }
      sc.current.raf = requestAnimationFrame(frame)
    },
    [reduceMotion, write],
  )

  /** Follow the growing answer: a spring toward the bottom while pinned. */
  const follow = useCallback(() => {
    const el = ref.current
    if (!el || !pinned.current || sc.current.anchoring) return
    if (reduceMotion) {
      write(el.scrollHeight)
      return
    }
    if (sc.current.raf) return
    const frame = () => {
      sc.current.raf = 0
      if (!pinned.current) {
        sc.current.vel = 0
        return
      }
      if (readerScrolledUp()) {
        release()
        return
      }
      const target = el.scrollHeight - el.clientHeight
      const dist = target - el.scrollTop
      if (Math.abs(dist) < 0.5 && Math.abs(sc.current.vel) < 0.5) {
        sc.current.vel = 0
        return
      }
      sc.current.vel = sc.current.vel * DAMPING + dist * STIFFNESS
      write(el.scrollTop + sc.current.vel)
      sc.current.raf = requestAnimationFrame(frame)
    }
    sc.current.raf = requestAnimationFrame(frame)
  }, [reduceMotion, release, write])

  /** A new question: pin, and glide it to the top of the transcript. */
  const anchorTurn = useCallback(
    (turn: HTMLElement) => {
      pinned.current = true
      setJump(false)
      anchorTo(turn.offsetTop - 8)
    },
    [anchorTo],
  )

  const jumpToLatest = useCallback(() => {
    const el = ref.current
    if (!el) return
    pinned.current = true
    setJump(false)
    anchorTo(el.scrollHeight - el.clientHeight)
  }, [anchorTo])

  const onScroll = useCallback(() => {
    if (atBottom()) {
      pinned.current = true
      setJump(false)
      return
    }
    if (busy.current && !sc.current.anchoring && readerScrolledUp()) release()
  }, [release])

  /** Whether an answer is in flight (only then does a scroll-up release). */
  const setBusy = useCallback((value: boolean) => {
    busy.current = value
  }, [])

  // The last turn's reserved height tracks the container.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => el.style.setProperty('--turn-min', `${el.clientHeight - 16}px`)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  })

  useEffect(() => () => cancelAnimationFrame(sc.current.raf), [])

  return { ref, jump, onScroll, anchorTurn, follow, jumpToLatest, setBusy }
}
