import { useEffect, useState } from 'react'
import {
  ActionIcon, Alert, AppShell, Burger, Center, Group, Loader, NavLink, Paper, SegmentedControl, Stack, Text,
  ThemeIcon, Title, Tooltip, useDirection,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconCamera, IconClipboardList, IconFlask, IconLock, IconLogout, IconTruck, IconVideo } from '@tabler/icons-react'
import { api, type Auth, type Lang, send, TextContext, type TextTable, useT } from './api'
import type { Settings } from './pages/Cameras'
import Cameras from './pages/Cameras'
import Live from './pages/Live'
import Login from './pages/Login'
import Records from './pages/Records'
import Setup, { setupSkipped } from './pages/Setup'
import Test from './pages/Test'

const PAGES = [
  { key: 'live', icon: IconVideo },
  { key: 'records', icon: IconClipboardList },
  { key: 'cameras', icon: IconCamera },
  { key: 'test', icon: IconFlask },
] as const
type Page = (typeof PAGES)[number]['key'] | 'setup'  // setup: not in the menu, opened on first run

const pageFromHash = (): Page =>
  location.hash === '#setup' ? 'setup' : PAGES.find((p) => `#${p.key}` === location.hash)?.key ?? 'live'

function savedLang(): Lang {
  try {
    return localStorage.getItem('lang') === 'ar' ? 'ar' : 'en'
  } catch {
    return 'en'
  }
}

export default function App() {
  const [lang, setLang] = useState<Lang>(savedLang)
  const [text, setText] = useState<TextTable | null>(null)
  const [languages, setLanguages] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState(false)
  const [auth, setAuth] = useState<Auth>()
  const { setDirection } = useDirection()

  const loadAuth = () => api<Auth>('/api/auth').then(setAuth).catch(() => setFailed(true))
  useEffect(() => {
    api<{ languages: Record<string, string>; text: TextTable }>('/api/text')
      .then((r) => { setText(r.text); setLanguages(r.languages) })
      .catch(() => setFailed(true))
    loadAuth()
    addEventListener('gate-auth', loadAuth)  // signed out by the server, or the password was set/changed
    return () => removeEventListener('gate-auth', loadAuth)
  }, [])

  useEffect(() => {
    setDirection(lang === 'ar' ? 'rtl' : 'ltr')
    document.documentElement.lang = lang
    try { localStorage.setItem('lang', lang) } catch { /* private window: not remembered */ }
  }, [lang, setDirection])

  if (failed) {  // no text from the server, so both languages
    return (
      <Center h="100vh" p="md">
        <Alert color="red" title="⚠️" maw={480}>
          <Text>Can't reach the gate computer. Check that it is switched on, then reload this page.</Text>
          <Text dir="rtl" mt="sm">تعذّر الاتصال بجهاز البوابة. تأكد أنه يعمل ثم أعد تحميل الصفحة.</Text>
        </Alert>
      </Center>
    )
  }
  if (!text || !auth) return <Center h="100vh"><Loader /></Center>

  const languageSwitch = (
    <SegmentedControl value={lang} onChange={(v) => setLang(v as Lang)}
                      data={Object.entries(languages).map(([value, label]) => ({ value, label }))} />
  )
  return (
    <TextContext.Provider value={{ lang, text }}>
      {auth.password_set && !auth.logged_in ? <Login onDone={loadAuth} languageSwitch={languageSwitch} />
        : !auth.password_set && !auth.local ? <LocalOnly languageSwitch={languageSwitch} />
        : <Shell languageSwitch={languageSwitch} auth={auth} onSignOut={() => send('POST', '/api/logout', {}).then(loadAuth)} />}
    </TextContext.Provider>
  )
}

/** Another device, before the site has a password: the API only answers the gate computer. */
function LocalOnly({ languageSwitch }: { languageSwitch: React.ReactNode }) {
  const t = useT()
  return (
    <Center mih="100vh" p="md">
      <Paper withBorder radius="lg" p="xl" maw={440}>
        <Stack align="center" gap="md">
          {languageSwitch}
          <IconLock size={44} stroke={1.4} color="var(--mantine-color-dimmed)" />
          <Text ta="center">{t('local_only')}</Text>
        </Stack>
      </Paper>
    </Center>
  )
}

function Shell({ languageSwitch, auth, onSignOut }: { languageSwitch: React.ReactNode; auth: Auth; onSignOut: () => void }) {
  const t = useT()
  const [page, setPage] = useState<Page>(pageFromHash)
  const [opened, { toggle, close }] = useDisclosure()

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => { document.title = `${t(`nav_${page}`)} · ${t('app_name')}` }, [page, t])

  useEffect(() => {  // a fresh install (no recorder, no camera) opens the setup wizard
    if (location.hash || setupSkipped()) return
    api<Settings>('/api/settings')
      .then((s) => { if (!s.nvr.ip && s.cameras.length === 0) location.hash = '#setup' })
      .catch(() => {})
  }, [])

  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{ width: 270, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label={t('menu')} />
            <ThemeIcon size={40} radius="md" variant="gradient" gradient={{ from: 'teal', to: 'cyan' }}>
              <IconTruck size={24} />
            </ThemeIcon>
            <Title order={3} visibleFrom="xs">{t('app_name')}</Title>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {languageSwitch}
            {auth.password_set && (
              <Tooltip label={t('sign_out')}>
                <ActionIcon variant="subtle" color="gray" size="lg" onClick={onSignOut} aria-label={t('sign_out')}>
                  <IconLogout size={20} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        <Stack gap={4}>
          {PAGES.map(({ key, icon: Icon }) => (
            <NavLink
              key={key}
              href={`#${key}`}
              active={page === key}
              onClick={close}
              label={<Text fw={600} size="md">{t(`nav_${key}`)}</Text>}
              description={t(`nav_${key}_help`)}
              leftSection={<Icon size={26} stroke={1.6} />}
              py="sm"
              style={{ borderRadius: 'var(--mantine-radius-md)' }}
            />
          ))}
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main>
        <Stack gap="xs" mb="lg">
          <Title order={2}>{t(`nav_${page}`)}</Title>
          <Text c="dimmed">{t(`nav_${page}_help`)}</Text>
        </Stack>
        {page === 'live' ? <Live /> : page === 'records' ? <Records /> : page === 'cameras' ? <Cameras /> : page === 'test' ? <Test /> : page === 'setup' ? <Setup /> : (
          <Paper withBorder p="xl" radius="lg">
            <Text c="dimmed">{t('coming_soon')}</Text>
          </Paper>
        )}
      </AppShell.Main>
    </AppShell>
  )
}
