import { useEffect, useState } from 'react'
import {
  Alert, Button, FileButton, Group, Image, Paper, Progress, SegmentedControl, SimpleGrid, Slider, Stack, Text, TextInput,
} from '@mantine/core'
import { IconAlertTriangle, IconDownload, IconMovie, IconPlayerPlay } from '@tabler/icons-react'
import { api, ApiError, type Truck, useLang, usePoll, useT } from '../api'
import TruckTable from './TruckTable'

type Job = { progress: number; seconds: number; done: boolean; error: string | null; elapsed: number; rows: Truck[] }

/** Play a recorded video through the gate pipeline on the server, as if it were a camera. */
export default function VideoTest({ opts }: { opts: Record<string, number | boolean> }) {
  const t = useT()
  const lang = useLang()
  const [file, setFile] = useState<File | null>(null)
  const [direction, setDirection] = useState('IN')
  const [location, setLocation] = useState('')
  const [fps, setFps] = useState(2)
  const [minHits, setMinHits] = useState(2)
  const [job, setJob] = useState<string>()
  const [final, setFinal] = useState<Job>()  // kept once done, so polling can stop
  const [uploading, setUploading] = useState(false)
  const [problem, setProblem] = useState<string>()
  const poll = usePoll<Job>(job && !final ? `/api/video/${job}` : null, 1000)
  const status = final ?? poll.data

  useEffect(() => { if (poll.data?.done) setFinal(poll.data) }, [poll.data])

  const start = async () => {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    const fields = { fps, min_hits: minHits, direction, location, ...opts }
    for (const [k, v] of Object.entries(fields)) form.append(k, String(v))
    setUploading(true); setProblem(undefined); setJob(undefined); setFinal(undefined)
    try {
      setJob((await api<{ job: string }>('/api/video', { method: 'POST', body: form })).job)
    } catch (e) {
      setProblem(t((e instanceof ApiError && e.body?.detail?.errors?.[0]) || 'server_down'))
    } finally {
      setUploading(false)
    }
  }

  const running = uploading || (!!job && !status?.done)
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">{t('video_help')}</Text>
      <Paper withBorder radius="lg" p="md">
        <Stack gap="md">
          <Group>
            <FileButton onChange={setFile} accept="video/*">
              {(props) => <Button {...props} variant="light" leftSection={<IconMovie size={18} />}>{t('choose_video')}</Button>}
            </FileButton>
            {file && <Text fw={500}><bdi>{file.name}</bdi></Text>}
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
            <div>
              <Text size="sm" fw={500} mb={6}>{t('direction')}</Text>
              <SegmentedControl value={direction} onChange={setDirection}
                                data={[{ value: 'IN', label: t('IN') }, { value: 'OUT', label: t('OUT') }]} />
            </div>
            <TextInput label={t('location')} value={location} onChange={(e) => setLocation(e.currentTarget.value)} placeholder={t('demo_gate')} />
            <div>
              <Text size="sm" fw={500}>{t('fps')}: {fps}</Text>
              <Text size="xs" c="dimmed" mb={8}>{t('fps_help')}</Text>
              <Slider value={fps} onChange={setFps} min={0.5} max={5} step={0.5} label={null} />
            </div>
            <div>
              <Text size="sm" fw={500}>{t('min_hits')}: {minHits}</Text>
              <Text size="xs" c="dimmed" mb={8}>{t('min_hits_help')}</Text>
              <Slider value={minHits} onChange={setMinHits} min={1} max={5} step={1} label={null} />
            </div>
          </SimpleGrid>
          <Group>
            <Button size="md" leftSection={<IconPlayerPlay size={18} />} onClick={start} disabled={!file || running} loading={uploading}>
              {t('start_video')}
            </Button>
            {uploading && <Text size="sm" c="dimmed">{t('uploading')}</Text>}
          </Group>
        </Stack>
      </Paper>

      {problem && <Alert color="red" icon={<IconAlertTriangle />}>{problem}</Alert>}
      {job && status && (
        <Paper withBorder radius="lg" p="md">
          <Stack gap="md">
            <Progress value={status.progress * 100} size="lg" radius="xl" animated={!status.done} />
            <Text size="sm" c="dimmed">
              {status.done && !status.error
                ? t('video_done', { s: status.elapsed, n: status.rows.length })
                : t('video_progress', { s: status.seconds })}
            </Text>
            {status.error && <Alert color="red" icon={<IconAlertTriangle />}>{t(status.error)}</Alert>}
            {!status.done && poll.at > 0 && (
              <Image src={`/api/video/${job}/frame.jpg?t=${poll.at}`} radius="md" mah={420} fit="contain" alt="" />
            )}
            {status.done && !status.error && status.rows.length === 0 && <Text>{t('video_none')}</Text>}
            {status.rows.length > 0 && (
              <>
                <Paper withBorder radius="md"><TruckTable rows={status.rows} /></Paper>
                <SimpleGrid cols={{ base: 2, sm: 4 }}>
                  {status.rows.filter((r) => r.snapshot).map((r) => (
                    <Stack key={r.id} gap={4}>
                      <Image src={`/api/video/${job}/records/${r.id}/snapshot`} radius="md" alt="" />
                      <Text size="xs" ta="center" ff="monospace"><bdi>{[r.plate, r.container].filter(Boolean).join(' · ')}</bdi></Text>
                    </Stack>
                  ))}
                </SimpleGrid>
                {status.done && (
                  <Group>
                    <Button component="a" href={`/api/video/${job}/excel?lang=${lang}`} leftSection={<IconDownload size={18} />}>
                      {t('dl_excel')}
                    </Button>
                  </Group>
                )}
              </>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
