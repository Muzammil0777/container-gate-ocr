import { useState } from 'react'
import {
  Alert, AspectRatio, Badge, Button, Card, Center, Group, Image, Paper, SimpleGrid, Stack, Text, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconCameraOff, IconDownload, IconPlayerPlay, IconVideoPlus } from '@tabler/icons-react'
import { api, type Truck, useLang, usePoll, useT } from '../api'
import TruckTable, { Direction } from '../components/TruckTable'

type CameraState = {
  name: string; direction: string; location: string
  state: 'ok' | 'connecting' | 'offline' | 'stopped'; age: number | null; has_picture: boolean
}
type Status = { running: boolean; starting: boolean; today: string; cameras: CameraState[] }

export default function Live() {
  const t = useT()
  const lang = useLang()
  const status = usePoll<Status>('/api/status', 2000)
  const s = status.data
  const trucks = usePoll<Truck[]>(`/api/records?day=${s?.today ?? ''}`, 2000)
  const [clickedAt, setClickedAt] = useState(0)  // shows "starting" until the server reports it

  if (status.failed) return <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>
  if (!s) return null

  const rows = s.today && trucks.data ? [...trucks.data].reverse() : []  // newest first
  const start = () => { setClickedAt(Date.now()); api('/api/service/start', { method: 'POST' }).catch(() => setClickedAt(0)) }

  return (
    <Stack gap="xl">
      {s.cameras.length === 0 ? (
        <Paper withBorder p="xl" radius="lg">
          <Stack align="center" gap="md">
            <IconVideoPlus size={48} stroke={1.4} color="var(--mantine-color-dimmed)" />
            <Text ta="center">{t('web_no_cameras')}</Text>
            <Button component="a" href="#cameras" size="md">{t('go_cameras')}</Button>
          </Stack>
        </Paper>
      ) : !s.running && (
        <Alert color="yellow" icon={<IconAlertTriangle />} title={t('service_down')}>
          {s.starting || Date.now() - clickedAt < 5000
            ? <Text>{t('service_starting')}</Text>
            : <Button mt="xs" size="md" leftSection={<IconPlayerPlay size={18} />} onClick={start}>{t('start_detection')}</Button>}
        </Alert>
      )}

      {s.cameras.length > 0 && (
        <SimpleGrid cols={{ base: 1, md: s.cameras.length > 1 ? 2 : 1 }} maw={s.cameras.length > 1 ? undefined : 900}>
          {s.cameras.map((c) => <CameraCard key={c.name} cam={c} at={status.at} />)}
        </SimpleGrid>
      )}

      <Stack gap="md">
        <Group justify="space-between">
          <Title order={3}>{t('stat_total')}</Title>
          <Button
            component="a"
            href={`/api/excel/day/${s.today}?lang=${lang}`}
            variant="light"
            leftSection={<IconDownload size={18} />}
            disabled={rows.length === 0}
          >
            {t('download_today')}
          </Button>
        </Group>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Stat label={t('stat_total')} value={rows.length} />
          <Stat label={t('stat_in')} value={rows.filter((r) => r.direction === 'IN').length} color="teal" />
          <Stat label={t('stat_out')} value={rows.filter((r) => r.direction === 'OUT').length} color="orange" />
          <Stat label={t('stat_review')} value={rows.filter((r) => r.needs_review).length} color="yellow" />
        </SimpleGrid>
        {rows.length === 0 ? (
          <Text c="dimmed">{t('no_trucks_today')}</Text>
        ) : (
          <>
            <Paper withBorder radius="lg"><TruckTable rows={rows} /></Paper>
            <Text size="sm" c="dimmed">{t('live_hint')}</Text>
          </>
        )}
      </Stack>
    </Stack>
  )
}

const STATE_COLOR = { ok: 'teal', connecting: 'blue', offline: 'red', stopped: 'gray' } as const

function CameraCard({ cam, at }: { cam: CameraState; at: number }) {
  const t = useT()
  const label = cam.state === 'offline'
    ? (cam.age === null ? t('cam_offline_never') : t('cam_offline', { s: cam.age }))
    : t(`cam_${cam.state}`)
  return (
    <Card withBorder radius="lg" padding={0}>
      <AspectRatio ratio={16 / 9} bg="var(--mantine-color-default-hover)">
        {cam.has_picture ? (
          <Image src={`/api/live/${encodeURIComponent(cam.name)}.jpg?t=${at}`} alt={cam.name} fit="contain" />
        ) : (
          <Center>
            <Stack align="center" gap={4}>
              <IconCameraOff size={40} stroke={1.4} color="var(--mantine-color-dimmed)" />
              <Text c="dimmed" size="sm">{t('no_picture_yet')}</Text>
            </Stack>
          </Center>
        )}
      </AspectRatio>
      <Group justify="space-between" p="md" wrap="nowrap" align="flex-start">
        <Stack gap={4}>
          <Group gap="xs">
            <Text fw={700} size="lg">{cam.name}</Text>
            <Direction value={cam.direction} />
          </Group>
          {cam.location && <Text size="sm" c="dimmed">{cam.location}</Text>}
          {cam.state === 'offline' && <Text size="sm" c="red">{t('cam_offline_help')}</Text>}
        </Stack>
        <Badge size="lg" color={STATE_COLOR[cam.state]} variant={cam.state === 'ok' ? 'filled' : 'light'} style={{ flexShrink: 0 }}>
          {label}
        </Badge>
      </Group>
    </Card>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Paper withBorder p="md" radius="lg">
      <Text size="sm" c="dimmed">{label}</Text>
      <Text fz={32} fw={700} c={color && value ? `${color}.7` : undefined} lh={1.2}>{value}</Text>
    </Paper>
  )
}
