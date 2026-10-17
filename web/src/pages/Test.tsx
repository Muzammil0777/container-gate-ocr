import { useEffect, useState } from 'react'
import {
  Accordion, Alert, Button, FileButton, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Stack, Switch,
  Text, TextInput, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconPhotoUp, IconScan } from '@tabler/icons-react'
import { api, ApiError, send, useT } from '../api'
import OcrResultView, { type OcrResult } from '../components/OcrResult'

type Options = { max_side: number; zoom: boolean; vertical: boolean; plates: boolean }
type Item = { name: string; result?: OcrResult; problem?: string }

export default function Test() {
  const t = useT()
  const [mode, setMode] = useState<'photo' | 'stream'>('photo')
  const [opts, setOpts] = useState<Options>({ max_side: 1920, zoom: true, vertical: true, plates: true })
  const [items, setItems] = useState<Item[]>([])

  const problem = (e: unknown) => {
    const key = e instanceof ApiError ? e.body?.detail?.errors?.[0] : undefined
    return t(key ?? 'server_down')
  }
  /** Read pictures one by one (the server reads one at a time anyway), showing each as it's done. */
  const readAll = async (jobs: { name: string; run: () => Promise<OcrResult> }[]) => {
    setItems(jobs.map((j) => ({ name: j.name })))
    for (const [i, job] of jobs.entries()) {
      let done: Item
      try { done = { name: job.name, result: await job.run() } } catch (e) { done = { name: job.name, problem: problem(e) } }
      setItems((list) => list.map((x, k) => (k === i ? done : x)))
    }
  }

  return (
    <Stack gap="lg">
      <Text c="dimmed">{t('test_intro')}</Text>
      <SegmentedControl value={mode} onChange={(v) => { setMode(v as 'photo' | 'stream'); setItems([]) }} w="fit-content"
                        data={[{ value: 'photo', label: t('test_image') }, { value: 'stream', label: t('test_stream') }]} />
      {mode === 'photo' ? <PhotoInput opts={opts} readAll={readAll} /> : <StreamInput opts={opts} readAll={readAll} />}
      <Advanced opts={opts} setOpts={setOpts} />

      {items.map((it, i) => (
        <Paper key={i} withBorder radius="lg" p="md">
          <Stack gap="sm">
            <Title order={5}><bdi>{it.name}</bdi></Title>
            {it.result ? <OcrResultView result={it.result} />
              : it.problem ? <Alert color="red" icon={<IconAlertTriangle />}>{it.problem}</Alert>
              : <Loader size="sm" />}
          </Stack>
        </Paper>
      ))}
      {items.some((it) => it.result) && <Text size="sm" c="dimmed">{t('box_colors')}</Text>}
    </Stack>
  )
}

type Reader = (jobs: { name: string; run: () => Promise<OcrResult> }[]) => Promise<void>

function PhotoInput({ opts, readAll }: { opts: Options; readAll: Reader }) {
  const t = useT()
  const [samples, setSamples] = useState<string[]>([])
  const [sample, setSample] = useState<string | null>(null)
  const [over, setOver] = useState(false)

  useEffect(() => {
    api<string[]>('/api/samples').then((s) => { setSamples(s); setSample(s.find((n) => n.startsWith('ksa_')) ?? s[0] ?? null) }).catch(() => {})
  }, [])

  const readFiles = (files: File[]) => readAll(files.map((f) => ({
    name: f.name,
    run: () => {
      const form = new FormData()
      form.append('file', f)
      for (const [k, v] of Object.entries(opts)) form.append(k, String(v))
      return api<OcrResult>('/api/ocr', { method: 'POST', body: form })
    },
  })))

  return (
    <Stack gap="md">
      <Paper
        withBorder radius="lg" p="xl"
        style={{ borderStyle: 'dashed', borderWidth: 2, background: over ? 'var(--mantine-primary-color-light)' : undefined }}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); readFiles([...e.dataTransfer.files].filter((f) => f.type.startsWith('image/'))) }}
      >
        <Stack align="center" gap="sm">
          <IconPhotoUp size={44} stroke={1.4} color="var(--mantine-color-dimmed)" />
          <Text>{t('drop_photos')}</Text>
          <FileButton onChange={(f) => f.length && readFiles(f)} accept="image/*" multiple>
            {(props) => <Button {...props} size="md">{t('choose_photos')}</Button>}
          </FileButton>
        </Stack>
      </Paper>
      {samples.length > 0 && (
        <Group align="flex-end">
          <Select label={t('sample_photo')} data={samples} value={sample} onChange={setSample} allowDeselect={false} w={280} />
          <Button variant="light" leftSection={<IconScan size={18} />} disabled={!sample}
                  onClick={() => sample && readAll([{ name: sample, run: () => send<OcrResult>('POST', '/api/ocr/sample', { name: sample, ...opts }) }])}>
            {t('read_btn')}
          </Button>
        </Group>
      )}
    </Stack>
  )
}

function StreamInput({ opts, readAll }: { opts: Options; readAll: Reader }) {
  const t = useT()
  const [url, setUrl] = useState('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); readAll([{ name: url, run: () => send<OcrResult>('POST', '/api/stream/frame', { url, ...opts }) }]) }}>
      <Stack gap="xs">
        <Text size="sm" c="dimmed">{t('stream_help')}</Text>
        <Group align="flex-end">
          <TextInput label={t('camera_source')} value={url} onChange={(e) => setUrl(e.currentTarget.value)} size="md"
                     placeholder="rtsp://user:password@192.168.1.64:554/Streaming/Channels/101" style={{ flex: 1, minWidth: 260 }}
                     styles={{ input: { fontFamily: 'monospace' } }} dir="ltr" />
          <Button type="submit" size="md" leftSection={<IconScan size={18} />} disabled={!url.trim()}>{t('read_picture')}</Button>
        </Group>
      </Stack>
    </form>
  )
}

function Advanced({ opts, setOpts }: { opts: Options; setOpts: (o: Options) => void }) {
  const t = useT()
  return (
    <Accordion variant="contained" radius="lg">
      <Accordion.Item value="advanced">
        <Accordion.Control>{t('advanced')}</Accordion.Control>
        <Accordion.Panel>
          <Stack gap="md">
            <div>
              <Text size="sm" fw={500}>{t('max_side')}</Text>
              <Text size="xs" c="dimmed" mb={6}>{t('max_side_help')}</Text>
              <SegmentedControl value={String(opts.max_side)} onChange={(v) => setOpts({ ...opts, max_side: Number(v) })}
                                data={['960', '1280', '1600', '1920', '2560']} />
            </div>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <Switch label={t('zoom')} description={t('zoom_help')} checked={opts.zoom}
                      onChange={(e) => setOpts({ ...opts, zoom: e.currentTarget.checked })} />
              <Switch label={t('vertical')} description={t('vertical_help')} checked={opts.vertical}
                      onChange={(e) => setOpts({ ...opts, vertical: e.currentTarget.checked })} />
              <Switch label={t('read_plates')} checked={opts.plates}
                      onChange={(e) => setOpts({ ...opts, plates: e.currentTarget.checked })} />
            </SimpleGrid>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}
