import { createContext, useContext, useEffect, useState } from 'react'

/** An error status from the server, with its JSON body (e.g. {detail: {errors: [...]}}). */
export class ApiError extends Error {
  constructor(public status: number, public body: any) { super(`${status}`) }
}

/** JSON from the gate server (server.py); throws on a network error or an ApiError. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (res.status === 401 && path !== '/api/login') dispatchEvent(new Event('gate-auth'))  // signed out: App shows Login
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
  return res.json()
}

/** /api/auth: is a site password set, is this the gate computer, is this device signed in. */
export type Auth = { password_set: boolean; local: boolean; logged_in: boolean }

/** The current picture of an NVR channel, as an object URL (throws ApiError with a text key). */
export async function cameraPicture(channel: number): Promise<string> {
  const res = await fetch('/api/cameras/frame', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel }),
  })
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
  return URL.createObjectURL(await res.blob())
}

/** Send JSON with `method` (PATCH, POST, ...). */
export const send = <T>(method: string, path: string, body: unknown) =>
  api<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

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
 *  fails (until one succeeds), `at` changes on every successful refresh, `reload()` fetches now. */
export function usePoll<T>(path: string | null, everyMs: number) {
  const [state, setState] = useState<{ data?: T; failed: boolean; at: number }>({ failed: false, at: 0 })
  const [nudge, setNudge] = useState(0)
  useEffect(() => { setState({ failed: false, at: 0 }) }, [path])  // a new path: don't show the old path's data
  useEffect(() => {
    if (!path) return
    let alive = true
    const load = () => api<T>(path)
      .then((data) => alive && setState({ data, failed: false, at: Date.now() }))
      .catch(() => alive && setState((s) => ({ ...s, failed: true })))
    load()
    const id = setInterval(load, everyMs)
    return () => { alive = false; clearInterval(id) }
  }, [path, everyMs, nudge])
  return { ...state, reload: () => setNudge((n) => n + 1) }
}

/** A truck row as /api/records returns it (snapshot / plate_image: is there a photo). */
export type Truck = {
  id: number; date: string; time: string; direction: 'IN' | 'OUT' | null
  plate: string | null; plate_ar: string | null; plate_verified: number | null
  container: string | null; check_digit_ok: number | null; size_type: string | null
  camera: string | null; location: string | null; confidence: number | null
  corrected: number; needs_review: boolean; snapshot: boolean; plate_image: boolean
}
