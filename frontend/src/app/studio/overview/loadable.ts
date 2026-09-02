/** The states of something the pane fetches on demand. Pure. */
export type Loadable<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

export const IDLE: Loadable<never> = { status: 'idle' }
export const LOADING: Loadable<never> = { status: 'loading' }
