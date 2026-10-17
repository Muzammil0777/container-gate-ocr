import { useState } from 'react'
import { Alert, Anchor, Button, Group, Image, Paper, SegmentedControl, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { IconAlertTriangle, IconCheck, IconPencil, IconPhotoOff } from '@tabler/icons-react'
import { ApiError, send, type Truck, useT } from '../api'
import { Direction } from './TruckTable'

/** One truck: its readings, plate close-up (to compare with the reading), a form to correct
 *  the reading, and the snapshot. `onSaved` is called after a correction is saved. */
export default function TruckDetail({ row, onSaved }: { row: Truck; onSaved: () => void }) {
  const t = useT()
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState<{ warning: string | null }>()
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
      {saved && (
        <Alert color={saved.warning ? 'yellow' : 'teal'} icon={saved.warning ? <IconAlertTriangle /> : <IconCheck />}>
          {t(saved.warning ?? 'fix_saved')}
        </Alert>
      )}
      {editing ? (
        <FixForm row={row} onCancel={() => setEditing(false)}
                 onSaved={(warning) => { setEditing(false); setSaved({ warning }); onSaved() }} />
      ) : (
        <Button variant="light" size="md" leftSection={<IconPencil size={18} />} onClick={() => { setSaved(undefined); setEditing(true) }}>
          {t('fix_reading')}
        </Button>
      )}
      <Photo key={`s${row.id}`} src={row.snapshot ? `/api/records/${row.id}/snapshot` : null} label={t('snapshot')} />
    </Stack>
  )
}

function FixForm({ row, onCancel, onSaved }: { row: Truck; onCancel: () => void; onSaved: (warning: string | null) => void }) {
  const t = useT()
  const [plate, setPlate] = useState(row.plate ?? '')
  const [container, setContainer] = useState(row.container ?? '')
  const [direction, setDirection] = useState(row.direction ?? 'IN')
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const save = async () => {
    setBusy(true); setErrors([]); setFailed(false)
    try {
      const r = await send<{ warning: string | null }>('PATCH', `/api/records/${row.id}`, { plate, container, direction })
      onSaved(r.warning)
    } catch (e) {
      const keys = e instanceof ApiError ? e.body?.detail?.errors : undefined
      if (Array.isArray(keys)) setErrors(keys)
      else setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper withBorder radius="md" p="md">
      <form onSubmit={(e) => { e.preventDefault(); save() }}>
        <Stack gap="sm">
          <Text fw={700}>{t('fix_reading')}</Text>
          <TextInput label={t('plate')} placeholder="3231 UTA" value={plate} size="md" styles={{ input: { fontFamily: 'monospace' } }}
                     onChange={(e) => setPlate(e.currentTarget.value)}
                     error={errors.includes('bad_plate') && t('bad_plate')} />
          <TextInput label={t('container')} placeholder="MRSU 786939 5" value={container} size="md" styles={{ input: { fontFamily: 'monospace' } }}
                     onChange={(e) => setContainer(e.currentTarget.value)}
                     error={errors.includes('bad_container') && t('bad_container')} />
          <div>
            <Text size="sm" fw={500} mb={4}>{t('direction')}</Text>
            <SegmentedControl value={direction} onChange={(v) => setDirection(v as 'IN' | 'OUT')}
                              data={[{ value: 'IN', label: t('IN') }, { value: 'OUT', label: t('OUT') }]} />
          </div>
          <Text size="sm" c="dimmed">{t('fix_empty_hint')}</Text>
          {failed && <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>}
          <Group>
            <Button type="submit" size="md" loading={busy}>{t('save_correction')}</Button>
            <Button variant="default" size="md" onClick={onCancel}>{t('cancel')}</Button>
          </Group>
        </Stack>
      </form>
    </Paper>
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
