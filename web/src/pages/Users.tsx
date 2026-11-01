import { useEffect, useState } from 'react'
import {
  Alert, Badge, Button, Group, Modal, Paper, PasswordInput, Select, SimpleGrid, Stack, Switch, Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconAlertTriangle, IconCheck, IconKey, IconUserPlus } from '@tabler/icons-react'
import { api, ApiError, send, useT } from '../api'
import HelpTip from '../components/HelpTip'

type Role = 'viewer' | 'operator' | 'admin'
type User = { id: number; username: string; name: string; role: Role; active: number; created: string }
/** /api/users: every user and how many may be turned on. */
type UserList = { users: User[]; limit: number }
const ROLES: Role[] = ['viewer', 'operator', 'admin']
const NEW_USER = { username: '', name: '', role: 'operator' as Role, password: '' }

const errorKey = (e: unknown) => (e instanceof ApiError && e.body?.detail?.errors?.[0]) || 'server_down'

/** Admins only: add users, change what they can do, turn them off, give them a new password. */
export default function Users() {
  const t = useT()
  const [data, setData] = useState<UserList>()
  // a text key (so it follows the language), shown next to the part of the page it is about
  const [message, setMessage] = useState<{ ok: boolean; key: string; at: 'list' | 'add' | 'reset' }>()
  const [resetting, setResetting] = useState<User>()

  useEffect(() => { api<UserList>('/api/users').then(setData).catch((e) => setMessage({ ok: false, key: errorKey(e), at: 'list' })) }, [])

  const run = async (call: Promise<UserList>, at: 'list' | 'add' | 'reset' = 'list') => {
    setMessage(undefined)
    try {
      setData(await call); setMessage({ ok: true, key: 'saved', at })
      return true
    } catch (e) {
      setMessage({ ok: false, key: errorKey(e), at })
      return false
    }
  }
  const change = (u: User, body: object, at: 'list' | 'reset' = 'list') => run(send<UserList>('PATCH', `/api/users/${u.id}`, body), at)

  const limit = data?.limit ?? 0
  const alert = (at: string) => message?.at === at && (
    <Alert color={message.ok ? 'teal' : 'red'} icon={message.ok ? <IconCheck /> : <IconAlertTriangle />}>
      {t(message.key, { n: limit })}
    </Alert>
  )
  if (!data) return alert('list') || null
  const active = data.users.filter((u) => u.active).length
  const full = active >= limit
  const roles = ROLES.map((r) => ({ value: r, label: t(`user_role_${r}`) }))

  return (
    <Stack gap="md">
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="md">
          <Group gap={6}>
            <Badge size="xl" variant="light" tt="none" color={full ? 'yellow' : 'teal'}>{t('users_count', { n: active, m: limit })}</Badge>
            <HelpTip text={t('help_users_count')} />
          </Group>
          {alert('list')}
          <Table.ScrollContainer minWidth={560}>
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('full_name')}</Table.Th>
                  <Table.Th><Group gap={4} wrap="nowrap">{t('user_role')}<HelpTip text={t('help_user_role')} /></Group></Table.Th>
                  <Table.Th />
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.users.map((u) => (
                  <Table.Tr key={u.id} opacity={u.active ? 1 : 0.6}>
                    <Table.Td>
                      <Text fw={600}>{u.name || u.username}</Text>
                      <Text size="sm" c="dimmed"><bdi>{u.username}</bdi></Text>
                    </Table.Td>
                    <Table.Td>
                      <Select data={roles} value={u.role} allowDeselect={false} w={150} aria-label={t('user_role')}
                              onChange={(v) => v && v !== u.role && change(u, { role: v })} />
                    </Table.Td>
                    <Table.Td>
                      <Switch checked={!!u.active} label={t(u.active ? 'user_on' : 'user_off')}
                              onChange={(e) => change(u, { active: e.currentTarget.checked })} />
                    </Table.Td>
                    <Table.Td>
                      <Button variant="light" size="xs" leftSection={<IconKey size={16} />} onClick={() => setResetting(u)}>
                        {t('reset_password')}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      </Paper>

      <Paper withBorder radius="lg" p="lg">
        <Title order={3} mb="md">{t('add_user')}</Title>
        {full ? <Alert color="yellow" icon={<IconAlertTriangle />}>{t('users_limit', { n: limit })}</Alert>
          : <AddUser roles={roles} onAdd={(u) => run(send<UserList>('POST', '/api/users', u), 'add')} />}
        {message?.at === 'add' && <Stack mt="md">{alert('add')}</Stack>}
      </Paper>

      {resetting && (
        <ResetPassword user={resetting} onClose={() => setResetting(undefined)} problem={alert('reset')}
                       onSave={(password) => change(resetting, { password }, 'reset')} />
      )}
    </Stack>
  )
}

function AddUser({ roles, onAdd }: { roles: { value: string; label: string }[]; onAdd: (u: typeof NEW_USER) => Promise<boolean> }) {
  const t = useT()
  const [u, setU] = useState(NEW_USER)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof NEW_USER) => (e: React.ChangeEvent<HTMLInputElement>) => setU({ ...u, [k]: e.currentTarget.value })
  return (
    <form onSubmit={async (e) => {
      e.preventDefault(); setBusy(true)
      if (await onAdd(u)) setU(NEW_USER)
      setBusy(false)
    }}>
      <Stack gap="md">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t('username')} value={u.username} onChange={set('username')} size="md" dir="ltr" autoComplete="off" />
          <TextInput label={t('full_name')} value={u.name} onChange={set('name')} size="md" />
          <Select label={t('user_role')} data={roles} value={u.role} allowDeselect={false} size="md"
                  onChange={(v) => v && setU({ ...u, role: v as Role })} />
          <PasswordInput label={t('password')} description={t('short_password')} value={u.password}
                         onChange={set('password')} size="md" autoComplete="new-password" />
        </SimpleGrid>
        <Group>
          <Button type="submit" size="md" loading={busy} disabled={!u.username.trim() || u.password.length < 6}
                  leftSection={<IconUserPlus size={18} />}>{t('add_user')}</Button>
        </Group>
      </Stack>
    </form>
  )
}

function ResetPassword({ user, onClose, onSave, problem }: {
  user: User; onClose: () => void; onSave: (pw: string) => Promise<boolean>; problem: React.ReactNode
}) {
  const t = useT()
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal opened onClose={onClose} title={<Text fw={700}>{t('reset_password')}: {user.name || user.username}</Text>}>
      <form onSubmit={async (e) => {
        e.preventDefault(); setBusy(true)
        if (await onSave(pw)) onClose()
        else setBusy(false)
      }}>
        <Stack gap="md">
          <Text size="sm">{t('reset_password_help')}</Text>
          <PasswordInput label={t('new_password')} description={t('short_password')} value={pw} data-autofocus
                         onChange={(e) => setPw(e.currentTarget.value)} size="md" autoComplete="new-password" />
          {problem}
          <Group>
            <Button type="submit" size="md" loading={busy} disabled={pw.length < 6}>{t('save_password')}</Button>
            <Button variant="default" size="md" onClick={onClose}>{t('cancel')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
