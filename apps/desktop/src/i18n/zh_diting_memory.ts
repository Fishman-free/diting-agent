import type { DitingMemoryTranslations } from './types_diting_memory'

// 设置 > 记忆与上下文：谛听画像与长程记忆面板。
export const zhDitingMemory: DitingMemoryTranslations = {
  panelTitle: '谛听画像与长程记忆',
  panelDesc: '查看并修改谛听记住的用户画像（USER.md）与长程记忆（MEMORY.md）。改动即时落盘，随每次会话加载。',
  memoryCard: '长程记忆 · MEMORY.md',
  profileCard: '用户画像 · USER.md',
  usage: (count, limit) => `${count} / ${limit} 字符`,
  empty: '暂无条目。',
  addPlaceholder: '新增一条…',
  add: '添加',
  edit: '编辑',
  delete: '删除',
  save: '保存',
  cancel: '取消',
  editHint: '保存将整条替换原条目。',
  failedTitle: '修改失败',
  disabledNote: '该层已在配置中停用——条目只读。',
  ditingCard: '谛听扩展画像',
  interests: '兴趣信号（授权制浏览画像）',
  interestsEmpty: '暂无兴趣信号。',
  consent: '授权状态',
  consentGranted: '已授权',
  consentDenied: '未授权',
  longtask: '进行中长任务',
  longtaskEmpty: '暂无进行中的长任务。',
  kernelUnavailable: '谛听内核暂不可用——内置画像条目不受影响。',
  cliTitle: '等效命令',
  cliNote: '同一份数据也可以在终端里查看和修改：'
}
