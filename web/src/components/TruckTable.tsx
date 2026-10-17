import { Badge, Group, Stack, Table, Text, Tooltip } from '@mantine/core'
import { IconAlertTriangle, IconCircleCheck, IconLogin, IconLogout, IconPencil } from '@tabler/icons-react'
import { type Truck, useT } from '../api'
import HelpTip from './HelpTip'

/** Trucks as a table; `onPick` makes rows clickable (Records page). */
export default function TruckTable({ rows, onPick, picked }: { rows: Truck[]; onPick?: (r: Truck) => void; picked?: number }) {
  const t = useT()
  return (
    <Table.ScrollContainer minWidth={680}>
      <Table highlightOnHover={!!onPick} verticalSpacing="sm" striped>
        <Table.Thead>
          <Table.Tr>
            {['time', 'direction', 'plate', 'container', 'camera', 'col_status'].map((k) => (
              <Table.Th key={k}>
                <Group gap={4} wrap="nowrap">
                  {t(k)}
                  {k === 'container' && <HelpTip text={t('help_check_digit')} />}
                  {k === 'col_status' && <HelpTip text={t('help_check')} />}
                </Group>
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr
              key={r.id}
              onClick={onPick && (() => onPick(r))}
              style={onPick && { cursor: 'pointer' }}
              bg={picked === r.id ? 'var(--mantine-primary-color-light)' : undefined}
            >
              <Table.Td><Text ff="monospace">{r.time.slice(0, 5)}</Text></Table.Td>
              <Table.Td><Direction value={r.direction} /></Table.Td>
              <Table.Td>
                {r.plate ? (
                  <Stack gap={0}>
                    <Group gap={6} wrap="nowrap">
                      <Text fw={600} ff="monospace"><bdi>{r.plate}</bdi></Text>
                      <Check ok={!!r.plate_verified} />
                    </Group>
                    <Text size="sm" c="dimmed"><bdi>{r.plate_ar}</bdi></Text>
                  </Stack>
                ) : <Text c="dimmed">—</Text>}
              </Table.Td>
              <Table.Td>
                {r.container ? (
                  <Stack gap={0}>
                    <Group gap={6} wrap="nowrap">
                      <Text fw={600} ff="monospace" style={{ whiteSpace: 'nowrap' }}><bdi>{r.container}</bdi></Text>
                      <Check ok={!!r.check_digit_ok} />
                    </Group>
                    {r.size_type && <Text size="sm" c="dimmed">{r.size_type}</Text>}
                  </Stack>
                ) : <Text c="dimmed">—</Text>}
              </Table.Td>
              <Table.Td><Text size="sm">{r.camera}</Text></Table.Td>
              <Table.Td><Status row={r} /></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

export function Direction({ value }: { value: string | null }) {
  const t = useT()
  if (!value) return null
  const IN = value === 'IN'
  return (
    <Badge color={IN ? 'teal' : 'orange'} variant="light" size="lg" leftSection={IN ? <IconLogin size={14} /> : <IconLogout size={14} />}>
      {t(value)}
    </Badge>
  )
}

function Check({ ok }: { ok: boolean }) {
  const t = useT()
  return (
    <Tooltip label={t(ok ? 'confirmed' : 'not_confirmed')}>
      {ok ? <IconCircleCheck size={18} color="var(--mantine-color-teal-6)" />
        : <IconAlertTriangle size={18} color="var(--mantine-color-yellow-6)" />}
    </Tooltip>
  )
}

function Status({ row }: { row: Truck }) {
  const t = useT()
  if (row.corrected) return <Badge color="blue" variant="light" leftSection={<IconPencil size={12} />}>{t('badge_fixed')}</Badge>
  if (row.needs_review) return <Badge color="yellow" variant="light" leftSection={<IconAlertTriangle size={12} />}>{t('badge_check')}</Badge>
  return null
}
