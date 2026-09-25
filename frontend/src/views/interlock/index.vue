<template>
  <section class="page" data-module="interlock">
    <header class="page-head">
      <div>
        <h2>联锁设备管理</h2>
        <p class="page-desc">维护联锁设备，围绕设备编号、联锁类型、控制范围、软件版本做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <label class="account-switch">
          <span>当前账号</span>
          <select :value="store.operator" @change="onSwitchAccount">
            <option v-for="account in store.accounts" :key="account.name" :value="account.name">
              {{ account.name }}（{{ account.station }}）
            </option>
          </select>
        </label>
        <button class="btn primary" type="button" @click="openCreate">登记联锁设备</button>
        <button class="btn" type="button" @click="exportRows">导出联锁设备清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-if="canOperateRow(row)">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="openVersion(row)">版本变更</button>
            </template>
            <span v-else class="readonly-hint">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无联锁设备数据，可先登记联锁设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条联锁设备记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detailRow" class="modal-mask" @click.self="closeModals">
      <div class="modal-card">
        <h3>联锁设备详情 · {{ detailRow['设备编号'] }}</h3>
        <dl class="detail-list">
          <template v-for="field in columns" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailRow[field] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeModals">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-mask" @click.self="closeModals">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记联锁设备</h3>
        <label v-for="field in createFields" :key="field" class="form-row">
          <span>{{ field }}</span>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </label>
        <label class="form-row">
          <span>所属车站</span>
          <input :value="store.station" disabled />
        </label>
        <label class="form-row">
          <span>责任人</span>
          <select v-model="createForm['责任人']">
            <option v-for="account in stationAccounts" :key="account.name" :value="account.name">
              {{ account.name }}
            </option>
          </select>
        </label>
        <p class="modal-hint">只能登记本站（{{ store.station }}）的设备；控制范围全网唯一，一段范围只能由一个车站认领。</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">提交登记</button>
          <button class="btn ghost" type="button" @click="closeModals">取消</button>
        </div>
      </form>
    </div>

    <div v-if="versionRow" class="modal-mask" @click.self="closeModals">
      <form class="modal-card" @submit.prevent="submitVersion">
        <h3>软件版本变更 · {{ versionRow['设备编号'] }}</h3>
        <label v-for="field in versionFields" :key="field" class="form-row">
          <span>{{ field }}</span>
          <input v-if="field !== '责任人'" v-model="versionForm[field]" :placeholder="`请输入${field}`" />
          <select v-else v-model="versionForm['责任人']">
            <option v-for="account in stationAccounts" :key="account.name" :value="account.name">
              {{ account.name }}
            </option>
          </select>
        </label>
        <p class="modal-hint">版本变更会同时更新控制范围与责任人；控制范围不能与其他车站重复认领。</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">提交变更</button>
          <button class="btn ghost" type="button" @click="closeModals">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore, type Account } from '@/stores/session'

type Row = Record<string, string | number | null>
type ActionReply = { ok: boolean; message: string }

const ENDPOINT = '/api/interlock'
const columns = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人", "设备状态"]
const actions = ["确认检修", "降级登记", "停用设备"]
const createFields = ["设备编号", "联锁类型", "控制范围", "软件版本", "上次检修日"]
const versionFields = ["软件版本", "控制范围", "责任人"]

const store = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref([{ label: '在运联锁', value: 0 }, { label: '降级使用设备', value: 0 }, { label: '待检修设备', value: 0 }])

const detailRow = ref<Row | null>(null)
const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const versionRow = ref<Row | null>(null)
const versionForm = ref<Record<string, string>>({})

const stationAccounts = computed(() => store.accounts.filter((account) => account.station === store.station))

function canOperateRow(row: Row) {
  return row['所属车站'] === store.station || row['责任人'] === store.operator
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function onSwitchAccount(event: Event) {
  store.switchAccount((event.target as HTMLSelectElement).value)
}

function closeModals() {
  detailRow.value = null
  createVisible.value = false
  versionRow.value = null
}

function openCreate() {
  createForm.value = { '责任人': store.operator }
  createVisible.value = true
}

function openVersion(row: Row) {
  versionForm.value = {
    '软件版本': String(row['软件版本'] ?? ''),
    '控制范围': String(row['控制范围'] ?? ''),
    '责任人': String(row['责任人'] ?? ''),
  }
  versionRow.value = row
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('联锁设备详情读取失败')
    }
    detailRow.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备详情读取失败'
  }
}

async function postJson(path: string, values: Record<string, unknown>): Promise<ActionReply> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values, operator: store.operator }),
  })
  return (await response.json()) as ActionReply
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const reply = await postJson(`${ENDPOINT}/${row.id}/actions`, { action })
    if (!reply.ok) {
      errorMessage.value = reply.message || '联锁设备动作未生效'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备操作失败'
  }
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const reply = await postJson(ENDPOINT, { ...createForm.value, '所属车站': store.station })
    if (!reply.ok) {
      errorMessage.value = reply.message || '联锁设备登记未生效'
      return
    }
    closeModals()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备登记失败'
  }
}

async function submitVersion() {
  errorMessage.value = ''
  if (!versionRow.value) {
    return
  }
  try {
    const reply = await postJson(`${ENDPOINT}/${versionRow.value.id}/version`, { ...versionForm.value })
    if (!reply.ok) {
      errorMessage.value = reply.message || '软件版本变更未生效'
      return
    }
    closeModals()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '软件版本变更失败'
  }
}

function refreshStats() {
  const count = (status: string) => rows.value.filter((row) => row['设备状态'] === status).length
  stats.value = [
    { label: '在运联锁', value: count('运用正常') },
    { label: '降级使用设备', value: count('降级使用') },
    { label: '待检修设备', value: count('待检修') },
  ]
}

async function loadAccounts() {
  try {
    const response = await request(`${ENDPOINT}/operators`)
    if (!response.ok) {
      return
    }
    const payload = (await response.json()) as { items?: Account[] }
    const items = Array.isArray(payload.items) ? payload.items : []
    if (items.length) {
      store.setAccounts(items)
      if (!items.some((item) => item.name === store.operator)) {
        store.switchAccount(items[0].name)
      }
    }
  } catch {
    // 名录拉不到时沿用本地默认账号
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('联锁设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    refreshStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备列表读取失败'
  }
}

onMounted(async () => {
  await loadAccounts()
  await reload()
})
</script>
