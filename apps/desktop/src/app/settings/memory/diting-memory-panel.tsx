import { useCallback, useEffect, useState } from 'react'

import {
  type DitingMemoryAction,
  type DitingMemoryData,
  type DitingMemoryTarget,
  type DitingProfileData,
  editDitingMemory,
  getDitingMemory,
  getDitingProfile
} from '@/api/diting'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import type { DitingMemoryTranslations } from '@/i18n/types_diting_memory'
import { Ear, Pencil, Plus, Trash2, X } from '@/lib/icons'

import { Pill, SettingsSection } from '../primitives'

// CLI 等效命令——命令本身不翻译，说明文字走 cliNote。与 `hermes diting help`
// 的命令全览同源（plugins/diting_guard/cli.py），保持两端提示一致。
const CLI_LINES = [
  'hermes diting profile',
  'hermes diting profile add <content>',
  'hermes diting memory',
  'hermes diting memory add <content>',
  'hermes diting tasks list',
  'hermes diting help'
]

interface EditDraft {
  index: number
  draft: string
  target: DitingMemoryTarget
}

/** One built-in store (MEMORY.md or USER.md): usage, entries, add/edit/remove. */
function MemoryStoreCard({
  busy,
  data,
  disabled,
  m,
  onMutate,
  title
}: {
  busy: boolean
  data: DitingMemoryData | null
  disabled: boolean
  m: DitingMemoryTranslations
  onMutate: (action: DitingMemoryAction, fields: { content?: string; new_text?: string; old_text?: string }) => void
  title: string
}) {
  const [adding, setAdding] = useState('')
  const [edit, setEdit] = useState<EditDraft | null>(null)

  if (!data) {
    return null
  }

  const submitAdd = () => {
    const content = adding.trim()

    if (!content || busy) {
      return
    }

    setAdding('')
    onMutate('add', { content })
  }

  const submitEdit = () => {
    if (!edit || busy) {
      return
    }

    const original = data.entries[edit.index]
    const next = edit.draft.trim()
    setEdit(null)

    if (!next || next === original) {
      return
    }

    // old_text 传整条原文：内核先做整条精确匹配，定位最稳。
    onMutate('replace', { content: next, old_text: original })
  }

  return (
    <div className="rounded-lg border border-border bg-card p-3" data-testid={`diting-${data.target}-card`}>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-medium">{title}</span>
        <Pill>{m.usage(data.char_count.toLocaleString(), data.char_limit.toLocaleString())}</Pill>
        {!data.enabled ? <Pill tone="warn">{m.disabledNote}</Pill> : null}
      </div>
      {data.entries.length === 0 ? (
        <p className="mb-2 text-xs text-muted-foreground">{m.empty}</p>
      ) : (
        <ol className="mb-2 grid gap-1.5">
          {data.entries.map((entry, index) => (
            <li className="flex items-start gap-2 text-sm" key={`${data.target}-${index}`}>
              <span className="mt-0.5 w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                {index + 1}.
              </span>
              {edit?.target === data.target && edit.index === index ? (
                <span className="grid min-w-0 flex-1 gap-1.5">
                  <Textarea onChange={e => setEdit({ ...edit, draft: e.target.value })} rows={3} value={edit.draft} />
                  <span className="flex items-center gap-1.5">
                    <Button disabled={busy} onClick={submitEdit} size="xs" type="button">
                      {m.save}
                    </Button>
                    <Button onClick={() => setEdit(null)} size="xs" type="button" variant="textStrong">
                      {m.cancel}
                    </Button>
                    <span className="text-xs text-muted-foreground">{m.editHint}</span>
                  </span>
                </span>
              ) : (
                <>
                  <span className="min-w-0 flex-1 break-words">{entry}</span>
                  <span className="flex shrink-0 gap-0.5">
                    <Button
                      aria-label={m.edit}
                      disabled={busy || disabled}
                      onClick={() => setEdit({ index, draft: entry, target: data.target })}
                      size="xs"
                      type="button"
                      variant="ghost"
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      aria-label={m.delete}
                      disabled={busy || disabled}
                      onClick={() => onMutate('remove', { old_text: entry })}
                      size="xs"
                      type="button"
                      variant="ghost"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ol>
      )}
      <div className="flex items-center gap-1.5">
        <Input
          disabled={busy || disabled}
          onChange={e => setAdding(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              submitAdd()
            }
          }}
          placeholder={m.addPlaceholder}
          value={adding}
        />
        <Button disabled={busy || disabled || !adding.trim()} onClick={submitAdd} size="xs" type="button">
          <Plus className="size-3.5" />
          {m.add}
        </Button>
      </div>
    </div>
  )
}

/** 谛听扩展画像：兴趣信号（授权制）、授权状态、进行中长任务——只读，改动走各自命令。 */
function DitingExtraCard({ m, profile }: { m: DitingMemoryTranslations; profile: DitingProfileData | null }) {
  if (!profile) {
    return null
  }

  if (profile.diting_error) {
    return <p className="text-xs text-muted-foreground">{m.kernelUnavailable}</p>
  }

  const interests = Object.entries(profile.interests ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)

  const consent = Object.entries(profile.consent ?? {})
  const tasks = profile.longtask?.active ?? []

  return (
    <div className="grid gap-2 rounded-lg border border-border bg-card p-3 text-sm" data-testid="diting-extra-card">
      <span className="text-sm font-medium">{m.ditingCard}</span>
      <div className="grid gap-1">
        <span className="text-xs text-muted-foreground">{m.interests}</span>
        {interests.length === 0 ? (
          <span className="text-xs text-muted-foreground">{m.interestsEmpty}</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {interests.map(([key, score]) => (
              <Pill key={key}>
                {key} · {score.toFixed(1)}
              </Pill>
            ))}
          </span>
        )}
      </div>
      {consent.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">{m.consent}:</span>
          {consent.map(([scope, granted]) => (
            <Pill key={scope} tone={granted ? 'success' : 'muted'}>
              {scope} · {granted ? m.consentGranted : m.consentDenied}
            </Pill>
          ))}
        </div>
      ) : null}
      <div className="grid gap-1">
        <span className="text-xs text-muted-foreground">{m.longtask}</span>
        {tasks.length === 0 ? (
          <span className="text-xs text-muted-foreground">{m.longtaskEmpty}</span>
        ) : (
          tasks.slice(0, 5).map(task => (
            <span className="text-xs" key={task.task_id}>
              [{task.task_id}] {task.title}（{task.open_steps.length} open）
            </span>
          ))
        )}
      </div>
    </div>
  )
}

/** Settings > Memory & Context: 谛听画像与长程记忆（与 hermes diting profile/memory CLI 同源数据）。 */
export function DitingMemoryPanel({ profile }: { profile?: null | string }) {
  const { t } = useI18n()
  const m = t.settings.ditingMemory
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  // 读写分开两个错误位：刷新只清加载错误，编辑失败的提示不会被紧随其后的
  // refresh 静默抹掉（编辑失败必须可见，见测试 'surfaces a failed edit'）。
  const [loadError, setLoadError] = useState<null | string>(null)
  const [editError, setEditError] = useState<null | string>(null)
  const [memory, setMemory] = useState<DitingMemoryData | null>(null)
  const [user, setUser] = useState<DitingMemoryData | null>(null)
  const [extra, setExtra] = useState<DitingProfileData | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoadError(null)
    Promise.all([getDitingMemory('memory', profile), getDitingMemory('user', profile), getDitingProfile(profile)])
      .then(([memoryNext, userNext, profileNext]) => {
        if (!cancelled) {
          setMemory(memoryNext)
          setUser(userNext)
          setExtra(profileNext)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(m.failedTitle)
        }
      })

    return () => {
      cancelled = true
    }
  }, [attempt, m.failedTitle, profile])

  const refresh = useCallback(() => setAttempt(n => n + 1), [])

  const mutate = (target: DitingMemoryTarget) =>
    (
      action: DitingMemoryAction,
      fields: { content?: string; new_text?: string; old_text?: string }
    ) => {
      setBusy(true)
      setEditError(null)
      editDitingMemory({ action, target, ...fields }, profile)
        .then(result => {
          if (!result.success) {
            setEditError(result.error ?? result.message ?? m.failedTitle)
          }

          refresh()
        })
        .catch(() => setEditError(m.failedTitle))
        .finally(() => setBusy(false))
    }

  const error = editError ?? loadError

  return (
    <SettingsSection icon={Ear} title={m.panelTitle}>
      <div className="grid gap-3" data-testid="diting-memory-panel">
        <p className="text-xs text-muted-foreground">{m.panelDesc}</p>
        {error ? (
          <p className="flex items-center gap-1 text-xs text-destructive" role="alert">
            <X className="size-3.5 shrink-0" />
            {error}
          </p>
        ) : null}
        <MemoryStoreCard
          busy={busy}
          data={user}
          disabled={user?.enabled === false}
          m={m}
          onMutate={mutate('user')}
          title={m.profileCard}
        />
        <MemoryStoreCard
          busy={busy}
          data={memory}
          disabled={memory?.enabled === false}
          m={m}
          onMutate={mutate('memory')}
          title={m.memoryCard}
        />
        <DitingExtraCard m={m} profile={extra} />
        <div className="grid gap-1 rounded-lg border border-dashed border-border p-3">
          <span className="text-xs font-medium">{m.cliTitle}</span>
          <span className="text-xs text-muted-foreground">{m.cliNote}</span>
          <pre className="overflow-x-auto text-xs text-muted-foreground">
            {CLI_LINES.map(line => (
              <span className="block font-mono" key={line}>
                {line}
              </span>
            ))}
          </pre>
        </div>
      </div>
    </SettingsSection>
  )
}

interface DitingMemorySlotProps {
  profile?: null | string
  sectionId: string
  subpage?: string
}

/** Settings > Memory & Context > Persistent memory（与 MemoryLayersSlot 同门控）。 */
export function DitingMemorySlot({ profile, sectionId, subpage }: DitingMemorySlotProps) {
  if (sectionId !== 'memory' || (subpage !== undefined && subpage !== 'persistent')) {
    return null
  }

  return <DitingMemoryPanel profile={profile} />
}
