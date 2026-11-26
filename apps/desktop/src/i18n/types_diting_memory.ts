// Settings > Memory & Context: 谛听画像与长程记忆面板
// (`Translations.settings.ditingMemory`). Entries mirror the built-in
// MEMORY.md / USER.md stores plus the Diting extensions (interest signals,
// consent, long tasks); CLI parity hints included.
export interface DitingMemoryTranslations {
  panelTitle: string
  panelDesc: string
  memoryCard: string
  profileCard: string
  usage: (count: string, limit: string) => string
  empty: string
  addPlaceholder: string
  add: string
  edit: string
  delete: string
  save: string
  cancel: string
  editHint: string
  failedTitle: string
  disabledNote: string
  ditingCard: string
  interests: string
  interestsEmpty: string
  consent: string
  consentGranted: string
  consentDenied: string
  longtask: string
  longtaskEmpty: string
  kernelUnavailable: string
  cliTitle: string
  cliNote: string
}
