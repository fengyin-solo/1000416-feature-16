import { defineStore } from 'pinia'

/** 脱水运行页的筛选与翻页状态：离开页面再返回时保持现场。 */
export const useDewaterViewStore = defineStore('dewaterView', {
  state: () => ({
    keyword: '',
    machine: '',
    status: '',
    page: 1,
    anomalyKinds: ['进泥量异常', '出泥含水率偏高'] as string[],
  }),
})
