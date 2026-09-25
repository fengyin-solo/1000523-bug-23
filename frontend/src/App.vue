<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">轨道交通信号设备检修平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向轨道交通信号机、转辙机、轨道电路、联锁设备的检修计划、故障处置与验收的一体化检修管理后台。</span>
        <span class="head-user">
          当前值班：{{ store.operator }} · {{ store.shiftLabel }}
          <label class="account-switch">
            当前车站账号
            <select :value="store.accountKey" @change="switchAccount">
              <option v-for="account in store.accounts" :key="`${account.station}|${account.operator}`"
                :value="`${account.station}|${account.operator}`">
                {{ account.station }} · {{ account.operator }}
              </option>
            </select>
          </label>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

import { request } from '@/api/client'
import { useSessionStore, type StationAccount } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "线路区段", path: "/section" }, { label: "信号机", path: "/signal" }, { label: "转辙机", path: "/switch" }, { label: "轨道电路", path: "/track" }, { label: "联锁设备", path: "/interlock" }, { label: "联锁归属", path: "/interlock/owners" }, { label: "列车防护", path: "/atp" }, { label: "检修计划", path: "/plan" }, { label: "检修任务", path: "/task" }, { label: "故障登记", path: "/fault" }, { label: "故障处置", path: "/dispose" }, { label: "器材领用", path: "/spare" }, { label: "电气测试", path: "/measure" }, { label: "巡视检查", path: "/patrol" }, { label: "天窗作业", path: "/window" }, { label: "监测报警", path: "/alarm" }, { label: "验收确认", path: "/verify" }, { label: "值班交接", path: "/shift" }, { label: "状态评估", path: "/assess" }]

function switchAccount(event: Event) {
  const [station, operator] = (event.target as HTMLSelectElement).value.split('|')
  store.setAccount(station, operator)
}

onMounted(async () => {
  // 账号清单以后端为准；接口不可用时继续使用内置的只读账号，不阻塞页面。
  try {
    const response = await request('/api/interlock/accounts')
    if (response.ok) {
      const payload = await response.json() as { items?: StationAccount[] }
      if (payload.items?.length) {
        store.accounts = [{ station: '调度中心', operator: '值班管理员' }, ...payload.items]
      }
    }
  } catch {
    // 静默降级：头部切换器仍可用内置账号
  }
})
</script>

<style scoped>
.account-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 12px;
  font-size: 13px;
  color: var(--muted);
}
.account-switch select {
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
}
</style>
