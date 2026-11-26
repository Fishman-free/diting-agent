import type { DitingMemoryTranslations } from './types_diting_memory'

// Settings > Memory & Context: the Diting profile & long-term memory panel.
export const enDitingMemory: DitingMemoryTranslations = {
  panelTitle: 'Diting profile & long-term memory',
  panelDesc:
    'View and edit what Diting remembers about you (USER.md) and its own persistent notes (MEMORY.md). Changes save instantly and load into every session.',
  memoryCard: 'Long-term memory · MEMORY.md',
  profileCard: 'User profile · USER.md',
  usage: (count, limit) => `${count} / ${limit} chars`,
  empty: 'No entries yet.',
  addPlaceholder: 'Add an entry…',
  add: 'Add',
  edit: 'Edit',
  delete: 'Delete',
  save: 'Save',
  cancel: 'Cancel',
  editHint: 'Saving replaces the whole entry.',
  failedTitle: 'Edit failed',
  disabledNote: 'This layer is turned off in config — entries are read-only.',
  ditingCard: 'Diting extensions',
  interests: 'Interest signals (opt-in browse profile)',
  interestsEmpty: 'No interest signals yet.',
  consent: 'Consent',
  consentGranted: 'granted',
  consentDenied: 'not granted',
  longtask: 'Active long tasks',
  longtaskEmpty: 'No active long tasks.',
  kernelUnavailable: 'Diting kernel unavailable — built-in profile entries still work.',
  cliTitle: 'Command equivalents',
  cliNote: 'The same data is available from the terminal:'
}
