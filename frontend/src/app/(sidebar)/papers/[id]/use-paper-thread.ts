'use client'

/**
 * One paper's conversations: the list of sessions filed against it, the
 * thread in hand, and the answer streaming into it. The surface that shows
 * all this (paper-chat.tsx) is layout; this is the state machine, so a
 * different surface could sit on the same hook.
 *
 * Rules, decided 9 Sep 2026:
 * - The thread outlives the surface. Collapsing never touches it; only
 *   "New chat" clears it, and the previous thread stays filed.
 * - Opening resumes the NEWEST session for this paper, settled — loaded from
 *   the server, never re-streamed. `?session=` names a specific one instead.
 * - History is `GET /bff/chat/sessions?paper_id=&mine=1`, fetched once the
 *   page is idle (so the entry card can name the thread the next question
 *   joins) and refreshed after every settled answer. `mine` matters: Django
 *   lists a whole workspace to its admins, and a thread resumed on the
 *   reader's behalf must be their own. The result is filtered by paper on
 *   the client too, so a backend that ignored the query could not show the
 *   whole workspace here.
 * - An answer can now stream with the surface collapsed, so Stop is always
 *   offered while one runs.
 * - An answer belongs to the thread it was asked in. Leaving that thread
 *   (New chat, opening another, deleting it) abandons the answer outright —
 *   the stream is cut silently and nothing of it is filed — so a late
 *   ending can never land in the thread that replaced it.
 */
import type { ChatSession, ChatSessionDetail, VisualCitation } from '@/lib/bff/chat/schema'
import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import { problemMessage } from '@/lib/bff/problem-copy'
import { useChatStream, type ChatStreamState } from '@/lib/chat/use-chat-stream'
import type { T } from '@/lib/i18n'
import { useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { timeOf } from '../../ask/types'

export interface Msg {
  role: 'user' | 'scanner'
  text: string
  /** 'HH:MM' local time a question was asked; answers carry none. */
  askedAt?: string
  /** Structured partners of the answer's inline `[Page N, …]` markers. */
  visualCitations: VisualCitation[]
  /** Mapped problem copy when the turn failed; partial `text` is kept. */
  error?: string | null
}

export type HistoryStatus = 'idle' | 'loading' | 'ready' | 'stale'

const SESSIONS_PAGE = 100

function msgsOf(detail: ChatSessionDetail, t: T): Msg[] {
  return detail.turns.flatMap((turn): Msg[] => [
    { role: 'user', text: turn.question, askedAt: timeOf(turn.created_at), visualCitations: [] },
    {
      role: 'scanner',
      text: turn.answer ?? '',
      visualCitations: turn.visual_citations,
      error: turn.status === 'failed' ? (turn.error ?? t('The answer failed.')) : null,
    },
  ])
}

/** `?session=` follows the thread in hand, so a reload or a shared link lands on it. */
function writeSessionParam(id: string | null) {
  const url = new URL(window.location.href)
  if (id) url.searchParams.set('session', id)
  else url.searchParams.delete('session')
  window.history.replaceState(window.history.state, '', url)
}

export function usePaperThread({
  paperId,
  t,
  initialSessionId = null,
}: {
  paperId: string
  t: T
  /** A `?session=` from the URL: opened instead of the newest thread. */
  initialSessionId?: string | null
}) {
  const reduceMotion = useReducedMotion()

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>('idle')
  const [activeId, setActiveIdState] = useState<string | null>(null)
  // Mirrored in a ref: a question asked right after a resume must join the
  // thread that just landed, not the one this render saw.
  const activeIdRef = useRef<string | null>(null)
  const setActiveId = (id: string | null) => {
    activeIdRef.current = id
    setActiveIdState(id)
  }
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [openingId, setOpeningIdState] = useState<string | null>(null)
  const openingRef = useRef<string | null>(null)
  const setOpeningId = (id: string | null) => {
    openingRef.current = id
    setOpeningIdState(id)
  }
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)
  // True after "New chat" until a thread is in hand again: the entry card
  // must not promise to continue the newest thread when the next question
  // deliberately starts a fresh one.
  const [fresh, setFresh] = useState(false)
  // Bumped whenever the thread in hand changes; an open or an answer that
  // began under an older epoch is discarded when it lands.
  const epochRef = useRef(0)

  const [asking, setAskingState] = useState(false)
  const askingRef = useRef(false)
  const setAsking = (v: boolean) => {
    askingRef.current = v
    setAskingState(v)
  }
  // Bumps per question so the live answer mounts fresh (its reveal position
  // is never reset, only clamped).
  const [askSeq, setAskSeq] = useState(0)

  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  /* ------------------------------ History ------------------------------ */

  // Refreshes can overlap (an answer settles while the first list is still
  // loading): only the newest request may write the list.
  const listSeq = useRef(0)
  /** The paper's sessions, newest first; null when the request failed. */
  const refreshSessions = useCallback(async (): Promise<ChatSession[] | null> => {
    const seq = ++listSeq.current
    try {
      const page = await bffFetch<Page<ChatSession>>(
        `/bff/chat/sessions?paper_id=${encodeURIComponent(paperId)}&mine=1&page_size=${SESSIONS_PAGE}`,
      )
      const mine = page.results.filter((s) => s.paper_id === paperId)
      if (seq === listSeq.current) {
        setSessions(mine)
        setHistoryStatus('ready')
      }
      return mine
    } catch (error) {
      // The list keeps its last known state — but says so instead of
      // letting a just-finished conversation silently not appear.
      console.error('[paper-chat] session refresh failed:', error)
      if (seq === listSeq.current) setHistoryStatus('stale')
      return null
    }
  }, [paperId])

  /**
   * The list is fetched once the page is idle — one small GET — so the
   * entry card can say how many chats the paper has and which one the next
   * question joins, before the console has ever been opened. The promise is
   * kept so the first open can wait on the same request instead of a
   * second; a failed one is forgotten, so the next open tries again.
   */
  const listRef = useRef<Promise<ChatSession[] | null> | null>(null)
  const fetchList = useCallback(() => {
    if (!listRef.current) {
      setHistoryStatus('loading')
      const request = refreshSessions().then((list) => {
        if (list === null && listRef.current === request) listRef.current = null
        return list
      })
      listRef.current = request
    }
    return listRef.current
  }, [refreshSessions])

  /** A list that failed (or went stale after an answer) is fetched afresh; a no-op while one loads. */
  const retryHistory = useCallback(() => {
    if (historyStatus === 'loading') return listRef.current ?? Promise.resolve(null)
    listRef.current = null
    return fetchList()
  }, [fetchList, historyStatus])

  useEffect(() => {
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number
      cancelIdleCallback?: (id: number) => void
    }
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => void fetchList(), { timeout: 2000 })
      return () => w.cancelIdleCallback?.(id)
    }
    const timer = window.setTimeout(() => void fetchList(), 800)
    return () => window.clearTimeout(timer)
  }, [fetchList])

  /* ------------------------------ Streaming ---------------------------- */

  // A stream settles into the transcript once two things are true: the
  // stream has finished (finalRef) and the reveal has shown every word
  // (revealedRef). Either can come first.
  const finalRef = useRef<ChatStreamState | null>(null)
  const revealedRef = useRef(false)
  const settleTimer = useRef(0)

  const {
    state: live,
    send,
    stop: stopStream,
    reset: resetStream,
  } = useChatStream((final) => {
    if (!askingRef.current) return
    finalRef.current = final
    trySettleRef.current()
  })

  /**
   * Drop the answer in flight without filing any of it: the stream is cut
   * silently (no ending is reported) and the settle state is cleared, so a
   * commit already on its timer finds nothing to do.
   */
  const abandon = useCallback(() => {
    if (!askingRef.current) return
    resetStream()
    finalRef.current = null
    revealedRef.current = false
    window.clearTimeout(settleTimer.current)
    settleTimer.current = 0
    setAsking(false)
  }, [resetStream])

  useEffect(() => () => window.clearTimeout(settleTimer.current), [])

  const commit = useCallback(
    (final: ChatStreamState, epoch: number) => {
      settleTimer.current = 0
      // The thread changed hands while the last words were unveiling.
      if (!askingRef.current || epoch !== epochRef.current) return
      setMsgs((prev) => [
        ...prev,
        {
          role: 'scanner',
          // A failure keeps what streamed; the error rides alongside the text.
          text: final.text,
          visualCitations: final.visualCitations,
          error: final.status === 'error' ? problemMessage(final.error, t) : null,
        },
      ])
      if (final.sessionId) {
        setActiveId(final.sessionId)
        setFresh(false)
      }
      setAsking(false)
      // The server now holds the turn (and, for a first question, the new
      // session with its title): the list catches up.
      void refreshSessions()
    },
    [t, refreshSessions],
  )

  const trySettle = useCallback(() => {
    const final = finalRef.current
    if (!final || !revealedRef.current || !askingRef.current) return
    finalRef.current = null
    revealedRef.current = false
    // Let the last words finish unveiling before the settled text takes over.
    const delay = reduceMotion || final.status === 'error' ? 0 : 600
    const epoch = epochRef.current
    window.clearTimeout(settleTimer.current)
    settleTimer.current = window.setTimeout(() => commit(final, epoch), delay)
  }, [commit, reduceMotion])
  const trySettleRef = useRef(trySettle)
  useEffect(() => {
    trySettleRef.current = trySettle
  }, [trySettle])

  const onRevealed = useCallback(() => {
    revealedRef.current = true
    trySettle()
  }, [trySettle])

  /**
   * The surface that shows the reveal is gone (the console collapsed while
   * an answer ran): nothing will report the reveal, so the answer is filed
   * in full the moment the stream ends. Reopening finds it settled.
   */
  const settleBlind = useCallback(() => {
    if (!askingRef.current) return
    revealedRef.current = true
    trySettle()
  }, [trySettle])

  /* ------------------------------ Threads ------------------------------ */

  /** Opens a filed thread; false when it did not (in flight, or failed). */
  const openThread = useCallback(
    async (session: ChatSession): Promise<boolean> => {
      if (openingRef.current) return false
      // Already in hand and settled: nothing to fetch.
      if (session.id === activeIdRef.current && !askingRef.current) return true
      // Leaving the thread in hand: its running answer goes with it.
      abandon()
      const epoch = ++epochRef.current
      setOpeningId(session.id)
      setRowError(null)
      try {
        const detail = await bffFetch<ChatSessionDetail>(`/bff/chat/sessions/${session.id}`)
        if (epoch !== epochRef.current) return false
        setActiveId(detail.id)
        setMsgs(msgsOf(detail, t))
        setFresh(false)
        return true
      } catch (error) {
        console.error('[paper-chat] open failed:', error)
        if (epoch === epochRef.current) {
          setRowError({ id: session.id, message: t("Couldn't open this conversation. Try again.") })
        }
        return false
      } finally {
        setOpeningId(null)
      }
    },
    [t, abandon],
  )

  /**
   * The first open: wait for the list, then land on the thread the URL
   * names or, failing that, the newest. Later opens find the thread where it
   * was left. One promise, so a double click or a question typed on the
   * entry card in the same tick waits on the same resume — and a resume
   * that failed is forgotten, so the next open tries again rather than
   * showing a blank thread over a filed one.
   */
  const resumeRef = useRef<Promise<void> | null>(null)
  const resumeSeq = useRef(0)
  const ensureLoaded = useCallback(() => {
    if (!resumeRef.current) {
      const seq = ++resumeSeq.current
      const epoch = epochRef.current
      // Forgotten only while it is still the resume in hand.
      const forget = () => {
        if (resumeSeq.current === seq) resumeRef.current = null
      }
      resumeRef.current = (async () => {
        const list = await fetchList()
        if (list === null) return forget()
        // "New chat" pressed while the list was loading: the reader chose
        // a blank thread over the newest one.
        if (epochRef.current !== epoch) return
        let wanted: ChatSession | undefined = list[0]
        if (initialSessionId) {
          wanted = list.find((s) => s.id === initialSessionId)
          // A link to a thread that is not this paper's (or not the
          // reader's, or gone): the console opens blank rather than on a
          // thread the link never named, and the URL stops claiming it.
          if (!wanted) writeSessionParam(null)
        }
        if (wanted && !(await openThread(wanted))) forget()
      })()
    }
    return resumeRef.current
  }, [fetchList, initialSessionId, openThread])

  useEffect(() => {
    if (!resumeRef.current) return
    writeSessionParam(activeId)
  }, [activeId])

  const ask = useCallback(
    (q: string) => {
      const question = q.trim()
      if (!question || askingRef.current) return false
      // A reveal reported after its answer was already filed must not let
      // this one settle before its own reveal has caught up.
      finalRef.current = null
      revealedRef.current = false
      setMsgs((prev) => [
        ...prev,
        {
          role: 'user',
          text: question,
          askedAt: timeOf(new Date().toISOString()),
          visualCitations: [],
        },
      ])
      setAsking(true)
      setAskSeq((n) => n + 1)
      void send({
        question,
        paper_id: paperId,
        session_id: activeIdRef.current ?? undefined,
        deep_thinking: false,
      })
      return true
    },
    [paperId, send],
  )

  /** The reader's stop: what has arrived is filed as the answer. */
  const stop = useCallback(() => {
    if (!askingRef.current) return
    stopStream()
  }, [stopStream])

  /** A blank thread; the one in hand stays filed, its running answer abandoned. */
  const newChat = useCallback(() => {
    abandon()
    epochRef.current += 1
    setActiveId(null)
    setMsgs([])
    setFresh(true)
  }, [abandon])

  const requestDelete = useCallback((session: ChatSession) => {
    setDeleteError(null)
    setPendingDelete(session)
  }, [])

  const cancelDelete = useCallback(() => {
    if (deleting) return
    setPendingDelete(null)
    setDeleteError(null)
  }, [deleting])

  const confirmDelete = useCallback(async () => {
    const session = pendingDelete
    if (!session || deleting) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await bffFetch<void>(`/bff/chat/sessions/${session.id}`, { method: 'DELETE' })
      setSessions((prev) => prev.filter((s) => s.id !== session.id))
      if (session.id === activeIdRef.current) newChat()
      setPendingDelete(null)
      // The row — the outcome's anchor — is gone, so this is the one place
      // a toast is right (see the Toaster note in app/layout.tsx).
      toast(t('Conversation deleted'))
    } catch (error) {
      // The dialog stays open: a failed destructive action is never silent.
      console.error('[paper-chat] delete failed:', error)
      setDeleteError(t("Couldn't delete this conversation. Try again."))
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete, deleting, newChat, t])

  const firstQuestion = msgs.find((m) => m.role === 'user')?.text
  const title = sessions.find((s) => s.id === activeId)?.title ?? firstQuestion ?? t('New chat')
  // The thread the entry card promises to continue: the one in hand, else
  // the newest — unless the reader has just chosen a blank one.
  const resumeTarget = fresh
    ? null
    : (sessions.find((s) => s.id === activeId) ?? sessions[0] ?? null)

  return {
    sessions,
    historyStatus,
    activeId,
    msgs,
    title,
    resumeTarget,
    openingId,
    rowError,
    asking,
    live,
    askSeq,
    onRevealed,
    settleBlind,
    ask,
    stop,
    newChat,
    openThread,
    ensureLoaded,
    retryHistory,
    pendingDelete,
    deleting,
    deleteError,
    requestDelete,
    cancelDelete,
    confirmDelete,
  }
}
