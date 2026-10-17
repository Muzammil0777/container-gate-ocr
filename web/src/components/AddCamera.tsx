import { useState } from 'react'
import {
  Alert, Button, Group, NumberInput, Paper, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconPhoto, IconScan } from '@tabler/icons-react'
import { ApiError, cameraPicture, send, useT } from '../api'
import type { Settings } from '../pages/Cameras'
import AreaPicker from './AreaPicker'
import HelpTip from './HelpTip'
import OcrResultView, { type OcrResult } from './OcrResult'

/** Form for a new camera: name, recorder channel, in/out, location, and a reading area drawn
 *  on the camera's current picture, with a test read of that area. */
export default function AddCamera({ settings, onSaved, onCancel, initial }: {
  settings: Settings; onSaved: (s: Settings, name: string) => void; onCancel: () => void
  initial?: { channel: number; picture: string }  // already chosen (setup wizard)
}) {
  const t = useT()
  const [name, setName] = useState('')
  const [channel, setChannel] = useState<number | string>(initial?.channel ?? 1)
  const [direction, setDirection] = useState<'IN' | 'OUT'>('IN')
  const [location, setLocation] = useState('')
  const [roi, setRoi] = useState<number[] | null>(null)
  const [picture, setPicture] = useState(initial?.picture)
  const [result, setResult] = useState<OcrResult>()
  const [busy, setBusy] = useState<'picture' | 'test' | 'save'>()
  const [problem, setProblem] = useState<string>()
  const hasRecorder = !!settings.nvr.ip


  const explain = (e: unknown) => {
    const key = e instanceof ApiError ? e.body?.detail?.errors?.[0] : undefined
    setProblem(key ? t(key, { ip: settings.nvr.ip }) : t('server_down'))
  }
  const run = async (what: 'picture' | 'test' | 'save', job: () => Promise<void>) => {
    setBusy(what); setProblem(undefined)
    try { await job() } catch (e) { explain(e) } finally { setBusy(undefined) }
  }

  const getPicture = () => run('picture', async () => setPicture(await cameraPicture(Number(channel))))
  const test = () => run('test', async () => {
    setResult(await send<OcrResult>('POST', '/api/cameras/test', { channel: Number(channel), roi }))
  })
  const save = () => run('save', async () => {
    const body = { name, channel: Number(channel), direction, location, roi }
    onSaved(await send<Settings>('POST', '/api/cameras', body), name.trim())
  })

  return (
    <Paper withBorder radius="lg" p="lg">
      <form onSubmit={(e) => { e.preventDefault(); save() }}>
        <Stack gap="md">
          <Title order={4}>{t('new_camera')}</Title>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label={t('camera_name')} placeholder="Gate 1 Entry" value={name} size="md" required
                       onChange={(e) => setName(e.currentTarget.value)} />
            <NumberInput label={t('nvr_channel')} description={t('channel_help')} value={channel}
                         onChange={(v) => { setChannel(v); setPicture(undefined); setResult(undefined) }}
                         min={1} max={64} size="md" allowDecimal={false} />
            <div>
              <Text size="sm" fw={500}>{t('direction')}</Text>
              <Text size="xs" c="dimmed" mb={6}>{t('direction_help')}</Text>
              <SegmentedControl value={direction} onChange={(v) => setDirection(v as 'IN' | 'OUT')}
                                data={[{ value: 'IN', label: t('IN') }, { value: 'OUT', label: t('OUT') }]} />
            </div>
            <TextInput label={t('location')} placeholder="Main gate, Lane 1" value={location} size="md"
                       onChange={(e) => setLocation(e.currentTarget.value)} />
          </SimpleGrid>

          <Stack gap="xs">
            <Group gap={6}><Text fw={600}>{t('reading_area')}</Text><HelpTip text={t('help_area')} /></Group>
            <Text size="sm" c="dimmed">{t('area_help')}</Text>
            {!hasRecorder && <Alert color="blue">{t('no_nvr')}</Alert>}
            <Group>
              <Button variant="light" leftSection={<IconPhoto size={18} />} onClick={getPicture}
                      loading={busy === 'picture'} disabled={!hasRecorder}>
                {t('get_picture')}
              </Button>
              {roi && <Button variant="subtle" onClick={() => setRoi(null)}>{t('whole_picture')}</Button>}
              <Button variant="light" leftSection={<IconScan size={18} />} onClick={test}
                      loading={busy === 'test'} disabled={!hasRecorder}>
                {t('test_reading')}
              </Button>
            </Group>
            {picture && <AreaPicker src={picture} roi={roi} onChange={setRoi} />}
            <Text size="sm" c={roi ? 'teal' : 'dimmed'}>{t(roi ? 'area_drawn' : 'area_whole')}</Text>
          </Stack>

          {result && <OcrResultView result={result} />}
          {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
          <Group>
            <Button type="submit" size="md" loading={busy === 'save'} disabled={!name.trim()}>{t('save_camera_web')}</Button>
            <Button variant="default" size="md" onClick={onCancel}>{t('cancel')}</Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}
