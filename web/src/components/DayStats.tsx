import { Paper, SimpleGrid, Text } from '@mantine/core'
import { type Truck, useT } from '../api'

/** Trucks / came in / went out / to check, for a list of trucks. */
export default function DayStats({ rows }: { rows: Truck[] }) {
  const t = useT()
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }}>
      <Stat label={t('stat_trucks')} value={rows.length} />
      <Stat label={t('stat_in')} value={rows.filter((r) => r.direction === 'IN').length} color="teal" />
      <Stat label={t('stat_out')} value={rows.filter((r) => r.direction === 'OUT').length} color="orange" />
      <Stat label={t('stat_review')} value={rows.filter((r) => r.needs_review).length} color="yellow" />
    </SimpleGrid>
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
