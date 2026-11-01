import { useState } from 'react'
import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { IconAlertTriangle, IconLock, IconTruck, IconUser } from '@tabler/icons-react'
import { ApiError, send, useT } from '../api'

/** Shown instead of the app until this device signs in with a username and password. */
export default function Login({ onDone, languageSwitch }: { onDone: () => void; languageSwitch: React.ReactNode }) {
  const t = useT()
  const [username, setUsername] = useState(() => localStorage.getItem('gate-username') ?? '')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string>()

  const signIn = async () => {
    setBusy(true); setProblem(undefined)
    try {
      await send('POST', '/api/login', { username, password })
      localStorage.setItem('gate-username', username.trim())  // the next sign-in on this device
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
            <TextInput label={t('username')} value={username} size="lg" autoFocus={!username} autoComplete="username"
                       dir="ltr" leftSection={<IconUser size={18} />} onChange={(e) => setUsername(e.currentTarget.value)} />
            <PasswordInput label={t('password')} value={password} size="lg" autoFocus={!!username} autoComplete="current-password"
                           leftSection={<IconLock size={18} />} onChange={(e) => setPassword(e.currentTarget.value)} />
            {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
            <Button type="submit" size="lg" loading={busy} disabled={!username.trim() || !password}>{t('sign_in')}</Button>
            <Text size="sm" c="dimmed" ta="center">{t('sign_in_admin_hint')}</Text>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
