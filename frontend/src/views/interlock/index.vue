<template>
  <section class="page" data-module="interlock">
    <header class="page-head">
      <div>
        <h2>联锁设备管理</h2>
        <p class="page-desc">
          维护联锁设备的登记、筛选与状态流转。设备按「所属车站 + 责任人」归属，
          非归属账号只读；当前账号：<strong>{{ store.station }} · {{ store.operator }}</strong>
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记联锁设备</button>
        <button class="btn" type="button" @click="exportRows">导出联锁设备清单</button>
        <RouterLink class="btn ghost" to="/interlock/owners">责任人归属总览</RouterLink>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
      </label>
      <label class="filter-item">
        <span>设备状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>归属</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <a v-if="column === '设备编号'" class="link" @click="openDetail(row)">{{ row[column] ?? '—' }}</a>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>
            <span :class="['badge', store.owns(row) ? 'badge-ok' : 'badge-readonly']">
              {{ store.owns(row) ? '本站责任人' : '只读' }}
            </span>
          </td>
          <td class="row-actions">
            <template v-if="store.owns(row)">
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
            <span v-else class="readonly-tip">非所属车站/责任人，仅可查看</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无联锁设备数据，可先登记联锁设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条联锁设备记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 设备详情抽屉：与列表共用同一接口数据，额外展示操作履历 -->
    <div v-if="detail" class="drawer-mask" @click.self="detail = null">
      <aside class="drawer">
        <header class="drawer-head">
          <h3>联锁设备详情 · {{ detail['设备编号'] }}</h3>
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="column in detailColumns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </template>
          <dt>当前归属</dt>
          <dd>{{ detail['所属车站'] }} · {{ detail['责任人'] }}</dd>
        </dl>
        <h4 class="log-title">操作履历（按实际操作人留痕）</h4>
        <table class="data-table">
          <thead>
            <tr><th>时间</th><th>动作</th><th>目标状态</th><th>操作人</th><th>操作车站</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(log, index) in detailLogs" :key="index">
              <td>{{ log['时间'] }}</td>
              <td>{{ log['动作'] }}</td>
              <td>{{ log['目标状态'] }}</td>
              <td>{{ log['操作人'] }}</td>
              <td>{{ log['操作车站'] }}</td>
              <td>{{ log['说明'] || '—' }}</td>
            </tr>
            <tr v-if="!detailLogs.length">
              <td colspan="6" class="empty-state">暂无操作履历</td>
            </tr>
          </tbody>
        </table>
      </aside>
    </div>

    <!-- 登记表单 -->
    <div v-if="createOpen" class="drawer-mask" @click.self="createOpen = false">
      <aside class="drawer drawer-form">
        <header class="drawer-head">
          <h3>登记联锁设备</h3>
          <button class="btn ghost" type="button" @click="createOpen = false">关闭</button>
        </header>
        <p class="form-hint">归属车站固定为当前账号所在车站 {{ store.station }}，责任人默认取当前账号。</p>
        <form @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field" class="form-item">
            <span>{{ field }}</span>
            <input v-model="createForm[field]" required />
          </label>
          <label class="form-item">
            <span>软件版本</span>
            <input v-model="createForm['软件版本']" placeholder="如 V2.3.1" />
          </label>
          <label class="form-item">
            <span>所属车站（归属）</span>
            <input :value="store.station" disabled />
          </label>
          <label class="form-item">
            <span>责任人（归属）</span>
            <input v-model="createForm['责任人']" required />
          </label>
          <p v-if="formError" class="error-text">{{ formError }}</p>
          <button class="btn primary" type="submit">提交登记</button>
        </form>
      </aside>
    </div>

    <!-- 版本变更表单：版本号、控制范围、责任人、所属车站必须一起提交 -->
    <div v-if="versionTarget" class="drawer-mask" @click.self="versionTarget = null">
      <aside class="drawer drawer-form">
        <header class="drawer-head">
          <h3>软件版本变更 · {{ versionTarget['设备编号'] }}</h3>
          <button class="btn ghost" type="button" @click="versionTarget = null">关闭</button>
        </header>
        <p class="form-hint">
          版本变更时控制范围与责任人需随版本一起核对更新；同一段控制范围只能由一个车站认领。
        </p>
        <form @submit.prevent="submitVersion">
          <label class="form-item">
            <span>软件版本（必填）</span>
            <input v-model="versionForm['软件版本']" required />
          </label>
          <label class="form-item">
            <span>控制范围（必填，全平台唯一）</span>
            <input v-model="versionForm['控制范围']" required />
          </label>
          <label class="form-item">
            <span>所属车站（必填）</span>
            <input v-model="versionForm['所属车站']" required />
          </label>
          <label class="form-item">
            <span>责任人（必填）</span>
            <input v-model="versionForm['责任人']" required />
          </label>
          <p v-if="formError" class="error-text">{{ formError }}</p>
          <button class="btn primary" type="submit">确认版本变更</button>
        </form>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
type LogEntry = Record<string, string>

const ENDPOINT = '/api/interlock'
const store = useSessionStore()

const columns = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人", "设备状态"]
const detailColumns = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人", "设备状态", "status"]
const actions = ["确认检修", "降级登记", "停用设备"]
const statuses = ["待检修", "运用正常", "降级使用", "已停用"]
// 列表、统计与筛选共用同一批数据，避免三个口径各算各的。
const statsSource = ref<Row[]>([])
const stats = computed(() => [
  { label: "在运联锁", value: statsSource.value.filter((row) => row.status === '运用正常').length },
  { label: "降级使用设备", value: statsSource.value.filter((row) => row.status === '降级使用').length },
  { label: "待检修设备", value: statsSource.value.filter((row) => row.status === '待检修').length },
  { label: "已停用设备", value: statsSource.value.filter((row) => row.status === '已停用').length },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = [
  { key: 'keyword', label: '设备编号' },
  { key: 'scope', label: '控制范围' },
  { key: 'station', label: '所属车站' },
  { key: 'owner', label: '责任人' },
]

const detail = ref<Row | null>(null)
const detailLogs = computed<LogEntry[]>(() => {
  const logs = detail.value?.['操作履历']
  return Array.isArray(logs) ? logs as LogEntry[] : []
})

const createOpen = ref(false)
const createFields = ["设备编号", "联锁类型", "控制范围"]
const createForm = ref<Record<string, string>>({ 设备编号: '', 联锁类型: '', 控制范围: '', 软件版本: '', 责任人: store.operator })
const versionTarget = ref<Row | null>(null)
const versionForm = ref<Record<string, string>>({ 软件版本: '', 控制范围: '', 所属车站: '', 责任人: '' })
const formError = ref('')

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  formError.value = ''
  createForm.value = {
    设备编号: '', 联锁类型: '', 控制范围: '', 软件版本: '',
    责任人: store.operator,
  }
  createOpen.value = true
}

function openVersion(row: Row) {
  formError.value = ''
  versionTarget.value = row
  versionForm.value = {
    软件版本: String(row['软件版本'] ?? ''),
    控制范围: String(row['控制范围'] ?? ''),
    所属车站: String(row['所属车站'] ?? ''),
    责任人: String(row['责任人'] ?? ''),
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('联锁设备详情读取失败')
    }
    detail.value = await response.json() as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备详情读取失败'
  }
}

async function postAction(path: string, body: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ ...body, station: store.station, operator: store.operator }),
  })
  if (!response.ok) {
    throw new Error('联锁设备操作未生效，请稍后重试')
  }
  const payload = await response.json() as { ok: boolean; message: string }
  // 业务拒绝（越权、范围重复、字段缺失）HTTP 仍是 200，原因在 message 里原样透传。
  return { ok: payload.ok, message: payload.message }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const result = await postAction(`${ENDPOINT}/${row.id}/actions`, { action })
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备操作失败'
  }
}

async function submitCreate() {
  formError.value = ''
  try {
    const result = await postAction(ENDPOINT, { values: { ...createForm.value } })
    if (!result.ok) {
      formError.value = result.message
      return
    }
    createOpen.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '联锁设备登记失败'
  }
}

async function submitVersion() {
  if (!versionTarget.value) return
  formError.value = ''
  try {
    const result = await postAction(`${ENDPOINT}/${versionTarget.value.id}/version`, {
      values: { ...versionForm.value },
    })
    if (!result.ok) {
      formError.value = result.message
      return
    }
    versionTarget.value = null
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '版本变更失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(
    Object.entries(filters.value).filter(([, value]) => value.trim().length > 0),
  ).toString()
  try {
    // 统计取全量（size 放大到一页），表格仍走分页；两者来自同一个接口口径。
    const [pageResponse, allResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?${query ? `${query}&` : ''}size=200`),
    ])
    if (!pageResponse.ok || !allResponse.ok) {
      throw new Error('联锁设备列表读取失败')
    }
    const payload = await pageResponse.json() as { items?: Row[]; total?: number }
    const allPayload = await allResponse.json() as { items?: Row[] }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    statsSource.value = allPayload.items ?? rows.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '联锁设备列表读取失败'
  }
}

onMounted(reload)
</script>
