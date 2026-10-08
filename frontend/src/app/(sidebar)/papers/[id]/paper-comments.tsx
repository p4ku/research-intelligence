'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Card, ErrorNote } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Spinner } from '@/components/ui/spinner'
import type { SessionUser } from '@/lib/auth/session'
import { bffFetch } from '@/lib/bff/client'
import type { PaperComment } from '@/lib/bff/comments/schema'
import { useT } from '@/lib/i18n-client'
import {
  ChatBubbleLeftEllipsisIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { toast } from 'sonner'
import { ICON_BUTTON } from '../../ask/console-frame'

export interface PaperCommentsProps {
  paperId: string
  currentUser?: SessionUser | null
}

export function formatCommentDate(iso: string): string {
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function userInitials(name?: string, username?: string): string {
  const src = (name || username || '?').trim()
  const parts = src.split(/\s+/)
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return src.slice(0, 2).toUpperCase()
}

export function PaperComments({ paperId, currentUser = null }: PaperCommentsProps) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [comments, setComments] = useState<PaperComment[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [draft, setDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const [pendingDelete, setPendingDelete] = useState<PaperComment | null>(null)
  const [deleting, setDeleting] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

  const listRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const fetchComments = useCallback(async () => {
    try {
      setLoading(true)
      setLoadError(null)
      const res = await bffFetch<{ comments: PaperComment[]; count: number }>(
        `/bff/papers/${paperId}/comments`,
      )
      setComments(res.comments ?? [])
      setLoaded(true)
    } catch (err) {
      console.error('[comments] fetch failed:', err)
      setLoadError(t('Could not load comments.'))
    } finally {
      setLoading(false)
    }
  }, [paperId, t])

  useEffect(() => {
    void fetchComments()
  }, [fetchComments])

  // Focus textarea when expanded
  useEffect(() => {
    if (open) {
      const timer = window.setTimeout(() => {
        textareaRef.current?.focus({ preventScroll: true })
      }, 100)
      return () => window.clearTimeout(timer)
    }
  }, [open])

  // Scroll to bottom when new comment is added or when opened / loaded
  const scrollToBottom = useCallback(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [])

  useEffect(() => {
    if (open && loaded) {
      scrollToBottom()
      const timer = window.setTimeout(scrollToBottom, 60)
      const frame = window.requestAnimationFrame(scrollToBottom)
      return () => {
        window.clearTimeout(timer)
        window.cancelAnimationFrame(frame)
      }
    }
  }, [open, loaded, comments.length, scrollToBottom])

  const handleSubmit = async (e?: FormEvent) => {
    if (e) e.preventDefault()
    const content = draft.trim()
    if (!content || submitting) return

    setSubmitting(true)
    setSubmitError(null)

    try {
      const newComment = await bffFetch<PaperComment>(`/bff/papers/${paperId}/comments`, {
        method: 'POST',
        body: JSON.stringify({ content }),
      })
      setComments((prev) => [...prev, newComment])
      setDraft('')
      setTimeout(scrollToBottom, 50)
      toast.success(t('Comment added'))
    } catch (err) {
      console.error('[comments] post failed:', err)
      setSubmitError(t('Could not post comment. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      void handleSubmit()
    }
  }

  const startEditing = (comment: PaperComment) => {
    setEditingId(comment.id)
    setEditDraft(comment.content)
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditDraft('')
  }

  const handleSaveEdit = async (commentId: string) => {
    const content = editDraft.trim()
    if (!content || savingEdit) return

    setSavingEdit(true)
    try {
      const updated = await bffFetch<PaperComment>(`/bff/papers/${paperId}/comments/${commentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ content }),
      })
      setComments((prev) =>
        prev.map((c) => (c.id === commentId ? { ...c, ...updated, is_edited: true } : c)),
      )
      setEditingId(null)
      setEditDraft('')
      toast.success(t('Comment updated'))
    } catch (err) {
      console.error('[comments] update failed:', err)
      toast.error(t('Could not update comment.'))
    } finally {
      setSavingEdit(false)
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete || deleting) return
    setDeleting(true)

    try {
      await bffFetch<void>(`/bff/papers/${paperId}/comments/${pendingDelete.id}`, {
        method: 'DELETE',
      })
      setComments((prev) => prev.filter((c) => c.id !== pendingDelete.id))
      setPendingDelete(null)
      toast(t('Comment deleted'))
    } catch (err) {
      console.error('[comments] delete failed:', err)
      toast.error(t('Could not delete comment.'))
    } finally {
      setDeleting(false)
    }
  }

  const count = comments.length

  /* ------------------- Collapsed view ------------------- */
  if (!open) {
    return (
      <Card
        flush
        data-shape="paper-comments-card"
        className="mt-3 overflow-hidden transition-all duration-150"
      >
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          className="flex w-full items-center gap-2 px-4 pt-3 text-left font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase transition-transform duration-150 ease-out focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent active:scale-[0.985]"
        >
          <ChatBubbleLeftEllipsisIcon
            aria-hidden="true"
            className="size-3.5 shrink-0 text-accent"
          />
          {t('Comments')}
          <span className="ml-auto font-mono text-[11px] tracking-normal text-zinc-400 tabular-nums dark:text-zinc-500">
            {!loaded && loading ? <Bone.Text widths={['1ch']} /> : count}
          </span>
        </button>

        <p className="px-4 pt-1.5 pb-2.5 text-xs text-muted-foreground">
          {count === 0
            ? t('No comments yet. Start a discussion.')
            : count === 1
              ? t('1 note on this paper.')
              : `${count} ${t('notes on this paper.')}`}
        </p>

        <div className="border-t border-line-soft transition-colors focus-within:border-foreground/20">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="flex w-full items-center justify-between gap-2 p-1.5 pr-2.5 pl-4 text-left text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <span className="text-sm text-zinc-400 dark:text-zinc-500">{t('Add a comment…')}</span>
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground/10 text-muted-foreground transition-colors hover:bg-foreground/20">
              <ChatBubbleLeftEllipsisIcon className="size-3.5" />
            </span>
          </button>
        </div>
      </Card>
    )
  }

  /* ------------------- Expanded console view ------------------- */
  return (
    <>
      <div
        data-shape="paper-comments-console"
        data-console-open=""
        data-comments-open=""
        role="region"
        aria-label={t('Paper comments')}
        className="mt-3 flex flex-col"
      >
        <Card flush className="flex min-h-0 flex-col overflow-hidden">
          {/* Header */}
          <div className="flex shrink-0 items-center justify-between border-b border-line-soft py-1.5 pr-2 pl-4">
            <div className="flex items-center gap-2 font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase">
              <ChatBubbleLeftEllipsisIcon
                aria-hidden="true"
                className="size-3.5 shrink-0 text-accent"
              />
              {t('Comments')}
              <span className="font-mono text-[11px] tracking-normal text-zinc-400 tabular-nums dark:text-zinc-500">
                ({count})
              </span>
            </div>

            <div className="flex shrink-0 items-center">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t('Collapse')}
                title={t('Collapse')}
                className={ICON_BUTTON}
              >
                <XMarkIcon className="size-4" />
              </button>
            </div>
          </div>

          {/* Comments list scroller */}
          <div
            ref={listRef}
            className="max-h-[200px] min-h-[90px] flex-1 overflow-y-auto overscroll-contain px-4 py-3 lg:max-h-[min(220px,calc(100vh-480px))]"
          >
            {loading && !loaded ? (
              <div className="space-y-4 py-2">
                <Bone.Text lines={2} widths={['40%', '90%']} />
                <Bone.Text lines={2} widths={['30%', '75%']} />
              </div>
            ) : loadError ? (
              <ErrorNote className="my-2">{loadError}</ErrorNote>
            ) : count === 0 ? (
              <div className="flex min-h-[90px] flex-col items-center justify-center text-center">
                <p className="text-xs text-muted-foreground">{t('No comments yet.')}</p>
                <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                  {t('Leave the first note or discussion point below.')}
                </p>
              </div>
            ) : (
              <div className="space-y-3.5 divide-y divide-line-soft">
                {comments.map((comment, index) => {
                  const authorName = comment.user?.name || comment.user?.username || t('Anonymous')
                  const isAuthor =
                    Boolean(currentUser) &&
                    (currentUser?.id === comment.user?.id ||
                      currentUser?.username === comment.user?.username)
                  const canEdit = isAuthor
                  const canDelete = isAuthor || Boolean(currentUser?.isStaff)
                  const isEditing = editingId === comment.id

                  return (
                    <article
                      key={comment.id}
                      className={clsx('group/comment min-w-0', index > 0 && 'pt-3.5')}
                    >
                      {/* Meta header */}
                      <header className="flex items-center gap-1.5 text-xs">
                        <div
                          aria-hidden="true"
                          className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent/15 font-mono text-[10px] font-bold text-accent"
                        >
                          {userInitials(comment.user?.name, comment.user?.username)}
                        </div>

                        <span className="truncate font-medium text-foreground">{authorName}</span>

                        {isAuthor && (
                          <span className="py-0.2 rounded bg-accent/10 px-1 font-mono text-[10px] text-accent">
                            {t('You')}
                          </span>
                        )}

                        <span aria-hidden="true" className="text-zinc-300 dark:text-zinc-600">
                          ·
                        </span>

                        <time
                          dateTime={comment.created_at}
                          className="shrink-0 text-[11px] text-muted-foreground"
                        >
                          {formatCommentDate(comment.created_at)}
                        </time>

                        {comment.is_edited && (
                          <span className="text-[10px] text-muted-foreground">({t('edited')})</span>
                        )}

                        {/* Author actions */}
                        {(canEdit || canDelete) && !isEditing && (
                          <div className="ml-auto inline-flex items-center gap-0.5 opacity-70 transition-all group-hover/comment:opacity-100">
                            {canEdit && (
                              <button
                                type="button"
                                onClick={() => startEditing(comment)}
                                aria-label={t('Edit comment')}
                                title={t('Edit comment')}
                                className="inline-flex items-center justify-center rounded p-1 text-zinc-400 hover:text-foreground hover:opacity-100"
                              >
                                <PencilSquareIcon className="size-3.5" />
                              </button>
                            )}
                            {canDelete && (
                              <button
                                type="button"
                                onClick={() => setPendingDelete(comment)}
                                aria-label={t('Delete comment')}
                                title={t('Delete comment')}
                                className="inline-flex items-center justify-center rounded p-1 text-zinc-400 hover:text-red-600 hover:opacity-100 dark:hover:text-red-400"
                              >
                                <TrashIcon className="size-3.5" />
                              </button>
                            )}
                          </div>
                        )}
                      </header>

                      {/* Comment content or Inline editor */}
                      {isEditing ? (
                        <div className="mt-2 pl-6">
                          <textarea
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') {
                                e.preventDefault()
                                cancelEditing()
                              } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                                e.preventDefault()
                                void handleSaveEdit(comment.id)
                              }
                            }}
                            rows={2}
                            autoFocus
                            className="w-full resize-none rounded-sm border border-accent bg-transparent p-2 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground focus:ring-1 focus:ring-accent focus:outline-none"
                          />
                          <div className="mt-1.5 flex items-center justify-between">
                            <span className="font-mono text-[10px] text-muted-foreground">
                              esc {t('to cancel')} · ⌘↵ {t('to save')}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={cancelEditing}
                                disabled={savingEdit}
                                className="rounded-sm px-2 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                              >
                                {t('Cancel')}
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleSaveEdit(comment.id)}
                                disabled={!editDraft.trim() || savingEdit}
                                className={clsx(
                                  'inline-flex items-center gap-1 rounded-sm px-2.5 py-0.5 font-mono text-[11px] font-medium transition-colors',
                                  editDraft.trim() && !savingEdit
                                    ? 'bg-foreground text-background hover:bg-foreground/85'
                                    : 'cursor-not-allowed bg-foreground/10 text-muted-foreground',
                                )}
                              >
                                {savingEdit && (
                                  <Spinner className="size-2.5 shrink-0" aria-hidden="true" />
                                )}
                                {savingEdit ? t('Saving…') : t('Save')}
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-1.5 pl-6 text-[13px] leading-relaxed text-foreground">
                          <AnswerMarkdown text={comment.content} />
                        </div>
                      )}
                    </article>
                  )
                })}
              </div>
            )}
          </div>

          {/* Composer */}
          <form
            onSubmit={handleSubmit}
            className="shrink-0 border-t border-line-soft bg-surface p-3"
          >
            {submitError && <ErrorNote className="mb-2">{submitError}</ErrorNote>}

            <div className="relative">
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('Write a comment… (Markdown supported)')}
                rows={2}
                className="w-full resize-none rounded-sm border border-line bg-transparent p-2 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
              />
            </div>

            <div className="mt-2 flex items-center justify-between">
              <span className="font-mono text-[10px] text-muted-foreground">⌘↵ {t('to send')}</span>

              <button
                type="submit"
                disabled={!draft.trim() || submitting}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-sm px-3 py-1 font-mono text-xs font-medium transition-[background-color,color,transform] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.97]',
                  draft.trim() && !submitting
                    ? 'bg-foreground text-background hover:bg-foreground/85'
                    : 'cursor-not-allowed bg-foreground/10 text-muted-foreground',
                )}
              >
                {submitting ? (
                  <>
                    <Spinner className="size-3 shrink-0" aria-hidden="true" />
                    <span>{t('Posting…')}</span>
                  </>
                ) : (
                  <>
                    <PaperAirplaneIcon className="size-3 shrink-0" aria-hidden="true" />
                    <span>{t('Comment')}</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </Card>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen && !deleting) setPendingDelete(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('Delete comment?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('This comment will be permanently removed. This action cannot be undone.')}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t('Cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={deleting}
              onClick={(e) => {
                e.preventDefault()
                void confirmDelete()
              }}
              className="bg-red-600 text-white hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
            >
              {deleting && <Spinner className="size-3.5" aria-hidden="true" />}
              {deleting ? t('Deleting…') : t('Delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
