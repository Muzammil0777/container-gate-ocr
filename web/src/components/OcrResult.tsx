import { Badge, Grid, Group, Image, Paper, Stack, Text } from '@mantine/core'
import { useT } from '../api'

export type OcrResult = {
  ms: number
  codes: { code: string; valid: boolean; readable: boolean; size_type: string; score: number }[]
  plates: { plate: string; arabic: string; verified: boolean; score: number }[]
  texts: string[]
  image: string  // the picture with boxes drawn, as a data: URL
}

/** What the OCR read in one picture: the picture with boxes, the container codes and plates. */
export default function OcrResultView({ result }: { result: OcrResult }) {
  const t = useT()
  const found = result.codes.length + result.plates.length > 0
  return (
    <Grid gap="md">
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Image src={result.image} radius="md" alt="" />
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{t('read_in', { ms: result.ms })}</Text>
          {!found && <Text>{t('nothing_found')}</Text>}
          {result.codes.map((c, i) => (
            <Paper key={`c${i}`} withBorder radius="md" p="sm">
              <Text size="xs" c="dimmed">{t('container')}</Text>
              <Group justify="space-between" wrap="nowrap">
                <Text fw={700} size="lg" ff="monospace"><bdi>{c.code}</bdi></Text>
                <Badge color={c.valid ? 'teal' : 'yellow'} variant="light">{t(c.valid ? 'confirmed' : 'not_confirmed')}</Badge>
              </Group>
              {c.size_type && <Text size="sm" c="dimmed">{c.size_type}</Text>}
            </Paper>
          ))}
          {result.plates.map((p, i) => (
            <Paper key={`p${i}`} withBorder radius="md" p="sm">
              <Text size="xs" c="dimmed">{t('plate')}</Text>
              <Group justify="space-between" wrap="nowrap">
                <Text fw={700} size="lg" ff="monospace"><bdi>{p.plate}</bdi></Text>
                <Badge color={p.verified ? 'teal' : 'yellow'} variant="light">{t(p.verified ? 'confirmed' : 'not_confirmed')}</Badge>
              </Group>
              <Text size="sm" c="dimmed"><bdi>{p.arabic}</bdi></Text>
            </Paper>
          ))}
          {result.texts.length > 0 && (
            <details>
              <summary style={{ cursor: 'pointer' }}><Text span size="sm" c="dimmed">{t('all_text')}</Text></summary>
              <Text size="sm" ff="monospace" mt="xs"><bdi>{result.texts.join(' · ')}</bdi></Text>
            </details>
          )}
        </Stack>
      </Grid.Col>
    </Grid>
  )
}
