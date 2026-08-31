import { cookies } from 'next/headers'
import { LANG_COOKIE, makeT, type Lang, type T } from './i18n'

export async function getLang(): Promise<Lang> {
  const stored = (await cookies()).get(LANG_COOKIE)?.value
  return stored === 'de' ? 'de' : 'en'
}

export async function getT(): Promise<T> {
  return makeT(await getLang())
}
