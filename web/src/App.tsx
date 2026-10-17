import { useEffect, useState } from 'react'
import {
  Alert, AppShell, Burger, Center, Group, Loader, NavLink, Paper, SegmentedControl, Stack, Text,
  ThemeIcon, Title, useDirection,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconCamera, IconClipboardList, IconFlask, IconTruck, IconVideo } from '@tabler/icons-react'
import { api, type Lang, TextContext, type TextTable, useT } from './api'
import Cameras from './pages/Cameras'
import Live from './pages/Live'
import Records from './pages/Records'

const PAGES = [
  { key: 'live', icon: IconVideo },
  { key: 'records', icon: IconClipboardList },
  { key: 'cameras', icon: IconCamera },
  { key: 'test', icon: IconFlask },
] as const
type Page = (typeof PAGES)[number]['key']

const pageFromHash = (): Page => PAGES.find((p) => `#${p.key}` === location.hash)?.key ?? 'live'

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
  const { setDirection } = useDirection()

  useEffect(() => {
    api<{ languages: Record<string, string>; text: TextTable }>('/api/text')
      .then((r) => { setText(r.text); setLanguages(r.languages) })
      .catch(() => setFailed(true))
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
  if (!text) return <Center h="100vh"><Loader /></Center>

  return (
    <TextContext.Provider value={{ lang, text }}>
      <Shell lang={lang} setLang={setLang} languages={languages} />
    </TextContext.Provider>
  )
}

function Shell({ lang, setLang, languages }: { lang: Lang; setLang: (l: Lang) => void; languages: Record<string, string> }) {
  const t = useT()
  const [page, setPage] = useState<Page>(pageFromHash)
  const [opened, { toggle, close }] = useDisclosure()

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => { document.title = `${t(`nav_${page}`)} · ${t('app_name')}` }, [page, t])

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
          <SegmentedControl
            value={lang}
            onChange={(v) => setLang(v as Lang)}
            data={Object.entries(languages).map(([value, label]) => ({ value, label }))}
          />
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
        {page === 'live' ? <Live /> : page === 'records' ? <Records /> : page === 'cameras' ? <Cameras /> : (
          <Paper withBorder p="xl" radius="lg">
            <Text c="dimmed">{t('coming_soon')}</Text>
          </Paper>
        )}
      </AppShell.Main>
    </AppShell>
  )
}
