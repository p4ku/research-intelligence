import { describe, expect, test } from 'bun:test'
import { reduceKey } from './keys'

const closed = { open: false, cursor: -1, hasText: true }
const openNone = { open: true, cursor: -1, hasText: true }
const openAt = (cursor: number) => ({ open: true, cursor, hasText: true })

describe('reduceKey', () => {
  test('ArrowDown opens, then walks down without wrapping', () => {
    expect(reduceKey('ArrowDown', closed, 3)).toEqual({ type: 'cursor', cursor: 0 })
    expect(reduceKey('ArrowDown', openNone, 3)).toEqual({ type: 'cursor', cursor: 0 })
    expect(reduceKey('ArrowDown', openAt(1), 3)).toEqual({ type: 'cursor', cursor: 2 })
    expect(reduceKey('ArrowDown', openAt(2), 3)).toEqual({ type: 'cursor', cursor: 2 })
    expect(reduceKey('ArrowDown', closed, 0)).toEqual({ type: 'open' })
    expect(reduceKey('ArrowDown', openNone, 0)).toEqual({ type: 'none' })
  })

  test('ArrowUp walks up to nothing highlighted, never past it', () => {
    expect(reduceKey('ArrowUp', openAt(2), 3)).toEqual({ type: 'cursor', cursor: 1 })
    expect(reduceKey('ArrowUp', openAt(0), 3)).toEqual({ type: 'cursor', cursor: -1 })
    expect(reduceKey('ArrowUp', openNone, 3)).toEqual({ type: 'none' })
    expect(reduceKey('ArrowUp', closed, 3)).toEqual({ type: 'none' })
  })

  test('Enter activates a highlighted row, otherwise submits', () => {
    expect(reduceKey('Enter', openAt(1), 3)).toEqual({ type: 'activate' })
    expect(reduceKey('Enter', openNone, 3)).toEqual({ type: 'submit' })
    expect(reduceKey('Enter', closed, 3)).toEqual({ type: 'submit' })
    expect(reduceKey('Enter', openAt(5), 3)).toEqual({ type: 'submit' })
  })

  test('Escape closes first, clears second, then nothing', () => {
    expect(reduceKey('Escape', openAt(1), 3)).toEqual({ type: 'close' })
    expect(reduceKey('Escape', closed, 3)).toEqual({ type: 'clear' })
    expect(reduceKey('Escape', { ...closed, hasText: false }, 3)).toEqual({ type: 'none' })
  })

  test('Tab closes an open panel and is otherwise left alone', () => {
    expect(reduceKey('Tab', openNone, 3)).toEqual({ type: 'close' })
    expect(reduceKey('Tab', closed, 3)).toEqual({ type: 'none' })
    expect(reduceKey('a', openAt(1), 3)).toEqual({ type: 'none' })
  })
})
