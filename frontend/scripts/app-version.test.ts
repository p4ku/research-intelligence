import { describe, expect, test } from 'bun:test'
import {
  composeVersion,
  resolveAppCommit,
  resolveAppVersion,
  versionPrefix,
} from './app-version.mjs'

describe('app version', () => {
  test('major.minor come from the package version', () => {
    expect(versionPrefix('0.1.0')).toBe('0.1')
    expect(versionPrefix('2.7.13')).toBe('2.7')
  })

  test('the patch component is the commit count', () => {
    expect(composeVersion('0.1', 45)).toBe('0.1.45')
    expect(composeVersion('0.1', null)).toBe('0.1.0-local')
  })

  test('APP_VERSION wins outright (Docker builds have no git)', () => {
    expect(resolveAppVersion({ APP_VERSION: '0.1.99' })).toBe('0.1.99')
  })

  test('derives a well-formed version from this checkout', () => {
    expect(resolveAppVersion({})).toMatch(/^\d+\.\d+\.(\d+|0-local)$/)
  })

  test('BUILD_ID is the commit when set', () => {
    expect(resolveAppCommit({ BUILD_ID: 'abc123' })).toBe('abc123')
  })
})
