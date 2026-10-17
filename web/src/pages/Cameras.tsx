import { useEffect, useState } from 'react'
import {
  ActionIcon, Alert, Badge, Button, Card, Group, Modal, NumberInput, Paper, PasswordInput, SegmentedControl,
  SimpleGrid, Stack, Switch, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { IconAlertTriangle, IconCheck, IconPlus, IconTrash } from '@tabler/icons-react'
import { api, ApiError, send, useT } from '../api'
import AddCamera from '../components/AddCamera'
import { Direction } from '../components/TruckTable'

export type Camera = {
  name: string; channel?: number; source?: string; direction?: string; location?: string
  enabled?: boolean; roi?: number[]
}
export type Settings = {
  nvr: { ip: string; user: string; port: number; has_password: boolean }
  language: 'en' | 'ar'
  cameras: Camera[]
}

export default function Cameras() {
  const t = useT()
  const [settings, setSettings] = useState<Settings>()
  const [failed, setFailed] = useState(false)
  const [adding, setAdding] = useState(false)
  const [added, setAdded] = useState<string>()

  useEffect(() => { api<Settings>('/api/settings').then(setSettings).catch(() => setFailed(true)) }, [])

  if (failed) return <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>
  if (!settings) return null
  return (
    <Stack gap="xl">
      <RecorderForm settings={settings} onSaved={setSettings} />
      <CameraList cameras={settings.cameras} onChanged={setSettings} />
      {added && <Alert color="teal" icon={<IconCheck />} withCloseButton onClose={() => setAdded(undefined)}>{t('camera_saved', { name: added })}</Alert>}
      {adding ? (
        <AddCamera settings={settings} onCancel={() => setAdding(false)}
                   onSaved={(s, name) => { setSettings(s); setAdding(false); setAdded(name) }} />
      ) : (
        <Group><Button size="md" leftSection={<IconPlus size={18} />} onClick={() => { setAdded(undefined); setAdding(true) }}>{t('add_camera_btn')}</Button></Group>
      )}
    </Stack>
  )
}

function RecorderForm({ settings, onSaved }: { settings: Settings; onSaved: (s: Settings) => void }) {
  const t = useT()
  const [ip, setIp] = useState(settings.nvr.ip)
  const [user, setUser] = useState(settings.nvr.user)
  const [password, setPassword] = useState('')
  const [port, setPort] = useState<number | string>(settings.nvr.port)
  const [language, setLanguage] = useState(settings.language)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string }>()

  const save = async () => {
    setBusy(true); setMessage(undefined)
    try {
      onSaved(await send<Settings>('PUT', '/api/settings', { ip, user, password, port: Number(port) || 554, language }))
      setPassword('')
      setMessage({ ok: true, text: t('saved') })
    } catch (e) {
      const unreachable = e instanceof ApiError && e.body?.detail?.errors?.includes('unreachable')
      setMessage({ ok: false, text: unreachable ? t('unreachable', { ip }) : t('server_down') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper withBorder radius="lg" p="lg">
      <form onSubmit={(e) => { e.preventDefault(); save() }}>
        <Stack gap="md">
          <div>
            <Title order={3}>{t('nvr_settings')}</Title>
            <Text size="sm" c="dimmed">{t('recorder_help')}</Text>
          </div>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label={t('nvr_ip')} placeholder="192.168.1.64" value={ip} size="md"
                       onChange={(e) => setIp(e.currentTarget.value)} />
            <TextInput label={t('nvr_user')} value={user} size="md" autoComplete="off"
                       onChange={(e) => setUser(e.currentTarget.value)} />
            <PasswordInput label={t('nvr_password')} value={password} size="md" autoComplete="new-password"
                           placeholder={settings.nvr.has_password ? '••••••••' : ''}
                           description={settings.nvr.has_password ? t('password_keep') : undefined}
                           onChange={(e) => setPassword(e.currentTarget.value)} />
            <NumberInput label={t('port')} value={port} onChange={setPort} min={1} max={65535} size="md" allowDecimal={false} />
          </SimpleGrid>
          <div>
            <Text size="sm" fw={500}>{t('excel_language')}</Text>
            <Text size="xs" c="dimmed" mb={6}>{t('excel_lang_help')}</Text>
            <SegmentedControl value={language} onChange={(v) => setLanguage(v as 'en' | 'ar')}
                              data={[{ value: 'en', label: 'English' }, { value: 'ar', label: 'العربية' }]} />
          </div>
          {message && (
            <Alert color={message.ok ? 'teal' : 'red'} icon={message.ok ? <IconCheck /> : <IconAlertTriangle />}>{message.text}</Alert>
          )}
          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed" maw={480}>{t('password_note')}</Text>
            <Button type="submit" size="md" loading={busy}>{t('save_settings')}</Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}

function CameraList({ cameras, onChanged }: { cameras: Camera[]; onChanged: (s: Settings) => void }) {
  const t = useT()
  const [deleting, setDeleting] = useState<string>()
  const [confirmOpen, setConfirmOpen] = useState(false)  // separate, so the name stays while the dialog closes
  const [failed, setFailed] = useState(false)

  const change = (p: Promise<Settings>) => {
    setFailed(false)
    p.then(onChanged).catch(() => setFailed(true))
  }
  const path = (name: string) => `/api/cameras/${encodeURIComponent(name)}`

  return (
    <Stack gap="md">
      <Title order={3}>{t('cameras')}</Title>
      {failed && <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>}
      {cameras.length === 0 && <Text c="dimmed">{t('no_cameras_list')}</Text>}
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {cameras.map((c) => {
          const on = c.enabled ?? true
          return (
            <Card key={c.name} withBorder radius="lg" padding="md" style={{ opacity: on ? 1 : 0.65 }}>
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Stack gap={6}>
                  <Group gap="xs">
                    <Text fw={700} size="lg">{c.name}</Text>
                    <Direction value={c.direction ?? 'IN'} />
                  </Group>
                  <Group gap="xs">
                    <Badge variant="default">{c.channel ? t('channel_n', { n: c.channel }) : t('own_source')}</Badge>
                    {c.roi && <Badge variant="light" color="grape">{t('reading_area_set')}</Badge>}
                  </Group>
                  {c.location && <Text size="sm" c="dimmed">{c.location}</Text>}
                </Stack>
                <Group gap="sm" wrap="nowrap">
                  <Switch size="lg" checked={on} onLabel={t('camera_on')} offLabel={t('camera_off')}
                          aria-label={c.name}
                          onChange={(e) => change(send<Settings>('PATCH', path(c.name), { enabled: e.currentTarget.checked }))} />
                  <Tooltip label={t('delete')}>
                    <ActionIcon variant="subtle" color="red" size="lg" aria-label={t('delete')} onClick={() => { setDeleting(c.name); setConfirmOpen(true) }}>
                      <IconTrash size={20} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              </Group>
            </Card>
          )
        })}
      </SimpleGrid>

      <Modal opened={confirmOpen} onClose={() => setConfirmOpen(false)} title={t('delete')} centered>
        <Stack>
          <Text>{t('delete_confirm', { name: deleting ?? '' })}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmOpen(false)}>{t('cancel')}</Button>
            <Button color="red" onClick={() => { change(api<Settings>(path(deleting!), { method: 'DELETE' })); setConfirmOpen(false) }}>
              {t('delete_yes')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
