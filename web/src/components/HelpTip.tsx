import { ActionIcon, Popover, Text } from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { useT } from '../api'

/** A small (i) that explains a term in plain words; opens on tap, so it works on phones. */
export default function HelpTip({ text }: { text: string }) {
  const t = useT()
  return (
    <Popover width={300} withArrow shadow="md" position="bottom">
      <Popover.Target>
        <ActionIcon variant="subtle" color="gray" size="sm" radius="xl" aria-label={t('help')}>
          <IconInfoCircle size={16} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown><Text size="sm">{text}</Text></Popover.Dropdown>
    </Popover>
  )
}
