import { useEffect, useState } from 'react'
import {
  Alert, Button, Group, NumberInput, Paper, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconPhoto, IconScan } from '@tabler/icons-react'
import { ApiError, send, useT } from '../api'
import type { Settings } from '../pages/Cameras'
import AreaPicker from './AreaPicker'
import OcrResultView, { type OcrResult } from './OcrResult'

/** Form for a new camera: name, recorder channel, in/out, location, and a reading area drawn
 *  on the camera's current picture, with a test read of that area. */
export default function AddCamera({ settings, onSaved, onCancel }: {
  settings: Settings; onSaved: (s: Settings, name: string) => void; onCancel: () => void
}) {
  const t = useT()
  const [name, setName] = useState('')
  const [channel, setChannel] = useState<number | string>(1)
  const [direction, setDirection] = useState<'IN' | 'OUT'>('IN')
  const [location, setLocation] = useState('')
  const [roi, setRoi] = useState<number[] | null>(null)
  const [picture, setPicture] = useState<string>()
  const [result, setResult] = useState<OcrResult>()
  const [busy, setBusy] = useState<'picture' | 'test' | 'save'>()
  const [problem, setProblem] = useState<string>()
  const hasRecorder = !!settings.nvr.ip

  useEffect(() => { setPicture(undefined); setResult(undefined) }, [channel])  // another camera's picture
  useEffect(() => () => { if (picture) URL.revokeObjectURL(picture) }, [picture])

  const explain = (e: unknown) => {
    const key = e instanceof ApiError ? e.body?.detail?.errors?.[0] : undefined
    setProblem(key ? t(key, { ip: settings.nvr.ip }) : t('server_down'))
  }
  const run = async (what: 'picture' | 'test' | 'save', job: () => Promise<void>) => {
    setBusy(what); setProblem(undefined)
    try { await job() } catch (e) { explain(e) } finally { setBusy(undefined) }
  }

  const getPicture = () => run('picture', async () => {
    const res = await fetch('/api/cameras/frame', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: Number(channel) }),
    })
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
    setPicture(URL.createObjectURL(await res.blob()))
  })
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
            <NumberInput label={t('nvr_channel')} description={t('channel_help')} value={channel} onChange={setChannel}
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
            <Text fw={600}>{t('reading_area')}</Text>
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
