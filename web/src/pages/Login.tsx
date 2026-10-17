import { useState } from 'react'
import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, ThemeIcon, Title } from '@mantine/core'
import { IconAlertTriangle, IconLock, IconTruck } from '@tabler/icons-react'
import { ApiError, send, useT } from '../api'

/** Shown instead of the app until this device signs in with the site password. */
export default function Login({ onDone, languageSwitch }: { onDone: () => void; languageSwitch: React.ReactNode }) {
  const t = useT()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string>()

  const signIn = async () => {
    setBusy(true); setProblem(undefined)
    try {
      await send('POST', '/api/login', { password })
      onDone()
    } catch (e) {
      setProblem(t((e instanceof ApiError && e.body?.detail?.errors?.[0]) || 'server_down'))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder radius="lg" p="xl" w="100%" maw={400}>
        <form onSubmit={(e) => { e.preventDefault(); signIn() }}>
          <Stack gap="md" align="stretch">
            <Center>{languageSwitch}</Center>
            <Center>
              <ThemeIcon size={56} radius="md" variant="gradient" gradient={{ from: 'teal', to: 'cyan' }}>
                <IconTruck size={32} />
              </ThemeIcon>
            </Center>
            <Title order={2} ta="center">{t('app_name')}</Title>
            <Text c="dimmed" ta="center">{t('sign_in_help')}</Text>
            <PasswordInput label={t('site_password')} value={password} size="lg" autoFocus autoComplete="current-password"
                           leftSection={<IconLock size={18} />} onChange={(e) => setPassword(e.currentTarget.value)} />
            {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
            <Button type="submit" size="lg" loading={busy} disabled={!password}>{t('sign_in')}</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
