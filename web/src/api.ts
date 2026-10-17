import { createContext, useContext, useEffect, useState } from 'react'

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

export const useLang = () => useContext(TextContext).lang

/** GET `path` now and every `everyMs` (nothing while path is null). `failed` once a request
 *  fails (until one succeeds), `at` changes on every successful refresh. */
export function usePoll<T>(path: string | null, everyMs: number) {
  const [state, setState] = useState<{ data?: T; failed: boolean; at: number }>({ failed: false, at: 0 })
  useEffect(() => {
    setState({ failed: false, at: 0 })  // a new path: don't show the old path's data
    if (!path) return
    let alive = true
    const load = () => api<T>(path)
      .then((data) => alive && setState({ data, failed: false, at: Date.now() }))
      .catch(() => alive && setState((s) => ({ ...s, failed: true })))
    load()
    const id = setInterval(load, everyMs)
    return () => { alive = false; clearInterval(id) }
  }, [path, everyMs])
  return state
}

/** A truck row as /api/records returns it (snapshot / plate_image: is there a photo). */
export type Truck = {
  id: number; date: string; time: string; direction: 'IN' | 'OUT' | null
  plate: string | null; plate_ar: string | null; plate_verified: number | null
  container: string | null; check_digit_ok: number | null; size_type: string | null
  camera: string | null; location: string | null; confidence: number | null
  corrected: number; needs_review: boolean; snapshot: boolean; plate_image: boolean
}
