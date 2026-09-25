<template>
  <section class="page" data-module="dewater">
    <header class="page-head">
      <div>
        <h2>脱水运行管理</h2>
        <p class="page-desc">维护脱水记录，围绕记录编号、脱水机编号、进泥量、出泥含水率做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记脱水记录</button>
        <button class="btn" type="button" @click="exportRows">导出脱水运行清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>脱水机编号</span>
        <input v-model="machine" placeholder="按脱水机编号检索" />
      </label>
      <label class="filter-item">
        <span>运行状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <section class="panel">
      <h3>脱水机运行时序与故障停机统计</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in machineColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in machineStats" :key="text(item['脱水机编号'])">
            <td v-for="column in machineColumns" :key="column">{{ text(item[column]) }}</td>
          </tr>
          <tr v-if="!machineStats.length">
            <td :colspan="machineColumns.length" class="empty-state">当前筛选条件下没有脱水机统计数据，可调整筛选条件后重试</td>
          </tr>
        </tbody>
      </table>
      <ul v-if="machineNotes.length" class="note-list">
        <li v-for="note in machineNotes" :key="note">{{ note }}</li>
      </ul>
    </section>

    <section class="panel">
      <h3>异常记录定位（按时序排列）</h3>
      <div class="anomaly-filter">
        <label v-for="kind in anomalyKindOptions" :key="kind" class="anomaly-kind">
          <input v-model="anomalyKinds" type="checkbox" :value="kind" @change="persistView" />
          <span>{{ kind }}</span>
        </label>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in anomalyColumns" :key="column">{{ column }}</th>
            <th>定位</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in anomalyRows" :key="text(row.id)">
            <td>{{ text(row['登记时间']) }}</td>
            <td>{{ text(row['记录编号']) }}</td>
            <td>{{ text(row['脱水机编号']) }}</td>
            <td>{{ text(row['进泥量']) }}</td>
            <td>{{ text(row['出泥含水率']) }}</td>
            <td>
              <span v-for="reason in reasonsOf(row)" :key="reason" class="tag">{{ reason }}</span>
            </td>
            <td>{{ text(row['运行状态']) }}</td>
            <td><button class="link" type="button" @click="locateRow(row)">定位到列表</button></td>
          </tr>
          <tr v-if="!anomalyRows.length">
            <td :colspan="anomalyColumns.length + 1" class="empty-state">{{ anomalyEmptyText }}</td>
          </tr>
        </tbody>
      </table>
      <ul v-if="anomalyNotes.length" class="note-list">
        <li v-for="note in anomalyNotes" :key="note">{{ note }}</li>
      </ul>
    </section>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="text(row.id)">
          <td v-for="column in columns" :key="column">{{ text(row[column]) }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">未查到符合条件的脱水记录，可调整筛选条件或先登记脱水记录</td>
        </tr>
      </tbody>
    </table>

    <div class="pager">
      <button class="btn" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <button class="btn" type="button" :disabled="page >= pageCount" @click="changePage(page + 1)">下一页</button>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条脱水运行记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useDewaterViewStore } from '@/stores/dewater'

type Row = Record<string, unknown>

const ENDPOINT = '/api/dewater'
const PAGE_SIZE = 10
const columns = ["记录编号", "脱水机编号", "进泥量", "出泥含水率", "絮凝剂用量", "运行时长", "操作人员", "运行状态"]
const actions = ["确认开机", "确认停机", "登记故障"]
const statuses = ["待开机", "运行中", "已停机", "故障停机"]
const machineColumns = ["脱水机编号", "记录数", "开机次数", "停机次数", "故障停机次数", "累计运行时长", "异常记录数", "当前状态", "最近登记时间"]
const anomalyColumns = ["登记时间", "记录编号", "脱水机编号", "进泥量", "出泥含水率", "异常原因", "运行状态"]
const anomalyKindOptions = ["进泥量异常", "出泥含水率偏高"]

const viewStore = useDewaterViewStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref(viewStore.keyword)
const machine = ref(viewStore.machine)
const status = ref(viewStore.status)
const page = ref(viewStore.page)
const anomalyKinds = ref<string[]>([...viewStore.anomalyKinds])
const machineStats = ref<Row[]>([])
const machineNotes = ref<string[]>([])
const anomalies = ref<Row[]>([])
const anomalyNotes = ref<string[]>([])
const summary = ref<Record<string, number | null>>({})

const stats = computed(() => [
  { label: '运行机组', value: summary.value['运行机组'] ?? 0 },
  { label: '累计运行时长(h)', value: summary.value['累计运行时长'] ?? 0 },
  { label: '故障停机(次)', value: summary.value['故障停机次数'] ?? 0 },
  { label: '异常记录(条)', value: summary.value['异常记录数'] ?? 0 },
  { label: '出泥含水率均值(%)', value: summary.value['出泥含水率均值'] ?? '—' },
])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const anomalyRows = computed(() => {
  if (!anomalyKinds.value.length) {
    return []
  }
  return anomalies.value.filter((row) => reasonsOf(row).some((reason) => anomalyKinds.value.includes(reason)))
})

const anomalyEmptyText = computed(() => {
  if (!anomalyKinds.value.length) {
    return '请至少勾选一种异常类型后再定位异常记录'
  }
  return '未查到进泥量异常或出泥含水率偏高的记录，可调整筛选条件后重试'
})

function text(value: unknown): string | number {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return typeof value === 'number' ? value : String(value)
}

function reasonsOf(row: Row): string[] {
  const reasons = row['异常原因']
  return Array.isArray(reasons) ? (reasons as string[]) : []
}

function persistView() {
  viewStore.keyword = keyword.value
  viewStore.machine = machine.value
  viewStore.status = status.value
  viewStore.page = page.value
  viewStore.anomalyKinds = [...anomalyKinds.value]
}

function buildQuery(): URLSearchParams {
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (machine.value.trim()) {
    params.set('machine', machine.value.trim())
  }
  if (status.value) {
    params.set('status', status.value)
  }
  return params
}

function applyFilters() {
  page.value = 1
  persistView()
  void reload()
}

function resetFilters() {
  keyword.value = ''
  machine.value = ''
  status.value = ''
  page.value = 1
  persistView()
  void reload()
}

function changePage(target: number) {
  page.value = Math.min(Math.max(target, 1), pageCount.value)
  persistView()
  void reload()
}

function locateRow(row: Row) {
  keyword.value = String(row['记录编号'] ?? '')
  page.value = 1
  persistView()
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
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
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const params = buildQuery()
  const listParams = new URLSearchParams(params)
  listParams.set('page', String(page.value))
  listParams.set('size', String(PAGE_SIZE))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  try {
    const [listResponse, statsResponse, anomalyResponse] = await Promise.all([
      request(`${ENDPOINT}?${listParams.toString()}`),
      request(`${ENDPOINT}/stats${suffix}`),
      request(`${ENDPOINT}/anomalies${suffix}`),
    ])
    if (!listResponse.ok || !statsResponse.ok || !anomalyResponse.ok) {
      throw new Error('脱水运行数据读取失败')
    }
    const listPayload = await listResponse.json()
    const statsPayload = await statsResponse.json()
    const anomalyPayload = await anomalyResponse.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    if (!rows.value.length && total.value > 0 && page.value > 1) {
      page.value = 1
      persistView()
      return reload()
    }
    machineStats.value = statsPayload.machines ?? []
    machineNotes.value = statsPayload.notes ?? []
    summary.value = statsPayload.summary ?? {}
    anomalies.value = anomalyPayload.items ?? []
    anomalyNotes.value = anomalyPayload.notes ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '脱水运行列表读取失败'
  }
}

onMounted(reload)
</script>
