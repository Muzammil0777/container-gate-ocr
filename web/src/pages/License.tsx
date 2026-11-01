import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Code, CopyButton, Group, Paper, Stack, Text, Textarea, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconCheck, IconCopy, IconKey } from '@tabler/icons-react'
import { api, ApiError, send, useT } from '../api'
import HelpTip from '../components/HelpTip'

/** /api/license: this computer's license (see src/license.py). */
export type License = {
  state: 'trial' | 'active' | 'expiring' | 'grace' | 'expired' | 'unlicensed'
  ends: string; days_left: number; grace_days: number; machine: string; clock_behind: boolean
  customer: string | null; site: string | null
}

/** The license, reloaded whenever a key is activated anywhere in the app. */
export function useLicense() {
  const [lic, setLic] = useState<License>()
  useEffect(() => {
    const load = () => api<License>('/api/license').then(setLic).catch(() => {})
    load()
    addEventListener('gate-license', load)
    return () => removeEventListener('gate-license', load)
  }, [])
  return lic
}

export const needsKey = (lic?: License) => lic?.state === 'unlicensed' || lic?.state === 'expired'

/** On every page but the License page, from 30 days before the end date: when it ends and whom to contact. */
export function LicenseBanner() {
  const t = useT()
  const lic = useLicense()
  if (!lic || !['expiring', 'grace', 'expired', 'unlicensed'].includes(lic.state) || location.hash === '#license') return null
  const vars = { date: lic.ends, n: lic.state === 'grace' ? lic.grace_days + lic.days_left : lic.days_left }
  return (
    <Alert color={lic.state === 'expiring' ? 'yellow' : 'red'} icon={<IconAlertTriangle />} mb="lg">
      <Stack gap="xs">
        <Text fw={600}>{t(`license_banner_${lic.state}`, vars)}</Text>
        <Text size="sm">{t('license_contact')}</Text>
        <Group><Button component="a" href="#license" size="xs" variant="white" leftSection={<IconKey size={16} />}>{t('enter_key')}</Button></Group>
      </Stack>
    </Alert>
  )
}

/** Activation screen: opened by itself when there is no license (after the trial). */
export default function LicensePage() {
  const t = useT()
  const lic = useLicense()
  return (
    <Stack gap="md">
      {needsKey(lic) && (
        <Paper withBorder radius="lg" p="lg">
          <Title order={3}>{t('activation_title')}</Title>
          <Text mt="xs">{t('activation_help')}</Text>
        </Paper>
      )}
      <LicenseCard />
    </Stack>
  )
}

/** State, end date, machine code to copy, and a box to paste a key; on the Cameras page too. */
export function LicenseCard() {
  const t = useT()
  const lic = useLicense()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; key: string }>()  // a text key, so it follows the language

  const activate = async () => {
    setBusy(true); setResult(undefined)
    try {
      await send('POST', '/api/license', { key })
      setKey(''); setResult({ ok: true, key: 'license_activated' })
      dispatchEvent(new Event('gate-license'))
    } catch (e) {
      const reason = e instanceof ApiError ? e.body?.detail?.errors?.[0] : undefined
      setResult({ ok: false, key: reason ?? 'server_down' })
    } finally { setBusy(false) }
  }

  if (!lic) return null
  return (
    <Paper id="license" withBorder radius="lg" p="lg">
      <Stack gap="md">
        <Group gap="sm">
          <Title order={3}>{t('license')}</Title>
          <Badge size="lg" variant="light" color={needsKey(lic) || lic.state === 'grace' ? 'red' : lic.state === 'expiring' ? 'yellow' : 'teal'}>
            {t(`license_state_${lic.state}`)}
          </Badge>
        </Group>
        <Text>{t(lic.days_left < 0 ? 'license_ended' : 'license_ends', { date: lic.ends, n: lic.days_left })}</Text>
        {lic.customer && <Text c="dimmed">{t('license_for', { customer: lic.customer, site: lic.site ?? '' })}</Text>}
        {lic.clock_behind && <Alert color="yellow" icon={<IconAlertTriangle />}>{t('license_clock_behind')}</Alert>}
        <div>
          <Group gap={6}><Text size="sm" fw={500}>{t('machine_code')}</Text><HelpTip text={t('help_machine_code')} /></Group>
          <Group gap="sm" mt={4}>
            <Code fz="xl" dir="ltr">{lic.machine}</Code>
            <CopyButton value={lic.machine}>
              {({ copied, copy }) => (
                <Button variant="light" size="sm" onClick={copy} color={copied ? 'teal' : undefined}
                        leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}>
                  {t(copied ? 'copied' : 'copy')}
                </Button>
              )}
            </CopyButton>
          </Group>
        </div>
        <Text size="sm" c="dimmed">{t('license_contact')}</Text>
        <form onSubmit={(e) => { e.preventDefault(); activate() }}>
          <Stack gap="sm">
            <Textarea label={t('license_key')} description={t('license_key_help')} value={key} dir="ltr"
                      onChange={(e) => setKey(e.currentTarget.value)} autosize minRows={2} maxRows={6}
                      styles={{ input: { fontFamily: 'monospace' } }} />
            {result && <Alert color={result.ok ? 'teal' : 'red'} icon={result.ok ? <IconCheck /> : <IconAlertTriangle />}>{t(result.key)}</Alert>}
            <Group><Button type="submit" size="md" loading={busy} disabled={!key.trim()} leftSection={<IconKey size={18} />}>{t('activate')}</Button></Group>
          </Stack>
        </form>
      </Stack>
    </Paper>
  )
}
