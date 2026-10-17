import { useState } from 'react'
import { Anchor, Group, Image, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import { IconPhotoOff } from '@tabler/icons-react'
import { type Truck, useT } from '../api'
import { Direction } from './TruckTable'

/** One truck: its readings, plate close-up (to compare with the reading) and snapshot. */
export default function TruckDetail({ row }: { row: Truck }) {
  const t = useT()
  const yesNo = (v: number | null) => (v === null ? '—' : t(v ? 'confirmed' : 'not_confirmed'))
  const details: [string, string | null][] = [
    ['plate', row.plate],
    ['plate_ar', row.plate_ar],
    ['plate_check', row.plate ? yesNo(row.plate_verified) : null],
    ['container', row.container],
    ['col_check', row.container ? yesNo(row.check_digit_ok) : null],
    ['size_type', row.size_type],
    ['camera', row.camera],
    ['location', row.location],
  ]
  return (
    <Stack gap="lg">
      <Group gap="sm">
        <Text fw={700} size="xl" ff="monospace">{row.time}</Text>
        <Direction value={row.direction} />
      </Group>
      <SimpleGrid cols={2} spacing="md" verticalSpacing="sm">
        {details.map(([k, v]) => (
          <div key={k}>
            <Text size="sm" c="dimmed">{t(k)}</Text>
            <Text fw={600} ff={['plate', 'container'].includes(k) ? 'monospace' : undefined}><bdi>{v || '—'}</bdi></Text>
          </div>
        ))}
      </SimpleGrid>
      {row.plate_image && <Photo key={`p${row.id}`} src={`/api/records/${row.id}/plate_image`} label={t('plate_image')} />}
      <Photo key={`s${row.id}`} src={row.snapshot ? `/api/records/${row.id}/snapshot` : null} label={t('snapshot')} />
    </Stack>
  )
}

function Photo({ src, label }: { src: string | null; label: string }) {
  const t = useT()
  const [broken, setBroken] = useState(false)
  return (
    <Stack gap={6}>
      <Group justify="space-between">
        <Text size="sm" fw={600}>{label}</Text>
        {src && !broken && <Anchor href={src} target="_blank" size="sm">{t('open_full')}</Anchor>}
      </Group>
      {src && !broken ? (
        <Image src={src} alt={label} radius="md" mah="55vh" fit="contain" w="100%" onError={() => setBroken(true)} />
      ) : (
        <Paper withBorder radius="md" p="lg">
          <Group gap="sm" c="dimmed"><IconPhotoOff size={22} /><Text>{t('photo_missing')}</Text></Group>
        </Paper>
      )}
    </Stack>
  )
}
