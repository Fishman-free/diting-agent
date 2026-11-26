// 谛听画像与长程记忆 API（后端 hermes_cli/web_routers/diting.py）。
// 与 `hermes diting profile/memory` CLI 共享同一批 handler，数据永远一致。
import { hermesApi, profileScoped } from './client'

export type DitingMemoryTarget = 'memory' | 'user'
export type DitingMemoryAction = 'add' | 'patch' | 'remove' | 'replace'

export interface DitingMemoryData {
  target: DitingMemoryTarget
  file: string
  enabled: boolean
  entries: string[]
  char_count: number
  char_limit: number
}

export interface DitingMemoryEditResult {
  success: boolean
  error?: string
  message?: string
  usage?: string
  entry_count?: number
  matches?: string[]
  current_entries?: string[]
}

export interface DitingLongTaskSummary {
  task_id: string
  title: string
  open_steps: string[]
}

export interface DitingProfileData {
  user: DitingMemoryData
  interests?: Record<string, number>
  consent?: Record<string, boolean>
  longtask?: { active: DitingLongTaskSummary[]; active_count: number }
  knowledge_count?: number
  diting_error?: string
}

export function getDitingMemory(target: DitingMemoryTarget, profile?: null | string): Promise<DitingMemoryData> {
  return hermesApi<DitingMemoryData>({
    ...profileScoped(profile),
    path: `/api/diting/memory?target=${target}`
  })
}

export function editDitingMemory(
  payload: { action: DitingMemoryAction; content?: string; new_text?: string; old_text?: string; target: DitingMemoryTarget },
  profile?: null | string
): Promise<DitingMemoryEditResult> {
  return hermesApi<DitingMemoryEditResult>({
    ...profileScoped(profile),
    path: '/api/diting/memory',
    method: 'POST',
    body: payload
  })
}

export function getDitingProfile(profile?: null | string): Promise<DitingProfileData> {
  return hermesApi<DitingProfileData>({
    ...profileScoped(profile),
    path: '/api/diting/profile'
  })
}
