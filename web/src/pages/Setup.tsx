import { useEffect, useState } from 'react'
import {
  Alert, AspectRatio, Button, Card, Center, Group, Image, Loader, Paper, SimpleGrid, Stack, Stepper, Text,
} from '@mantine/core'
import { IconAlertTriangle, IconCameraOff, IconCheck, IconCircleCheck, IconPlus } from '@tabler/icons-react'
import { api, ApiError, type Auth, cameraPicture, send, useT } from '../api'
import AddCamera from '../components/AddCamera'
import PasswordForm from '../components/PasswordForm'
import { RecorderForm, type Role, type Settings } from './Cameras'

/** First-run setup: 1) choose the site password, 2) connect to the recorder, 3) tap the camera
 *  that sees the gate and mark where trucks pass, 4) optionally add the gate's second container
 *  camera and its plate camera (all three then form one lane), 5) done. */
export default function Setup() {
  const t = useT()
  const [settings, setSettings] = useState<Settings>()
  const [failed, setFailed] = useState(false)
  const [step, setStep] = useState(0)
  const [chosen, setChosen] = useState<{ channel: number; picture: string }>()
  const [first, setFirst] = useState('')  // the gate camera chosen in step 3

  useEffect(() => {
    Promise.all([api<Auth>('/api/auth'), api<Settings>('/api/settings')])
      .then(([a, s]) => { setSettings(s); setStep(!a.password_set ? 0 : !s.nvr.ip ? 1 : 2) })
      .catch(() => setFailed(true))
  }, [])

  if (failed) return <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>
  if (!settings) return null
  return (
    <Stack gap="xl">
      <Stepper active={step} onStepClick={(s) => s < step && setStep(s)} size="sm">
        <Stepper.Step label={t('step_password')} description={t('step_password_help')}>
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="md">
              <Text>{t('site_password_help')}</Text>
              <PasswordForm passwordSet={false} onSaved={() => setStep(1)} />
            </Stack>
          </Paper>
        </Stepper.Step>
        <Stepper.Step label={t('step_recorder')} description={t('step_recorder_help')}>
          <RecorderForm settings={settings} onSaved={(s) => { setSettings(s); if (s.nvr.ip) setStep(2) }} />
        </Stepper.Step>
        <Stepper.Step label={t('step_camera')} description={t('step_camera_help')}>
          <Stack gap="md">
            <Alert color="teal" icon={<IconCheck />}>{t('connected')}</Alert>
            {chosen ? (
              <AddCamera settings={settings} initial={chosen} onCancel={() => setChosen(undefined)}
                         onSaved={(s, name) => { setSettings(s); setFirst(name); setChosen(undefined); setStep(3) }} />
            ) : (
              <ChannelPicker onPick={setChosen} />
            )}
          </Stack>
        </Stepper.Step>
        <Stepper.Step label={t('step_more')} description={t('step_more_help')}>
          {first && <MoreCameras settings={settings} first={first} onChanged={setSettings} onDone={() => setStep(4)} />}
        </Stepper.Step>
        <Stepper.Step label={t('step_done')} description={t('step_done_help')}>
          <Paper withBorder radius="lg" p="xl">
            <Stack align="center" gap="md">
              <IconCircleCheck size={56} stroke={1.4} color="var(--mantine-color-teal-6)" />
              <Text fw={700} size="lg" ta="center">{t('setup_done')}</Text>
              <Text c="dimmed" ta="center" maw={520}>{t('setup_done_help')}</Text>
              <Group>
                <Button component="a" href="#live" size="md">{t('open_live')}</Button>
                <Button variant="default" size="md" onClick={() => { setChosen(undefined); setFirst(''); setStep(2) }}>{t('add_another')}</Button>
              </Group>
            </Stack>
          </Paper>
        </Stepper.Step>
      </Stepper>
      {step > 0 && step < 3 && (  // from step 4 on there is a camera, and Finish
        <Group>
          <Button variant="subtle" color="gray" onClick={() => { skipSetup(); location.hash = '#live' }}>{t('skip_setup')}</Button>
        </Group>
      )}
    </Stack>
  )
}

/** Offers the second container camera and the plate camera for the gate camera `first`. The
 *  first one added puts `first` in a lane named after it; with a plate camera, `first` reads
 *  only containers. Both can be skipped: `first` then works alone and reads both, as before. */
function MoreCameras({ settings, first, onChanged, onDone }: {
  settings: Settings; first: string; onChanged: (s: Settings) => void; onDone: () => void
}) {
  const t = useT()
  const [adding, setAdding] = useState<Role>()  // the camera being added: 'container' or 'plate'
  const [chosen, setChosen] = useState<{ channel: number; picture: string }>()
  const [problem, setProblem] = useState<string>()
  const cam = settings.cameras.find((c) => c.name === first)
  const lane = cam?.lane ?? first
  const others = cam?.lane ? settings.cameras.filter((c) => c.lane === lane && c.name !== first) : []

  const start = async (role: Role) => {
    setProblem(undefined)
    try {
      if (!cam?.lane) {
        await send('POST', '/api/lanes', { name: lane, direction: cam?.direction ?? 'IN', location: cam?.location ?? '' })
        onChanged(await send<Settings>('PATCH', `/api/cameras/${encodeURIComponent(first)}`, { lane, role: 'both' }))
      }
      setAdding(role)
    } catch { setProblem(t('server_down')) }
  }
  const saved = async (s: Settings) => {
    const role = adding!
    setAdding(undefined); setChosen(undefined); onChanged(s)
    if (role === 'plate') {  // the plate camera reads the plate, so the gate camera reads only the container
      try { onChanged(await send<Settings>('PATCH', `/api/cameras/${encodeURIComponent(first)}`, { role: 'container' })) }
      catch { setProblem(t('server_down')) }
    }
  }

  if (adding) {
    return chosen
      ? <AddCamera settings={settings} initial={{ ...chosen, lane, role: adding }} onSaved={saved}
                   onCancel={() => setChosen(undefined)} />
      : (
        <Stack gap="md">
          <ChannelPicker onPick={setChosen} title={t(adding === 'plate' ? 'pick_plate_channel' : 'pick_second_channel')} />
          <Group><Button variant="default" onClick={() => setAdding(undefined)}>{t('cancel')}</Button></Group>
        </Stack>
      )
  }
  const offers = ([['container', 'add_second_container'], ['plate', 'add_plate_camera']] as const)
    .filter(([role]) => !others.some((c) => c.role === role))
  return (
    <Paper withBorder radius="lg" p="lg">
      <Stack gap="md">
        <Alert color="teal" icon={<IconCheck />}>{t('camera_saved', { name: first })}</Alert>
        {others.length > 0 && <Text>{t('lane_has_cameras', { n: others.length + 1 })}</Text>}
        {offers.map(([role, key]) => (
          <Group key={role} justify="space-between" wrap="nowrap">
            <div>
              <Text fw={600}>{t(key)}</Text>
              <Text size="sm" c="dimmed">{t(`${key}_help`)}</Text>
            </div>
            <Button variant="light" leftSection={<IconPlus size={18} />} onClick={() => start(role)}>{t('add')}</Button>
          </Group>
        ))}
        {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
        <Group><Button size="md" onClick={onDone}>{t(offers.length ? 'no_more_cameras' : 'finish')}</Button></Group>
      </Stack>
    </Paper>
  )
}

export function setupSkipped() {
  try { return localStorage.getItem('setupSkipped') === '1' } catch { return false }
}
function skipSetup() {
  try { localStorage.setItem('setupSkipped', '1') } catch { /* private window: asked again next time */ }
}

/** Pictures of recorder channels 1-4 (more on request); tap the one that shows the gate. */
function ChannelPicker({ onPick, title }: { onPick: (c: { channel: number; picture: string }) => void; title?: string }) {
  const t = useT()
  const [count, setCount] = useState(4)
  const [pics, setPics] = useState<Record<number, string | null>>({})  // null: no picture on that channel
  const [problem, setProblem] = useState<string>()

  useEffect(() => {
    let alive = true
    ;(async () => {
      for (let ch = count - 3; ch <= count && alive; ch++) {  // one at a time: the recorder is slow to answer
        let url: string | null = null
        try {
          url = await cameraPicture(ch)
        } catch (e) {
          const key = e instanceof ApiError ? e.body?.detail?.errors?.[0] : undefined
          if (key !== 'no_video') { if (alive) setProblem(t(key ?? 'server_down')); return }
        }
        if (alive) setPics((p) => ({ ...p, [ch]: url }))
      }
    })()
    return () => { alive = false }
  }, [count])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Stack gap="md">
      <Text fw={600} size="lg">{title ?? t('pick_channel')}</Text>
      {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
      <SimpleGrid cols={{ base: 1, xs: 2 }}>
        {Array.from({ length: count }, (_, i) => i + 1).map((ch) => {
          const pic = pics[ch]
          return (
            <Card key={ch} withBorder radius="lg" padding={0}
                  onClick={pic ? () => onPick({ channel: ch, picture: pic }) : undefined}
                  style={{ cursor: pic ? 'pointer' : 'default', opacity: pic === null ? 0.6 : 1 }}>
              <AspectRatio ratio={16 / 9} bg="var(--mantine-color-default-hover)">
                {pic ? <Image src={pic} alt="" fit="cover" />
                  : <Center>{pic === null ? <IconCameraOff size={36} color="var(--mantine-color-dimmed)" /> : <Loader size="sm" />}</Center>}
              </AspectRatio>
              <Text p="sm" fw={600}>{t('channel_n', { n: ch })}</Text>
            </Card>
          )
        })}
      </SimpleGrid>
      <Group>
        <Button variant="light" onClick={() => setCount((c) => c + 4)} disabled={count >= 64 || Object.keys(pics).length < count}>
          {t('more_channels')}
        </Button>
      </Group>
    </Stack>
  )
}
