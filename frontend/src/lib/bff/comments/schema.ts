import * as z from 'zod'

export const commentAuthor = z.object({
  id: z.number(),
  username: z.string(),
  email: z.string().optional().default(''),
  name: z.string().optional().default(''),
})

export type CommentAuthor = z.infer<typeof commentAuthor>

export const commentReactionGroup = z.object({
  reaction_type: z.string(),
  count: z.number().default(0),
  users: z.array(z.string()).default([]),
  has_reacted: z.boolean().default(false),
})

export type CommentReactionGroup = z.infer<typeof commentReactionGroup>

export const toggleReactionResponse = z.object({
  action: z.enum(['added', 'removed']),
  reactions: z.array(commentReactionGroup),
})

export type ToggleReactionResponse = z.infer<typeof toggleReactionResponse>

export const paperComment = z.object({
  id: z.string(),
  paper_id: z.string().optional().default(''),
  pipeline_run_id: z.string().nullable().optional().default(null),
  user: commentAuthor,
  content: z.string(),
  created_at: z.string(),
  updated_at: z.string().optional().default(''),
  is_edited: z.boolean().optional().default(false),
  is_deleted: z.boolean().optional().default(false),
  reactions: z.array(commentReactionGroup).optional().default([]),
})

export type PaperComment = z.infer<typeof paperComment>

export const createCommentBody = z.object({
  content: z.string().min(1, 'Comment cannot be empty'),
})

export type CreateCommentBody = z.infer<typeof createCommentBody>

export const updateCommentBody = z.object({
  content: z.string().min(1, 'Comment cannot be empty'),
})

export type UpdateCommentBody = z.infer<typeof updateCommentBody>
