import { useState } from 'react'
import { ActionIcon, Alert, Button, Drawer, Group, Paper, Stack, Switch, Text, TextInput, Tooltip } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconAlertTriangle, IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { type Truck, useLang, usePoll, useT } from '../api'
import DayStats from '../components/DayStats'
import TruckDetail from '../components/TruckDetail'
import TruckTable from '../components/TruckTable'

/** 'YYYY-MM-DD' moved by n days (at noon, so a clock change can't skip a day). */
function shift(day: string, n: number) {
  const d = new Date(`${day}T12:00:00`)
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Records() {
  const t = useT()
  const rtl = useLang() === 'ar'
  const today = usePoll<{ today: string }>('/api/status', 60000).data?.today ?? ''  // the gate computer's date
  const [picked, setPicked] = useState<string>()
  const day = picked ?? today
  const records = usePoll<Truck[]>(day ? `/api/records?day=${day}` : null, 15000)  // new trucks keep coming in
  const [onlyCheck, setOnlyCheck] = useState(false)
  const [open, setOpen] = useState<number>()
  const small = useMediaQuery('(max-width: 48em)')
  const setDay = (d: string) => { setPicked(d); setOpen(undefined) }
  if (!day) return null

  const rows = records.data ?? []
  const shown = onlyCheck ? rows.filter((r) => r.needs_review) : rows  // oldest first: rows keep their place
  const row = rows.find((r) => r.id === open)
  const [Prev, Next] = rtl ? [IconChevronRight, IconChevronLeft] : [IconChevronLeft, IconChevronRight]

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end">
        <Group gap="xs" align="flex-end" wrap="nowrap">
          <Tooltip label={t('prev_day')}>
            <ActionIcon variant="default" size={36} onClick={() => setDay(shift(day, -1))} aria-label={t('prev_day')}>
              <Prev size={20} />
            </ActionIcon>
          </Tooltip>
          <TextInput type="date" label={t('pick_day')} value={day} max={today}
                     onChange={(e) => e.currentTarget.value && setDay(e.currentTarget.value)} />
          <Tooltip label={t('next_day')}>
            <ActionIcon variant="default" size={36} onClick={() => setDay(shift(day, 1))} disabled={day >= today} aria-label={t('next_day')}>
              <Next size={20} />
            </ActionIcon>
          </Tooltip>
          {day !== today && <Button variant="subtle" onClick={() => setDay(today)}>{t('go_today')}</Button>}
        </Group>
        <Switch size="md" label={t('only_to_check')} checked={onlyCheck} onChange={(e) => setOnlyCheck(e.currentTarget.checked)} />
      </Group>

      {records.failed && <Alert color="red" icon={<IconAlertTriangle />}>{t('server_down')}</Alert>}
      <DayStats rows={rows} />

      {records.data && (shown.length === 0 ? (
        <Text c="dimmed">{onlyCheck && rows.length ? t('none_to_check') : t('no_rows_day', { day })}</Text>
      ) : (
        <Stack gap="xs">
          <Text size="sm" c="dimmed">{t('tap_truck')}</Text>
          <Paper withBorder radius="lg"><TruckTable rows={shown} onPick={(r) => setOpen(r.id)} picked={open} /></Paper>
        </Stack>
      ))}

      <Drawer
        opened={!!row}
        onClose={() => setOpen(undefined)}
        position={rtl ? 'left' : 'right'}
        size={small ? '100%' : 'lg'}
        title={row && <Text fw={700}>{row.camera}</Text>}
      >
        {row && <TruckDetail row={row} />}
      </Drawer>
    </Stack>
  )
}
