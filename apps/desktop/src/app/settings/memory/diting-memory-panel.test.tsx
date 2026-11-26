import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type * as DitingApi from '@/api/diting'
import type { DitingMemoryData, DitingProfileData } from '@/api/diting'
import { editDitingMemory, getDitingMemory, getDitingProfile } from '@/api/diting'

vi.mock('@/api/diting', async importOriginal => ({
  ...(await importOriginal<typeof DitingApi>()),
  editDitingMemory: vi.fn(),
  getDitingMemory: vi.fn(),
  getDitingProfile: vi.fn()
}))

const { DitingMemoryPanel } = await import('./diting-memory-panel')

function storeData(target: 'memory' | 'user', entries: string[]): DitingMemoryData {
  return {
    target,
    file: `C:/home/memories/${target === 'user' ? 'USER' : 'MEMORY'}.md`,
    enabled: true,
    entries,
    char_count: entries.join('\n§\n').length,
    char_limit: target === 'user' ? 1375 : 2200
  }
}

const MEMORY_ENTRIES = ['Repo lives at Desktop/diting-agent', 'Second note']
const USER_ENTRIES = ['Prefers simplified Chinese']

function profileData(): DitingProfileData {
  return {
    user: storeData('user', USER_ENTRIES),
    interests: { 量子计算: 3.2 },
    consent: { browse_history: false, recommend_personalized: true },
    longtask: { active: [{ task_id: 't1', title: '写周报', open_steps: ['草稿'] }], active_count: 1 },
    knowledge_count: 67
  }
}

function seed() {
  vi.mocked(getDitingMemory).mockImplementation((target: 'memory' | 'user') =>
    Promise.resolve(storeData(target, target === 'user' ? USER_ENTRIES : MEMORY_ENTRIES))
  )
  vi.mocked(getDitingProfile).mockResolvedValue(profileData())
  vi.mocked(editDitingMemory).mockResolvedValue({ success: true })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('diting memory panel', () => {
  it('renders both stores, the diting extensions and the CLI hints', async () => {
    seed()
    render(<DitingMemoryPanel />)

    const memoryCard = await screen.findByTestId('diting-memory-card')
    const userCard = screen.getByTestId('diting-user-card')
    expect(within(memoryCard).getByText('Repo lives at Desktop/diting-agent')).toBeTruthy()
    expect(within(userCard).getByText('Prefers simplified Chinese')).toBeTruthy()

    const extra = screen.getByTestId('diting-extra-card')
    expect(within(extra).getByText('量子计算 · 3.2')).toBeTruthy()
    expect(within(extra).getByText('browse_history · not granted')).toBeTruthy()
    expect(within(extra).getByText('[t1] 写周报（1 open）')).toBeTruthy()

    // 命令提示全部放上去：面板里能直接看到等效 CLI 命令
    expect(screen.getByText('hermes diting profile')).toBeTruthy()
    expect(screen.getByText('hermes diting help')).toBeTruthy()
  })

  it('adds an entry through the memory card', async () => {
    seed()
    render(<DitingMemoryPanel />)
    const memoryCard = await screen.findByTestId('diting-memory-card')

    const input = within(memoryCard).getByPlaceholderText('Add an entry…')
    fireEvent.change(input, { target: { value: 'New fact' } })
    fireEvent.click(within(memoryCard).getByText('Add'))

    await waitFor(() =>
      expect(editDitingMemory).toHaveBeenCalledWith(
        { action: 'add', target: 'memory', content: 'New fact' },
        undefined
      )
    )
  })

  it('removes an entry with the full entry text as the locator', async () => {
    seed()
    render(<DitingMemoryPanel />)
    const memoryCard = await screen.findByTestId('diting-memory-card')

    const row = within(memoryCard).getByText('Second note').closest('li')!
    fireEvent.click(within(row as HTMLElement).getByLabelText('Delete'))

    await waitFor(() =>
      expect(editDitingMemory).toHaveBeenCalledWith(
        { action: 'remove', target: 'memory', old_text: 'Second note' },
        undefined
      )
    )
  })

  it('edits an entry via whole-entry replace', async () => {
    seed()
    render(<DitingMemoryPanel />)
    const userCard = await screen.findByTestId('diting-user-card')

    const row = within(userCard).getByText('Prefers simplified Chinese').closest('li')!
    fireEvent.click(within(row as HTMLElement).getByLabelText('Edit'))
    const textarea = await within(userCard).findByDisplayValue('Prefers simplified Chinese')
    fireEvent.change(textarea, { target: { value: 'Prefers Chinese, keeps English terms' } })
    fireEvent.click(within(userCard).getByText('Save'))

    await waitFor(() =>
      expect(editDitingMemory).toHaveBeenCalledWith(
        {
          action: 'replace',
          target: 'user',
          content: 'Prefers Chinese, keeps English terms',
          old_text: 'Prefers simplified Chinese'
        },
        undefined
      )
    )
  })

  it('surfaces a failed edit as an error, not a silent no-op', async () => {
    seed()
    vi.mocked(editDitingMemory).mockResolvedValue({ success: false, error: 'No entry matched' })
    render(<DitingMemoryPanel />)
    const memoryCard = await screen.findByTestId('diting-memory-card')

    const input = within(memoryCard).getByPlaceholderText('Add an entry…')
    fireEvent.change(input, { target: { value: 'whatever' } })
    fireEvent.click(within(memoryCard).getByText('Add'))

    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('No entry matched')).toBeTruthy()
  })
})
