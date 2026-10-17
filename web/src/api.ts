import { createContext, useContext } from 'react'

/** JSON from the gate server (server.py); throws on a network error or an error status. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export type Lang = 'en' | 'ar'
export type TextTable = Record<string, [string, string]>

export const TextContext = createContext<{ lang: Lang; text: TextTable }>({ lang: 'en', text: {} })

/** t('camera_saved', { name }) -> text in the current language, like t() in src/i18n.py. */
export function useT() {
  const { lang, text } = useContext(TextContext)
  return (key: string, vars: Record<string, string | number> = {}) => {
    let s = text[key]?.[lang === 'ar' ? 1 : 0] ?? key
    for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v))
    return s
  }
}
