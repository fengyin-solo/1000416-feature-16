<template>
  <section class="page dewater-page" data-module="dewater">
    <header class="page-head">
      <div>
        <h2>脱水运行管理</h2>
        <p class="page-desc">维护脱水记录，并按脱水机编号查看运行时序、故障停机与进泥量、出泥含水率异常定位。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记脱水记录</button>
        <button class="btn" type="button" @click="exportRows">导出脱水运行清单</button>
      </div>
    </header>

    <div v-if="statsData" class="stat-row stats-grid">
      <button v-for="item in statCards" :key="item.label" class="stat-card stat-button" type="button" @click="quickFilter(item.abnormal)">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="submitQuery">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="filters.keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>脱水机编号</span>
        <input v-model="filters.machine" placeholder="按脱水机编号检索" />
      </label>
      <label class="filter-item">
        <span>运行状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>异常类型</span>
        <select v-model="filters.abnormal">
          <option value="">全部记录</option>
          <option v-for="option in abnormalOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>开始时间</span>
        <input v-model="filters.start_time" type="datetime-local" />
      </label>
      <label class="filter-item">
        <span>结束时间</span>
        <input v-model="filters.end_time" type="datetime-local" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :id="`dewater-row-${row.id}`" :key="String(row.id)" :class="{ 'focus-row': Number(focusId) === Number(row.id) }">
          <td
            v-for="column in columns"
            :key="column"
            :class="{
              'abnormal-cell': column === '进泥量' && isFeedAbnormal(row),
              'warning-cell': column === '出泥含水率' && isMoistureAbnormal(row),
              'empty-cell': column === '运行时间' && !row[column],
            }"
          >
            {{ column === '进泥量' && isFeedAbnormal(row) ? `${row[column] ?? '—'}（异常）` :
               column === '出泥含水率' && isMoistureAbnormal(row) ? `${row[column] ?? '—'}（偏高）` :
               row[column] || '—' }}
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyMessage }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot list-foot">
      <span>共 {{ total }} 条脱水运行记录，第 {{ page }} / {{ totalPages }} 页</span>
      <div class="pager">
        <button class="btn pager-btn" type="button" :disabled="page <= 1" @click="goPage(1)">首页</button>
        <button class="btn pager-btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn pager-btn" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
        <button class="btn pager-btn" type="button" :disabled="page >= totalPages" @click="goPage(totalPages)">末页</button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="timeline-panel">
      <div class="timeline-head">
        <div>
          <h3>按脱水机编号的运行时序与故障停机统计</h3>
          <p v-if="statsData" class="page-desc">
            异常口径：进泥量低于 {{ statsData.thresholds['进泥量下限'] }} 或高于 {{ statsData.thresholds['进泥量上限'] }} m³/h；
            出泥含水率高于 {{ statsData.thresholds['出泥含水率上限'] }}%。统计与列表使用同一筛选条件。
          </p>
        </div>
        <button class="btn ghost" type="button" @click="loadAll(true)">刷新时序</button>
      </div>

      <div v-if="timelineNotes.length" class="note-list">
        <p v-for="note in timelineNotes" :key="note" class="note-item">{{ note }}</p>
      </div>

      <div v-if="machineGroups.length" class="machine-list">
        <article v-for="group in machineGroups" :key="group['脱水机编号']" class="machine-card">
          <header class="machine-head">
            <div>
              <h4>{{ group['脱水机编号'] }}</h4>
              <span>最近故障时间：{{ group['最近故障时间'] || '暂无故障停机' }}</span>
            </div>
            <div class="machine-badges">
              <span>记录 {{ group['记录数'] }}</span>
              <span>运行中 {{ group['运行中'] }}</span>
              <span>已停机 {{ group['已停机'] }}</span>
              <span class="fault-badge">故障停机 {{ group['故障停机'] }}</span>
              <span>进泥量异常 {{ group['进泥量异常'] }}</span>
              <span>含水率偏高 {{ group['出泥含水率偏高'] }}</span>
              <span>时间为空 {{ group['时间为空记录'] }}</span>
            </div>
          </header>

          <div v-if="group.warnings.length" class="warning-list">
            <strong v-for="warning in group.warnings" :key="warning">{{ warning }}，已按时序标出，请核对记录。</strong>
          </div>

          <table class="data-table event-table">
            <thead>
              <tr>
                <th>运行时间</th>
                <th>记录编号</th>
                <th>动作</th>
                <th>当前状态</th>
                <th>异常类型</th>
                <th>定位</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="event in group.events" :key="`${event.id}-${event['运行时间']}-${event.动作}`">
                <td :class="{ 'empty-cell': event['运行时间'] === '时间为空' }">{{ event['运行时间'] }}</td>
                <td>{{ event['记录编号'] }}</td>
                <td>
                  {{ event.动作 }}
                  <span v-if="event.note" class="duplicate-tag">{{ event.note }}</span>
                </td>
                <td>{{ event['状态'] }}</td>
                <td :class="{ 'warning-cell': event['异常类型'] }">{{ event['异常类型'] || '正常' }}</td>
                <td>
                  <button class="link" type="button" @click="locateEvent(event)">定位记录</button>
                </td>
              </tr>
            </tbody>
          </table>
        </article>
      </div>
      <div v-else class="empty-state timeline-empty">当前筛选条件下暂无可展示的脱水机时序。</div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Filters = {
  keyword: string
  machine: string
  status: string
  abnormal: string
  start_time: string
  end_time: string
}
type TimelineEvent = {
  id: number | string
  记录编号: string
  动作: string
  运行时间: string
  状态: string
  异常类型: string
  page: number
  note?: string
}
type MachineGroup = {
  脱水机编号: string
  记录数: number
  运行中: number
  已停机: number
  故障停机: number
  进泥量异常: number
  出泥含水率偏高: number
  时间为空记录: number
  运行时长合计: number
  最近故障时间: string
  warnings: string[]
  events: TimelineEvent[]
}
type StatsData = {
  summary: Record<string, number>
  groups: MachineGroup[]
  notes: string[]
  thresholds: Record<string, number>
}

const ENDPOINT = '/api/dewater'
const PAGE_SIZE = 20
const columns = ['记录编号', '脱水机编号', '运行时间', '进泥量', '出泥含水率', '絮凝剂用量', '运行时长', '操作人员', '运行状态', '异常类型']
const actions = ['确认开机', '确认停机', '登记故障']
const statuses = ['待开机', '运行中', '已停机', '故障停机']
const abnormalOptions = [
  { value: 'abnormal', label: '全部异常' },
  { value: 'feed', label: '进泥量异常' },
  { value: 'moisture', label: '出泥含水率偏高' },
]

const router = useRouter()
const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const focusId = ref<number | string | null>(null)
const errorMessage = ref('')
const statsData = ref<StatsData | null>(null)
const filters = reactive<Filters>({
  keyword: '',
  machine: '',
  status: '',
  abnormal: '',
  start_time: '',
  end_time: '',
})

const totalPages = computed(() => Math.max(Math.ceil(total.value / PAGE_SIZE), 1))
const machineGroups = computed(() => statsData.value?.groups ?? [])
const timelineNotes = computed(() => statsData.value?.notes ?? [])
const emptyMessage = computed(() => {
  if (rows.value.length === 0 && total.value > 0) {
    return `第 ${page.value} 页没有记录，请翻到第 ${totalPages.value} 页；筛选条件仍已保持`
  }
  const hasFilter = Object.values(filters).some(Boolean)
  return hasFilter ? '筛选无结果，请调整记录编号、脱水机编号、状态、异常类型或时间范围后重试' : '暂无脱水运行数据，可先登记脱水记录'
})
const statCards = computed(() => {
  const summary = statsData.value?.summary ?? {}
  return [
    { label: '脱水机数', value: summary['脱水机数'] ?? 0, abnormal: '' },
    { label: '记录数', value: summary['记录数'] ?? 0, abnormal: '' },
    { label: '故障停机', value: summary['故障停机'] ?? 0, abnormal: '' },
    { label: '故障率', value: `${summary['故障率'] ?? 0}%`, abnormal: '' },
    { label: '进泥量异常', value: summary['进泥量异常'] ?? 0, abnormal: 'feed' },
    { label: '出泥含水率偏高', value: summary['出泥含水率偏高'] ?? 0, abnormal: 'moisture' },
    { label: '时间为空记录', value: summary['时间为空记录'] ?? 0, abnormal: '' },
    { label: '运行时长合计(h)', value: summary['运行时长合计'] ?? 0, abnormal: '' },
  ]
})

function queryValue(name: string, search = window.location.search): string {
  const params = new URLSearchParams(search)
  const value = params.get(name)
  return value ?? ''
}

function hydrateFiltersFromUrl() {
  filters.keyword = queryValue('keyword')
  filters.machine = queryValue('machine')
  filters.status = queryValue('status')
  filters.abnormal = queryValue('abnormal')
  filters.start_time = queryValue('start_time')
  filters.end_time = queryValue('end_time')
  page.value = Math.max(Number.parseInt(queryValue('page'), 10) || 1, 1)
}

function appendFilterParams(params: URLSearchParams, includePage = false) {
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.machine) params.set('machine', filters.machine)
  if (filters.status) params.set('status', filters.status)
  if (filters.abnormal) params.set('abnormal', filters.abnormal)
  if (filters.start_time) params.set('start_time', filters.start_time)
  if (filters.end_time) params.set('end_time', filters.end_time)
  if (includePage) {
    params.set('page', String(page.value))
    params.set('size', String(PAGE_SIZE))
  }
}

function syncUrl(historyMode: 'push' | 'replace' = 'replace') {
  const params = new URLSearchParams()
  appendFilterParams(params, true)
  void router[historyMode]({ query: Object.fromEntries(params.entries()) })
}

function buildUrl(path: string, includePage = false, withPageSize = false) {
  const params = new URLSearchParams()
  appendFilterParams(params, includePage)
  if (withPageSize) params.set('page_size', String(PAGE_SIZE))
  const query = params.toString()
  return `${path}${query ? `?${query}` : ''}`
}

async function loadList() {
  const response = await request(buildUrl(ENDPOINT, true))
  if (!response.ok) {
    throw new Error('脱水记录列表读取失败')
  }
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadStatistics() {
  const response = await request(buildUrl(`${ENDPOINT}/statistics`, false, true))
  if (!response.ok) {
    throw new Error('脱水机时序统计读取失败')
  }
  statsData.value = await response.json()
}

async function loadAll(showError = true) {
  errorMessage.value = ''
  const results = await Promise.allSettled([loadList(), loadStatistics()])
  const failed = results.find((result) => result.status === 'rejected')
  if (failed && showError && failed.status === 'rejected') {
    errorMessage.value = failed.reason instanceof Error ? failed.reason.message : '脱水运行数据读取失败'
  }
}

function submitQuery() {
  page.value = 1
  focusId.value = null
  syncUrl()
  void loadAll()
}

function resetFilters() {
  Object.keys(filters).forEach((key) => {
    filters[key as keyof Filters] = ''
  })
  page.value = 1
  focusId.value = null
  syncUrl()
  void loadAll()
}

function goPage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return
  page.value = nextPage
  focusId.value = null
  syncUrl('push')
  void loadAll()
}

function quickFilter(abnormal: string) {
  if (!abnormal) return
  filters.abnormal = abnormal
  submitQuery()
}

function exportRows() {
  window.open(buildUrl(`${ENDPOINT}/export`), '_blank')
}

function openCreate() {
  errorMessage.value = '脱水记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('脱水运行动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (payload.ok === false) {
      throw new Error(payload.message || '脱水运行动作未生效，请稍后重试')
    }
    await loadAll(false)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行操作失败'
  }
}

async function scrollToFocus(id: number | string) {
  await nextTick()
  document.getElementById(`dewater-row-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function locateEvent(event: TimelineEvent) {
  errorMessage.value = ''
  focusId.value = event.id
  page.value = event.page
  syncUrl('push')
  try {
    await loadList()
    await scrollToFocus(event.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '记录定位失败，请检查当前筛选条件'
  }
}

function numericValue(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const match = String(value).replace(/,/g, '').match(/-?\d+(?:\.\d+)?/)
  return match ? Number.parseFloat(match[0]) : null
}

function isFeedAbnormal(row: Row) {
  const value = numericValue(row['进泥量'] as string | number | null)
  const min = statsData.value?.thresholds['进泥量下限'] ?? 10
  const max = statsData.value?.thresholds['进泥量上限'] ?? 80
  return value !== null && (value < min || value > max)
}

function isMoistureAbnormal(row: Row) {
  const rawValue = numericValue(row['出泥含水率'] as string | number | null)
  if (rawValue === null) return false
  const limit = statsData.value?.thresholds['出泥含水率上限'] ?? 80
  const value = rawValue <= 1 ? rawValue * 100 : rawValue
  return value > limit
}

function handleBrowserNavigation() {
  hydrateFiltersFromUrl()
  focusId.value = null
  void loadAll()
}

onMounted(() => {
  hydrateFiltersFromUrl()
  void loadAll()
  window.addEventListener('popstate', handleBrowserNavigation)
})

onUnmounted(() => {
  window.removeEventListener('popstate', handleBrowserNavigation)
})
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 10px;
}

.stat-button {
  text-align: left;
  font: inherit;
}

.stat-button:hover {
  border-color: var(--brand);
  box-shadow: 0 2px 8px rgb(31 111 235 / 12%);
}

.filter-item select,
.filter-item input {
  min-width: 150px;
}

.abnormal-cell {
  color: #b42318;
  font-weight: 600;
}

.warning-cell {
  color: #b54708;
  font-weight: 600;
}

.empty-cell {
  color: #b42318;
}

.focus-row {
  background: #fff7d6;
}

.focus-row td {
  box-shadow: inset 0 0 0 2px #eaaa00;
}

.list-foot {
  align-items: center;
}

.pager {
  display: flex;
  gap: 6px;
}

.pager-btn {
  padding: 4px 8px;
}

.pager-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.timeline-panel {
  margin-top: 18px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.timeline-head h3,
.machine-head h4 {
  margin: 0 0 4px;
}

.note-list {
  margin: 10px 0;
  display: grid;
  gap: 6px;
}

.note-item {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid #fedf89;
  background: #fffaeb;
  border-radius: 6px;
  color: #93370d;
  font-size: 13px;
}

.machine-list {
  display: grid;
  gap: 14px;
}

.machine-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}

.machine-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.machine-head span {
  color: var(--muted);
  font-size: 12px;
}

.machine-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.machine-badges span {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  background: #f8fafc;
}

.machine-badges .fault-badge {
  border-color: #fecdca;
  background: #fff1f0;
  color: #b42318;
}

.warning-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.warning-list strong {
  color: #b42318;
  background: #fff1f0;
  border: 1px solid #fecdca;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 600;
}

.event-table {
  margin-top: 8px;
}

.duplicate-tag {
  display: inline-block;
  margin-left: 6px;
  color: #b42318;
  font-size: 12px;
}

.timeline-empty {
  padding: 18px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
}

@media (max-width: 1280px) {
  .stats-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
