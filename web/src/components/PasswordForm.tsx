import { useState } from 'react'
import { Alert, Button, Group, PasswordInput, SimpleGrid, Stack } from '@mantine/core'
import { IconAlertTriangle, IconCheck } from '@tabler/icons-react'
import { ApiError, send, useT } from '../api'

/** Choose the site password (first time) or change it (asks for the current one). */
export default function PasswordForm({ passwordSet, onSaved }: { passwordSet: boolean; onSaved?: () => void }) {
  const t = useT()
  const [current, setCurrent] = useState('')
  const [pw, setPw] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string }>()

  const save = async () => {
    if (pw !== again) return setMessage({ ok: false, text: t('passwords_differ') })
    setBusy(true); setMessage(undefined)
    try {
      await send('PUT', '/api/password', { current, new: pw })
      setCurrent(''); setPw(''); setAgain('')
      setMessage({ ok: true, text: t('password_saved') })
      onSaved?.()
      dispatchEvent(new Event('gate-auth'))  // the header now offers Sign out
    } catch (e) {
      setMessage({ ok: false, text: t((e instanceof ApiError && e.body?.detail?.errors?.[0]) || 'server_down') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); save() }}>
      <Stack gap="md">
        <SimpleGrid cols={{ base: 1, sm: passwordSet ? 3 : 2 }}>
          {passwordSet && (
            <PasswordInput label={t('current_password')} value={current} size="md" autoComplete="current-password"
                           onChange={(e) => setCurrent(e.currentTarget.value)} />
          )}
          <PasswordInput label={t('new_password')} value={pw} size="md" autoComplete="new-password"
                         onChange={(e) => setPw(e.currentTarget.value)} />
          <PasswordInput label={t('repeat_password')} value={again} size="md" autoComplete="new-password"
                         onChange={(e) => setAgain(e.currentTarget.value)} />
        </SimpleGrid>
        {message && (
          <Alert color={message.ok ? 'teal' : 'red'} icon={message.ok ? <IconCheck /> : <IconAlertTriangle />}>{message.text}</Alert>
        )}
        <Group>
          <Button type="submit" size="md" loading={busy} disabled={!pw || (passwordSet && !current)}>{t('save_password')}</Button>
        </Group>
      </Stack>
    </form>
  )
}
