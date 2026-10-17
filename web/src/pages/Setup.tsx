import { useEffect, useState } from 'react'
import {
  Alert, AspectRatio, Button, Card, Center, Group, Image, Loader, Paper, SimpleGrid, Stack, Stepper, Text,
} from '@mantine/core'
import { IconAlertTriangle, IconCameraOff, IconCheck, IconCircleCheck } from '@tabler/icons-react'
import { api, ApiError, cameraPicture, useT } from '../api'
import AddCamera from '../components/AddCamera'
import { RecorderForm, type Settings } from './Cameras'

/** First-run setup: 1) connect to the recorder, 2) tap the camera that sees the gate and mark
 *  where trucks pass, 3) done. */
export default function Setup() {
  const t = useT()
  const [settings, setSettings] = useState<Settings>()
  const [failed, setFailed] = useState(false)
  const [step, setStep] = useState(0)
  const [chosen, setChosen] = useState<{ channel: number; picture: string }>()

  useEffect(() => {
    api<Settings>('/api/settings')
      .then((s) => { setSettings(s); if (s.nvr.ip) setStep(1) })
      .catch(() => setFailed(true))
  }, [])

  if (failed) return <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>
  if (!settings) return null
  return (
    <Stack gap="xl">
      <Stepper active={step} onStepClick={(s) => s < step && setStep(s)} size="sm">
        <Stepper.Step label={t('step_recorder')} description={t('step_recorder_help')}>
          <RecorderForm settings={settings} onSaved={(s) => { setSettings(s); if (s.nvr.ip) setStep(1) }} />
        </Stepper.Step>
        <Stepper.Step label={t('step_camera')} description={t('step_camera_help')}>
          <Stack gap="md">
            <Alert color="teal" icon={<IconCheck />}>{t('connected')}</Alert>
            {chosen ? (
              <AddCamera settings={settings} initial={chosen} onCancel={() => setChosen(undefined)}
                         onSaved={(s) => { setSettings(s); setStep(2) }} />
            ) : (
              <ChannelPicker onPick={setChosen} />
            )}
          </Stack>
        </Stepper.Step>
        <Stepper.Step label={t('step_done')} description={t('step_done_help')}>
          <Paper withBorder radius="lg" p="xl">
            <Stack align="center" gap="md">
              <IconCircleCheck size={56} stroke={1.4} color="var(--mantine-color-teal-6)" />
              <Text fw={700} size="lg" ta="center">{t('setup_done')}</Text>
              <Text c="dimmed" ta="center" maw={520}>{t('setup_done_help')}</Text>
              <Group>
                <Button component="a" href="#live" size="md">{t('open_live')}</Button>
                <Button variant="default" size="md" onClick={() => { setChosen(undefined); setStep(1) }}>{t('add_another')}</Button>
              </Group>
            </Stack>
          </Paper>
        </Stepper.Step>
      </Stepper>
      {step < 2 && (
        <Group>
          <Button variant="subtle" color="gray" onClick={() => { skipSetup(); location.hash = '#live' }}>{t('skip_setup')}</Button>
        </Group>
      )}
    </Stack>
  )
}

export function setupSkipped() {
  try { return localStorage.getItem('setupSkipped') === '1' } catch { return false }
}
function skipSetup() {
  try { localStorage.setItem('setupSkipped', '1') } catch { /* private window: asked again next time */ }
}

/** Pictures of recorder channels 1-4 (more on request); tap the one that shows the gate. */
function ChannelPicker({ onPick }: { onPick: (c: { channel: number; picture: string }) => void }) {
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
      <Text fw={600} size="lg">{t('pick_channel')}</Text>
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
