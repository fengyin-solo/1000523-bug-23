<template>
  <section class="page" data-module="interlock-owners">
    <header class="page-head">
      <div>
        <h2>联锁设备归属（责任人总览）</h2>
        <p class="page-desc">
          按所属车站与责任人汇总联锁设备，数据与设备列表、设备详情来自同一份后端记录。
          每段控制范围只允许一个车站认领，归属不一致时以本页与列表对比即可发现。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/interlock">返回联锁设备列表</RouterLink>
      </div>
    </header>

    <table class="data-table">
      <thead>
        <tr>
          <th>所属车站</th>
          <th>责任人</th>
          <th>设备总数</th>
          <th>运用正常</th>
          <th>降级使用</th>
          <th>待检修</th>
          <th>已停用</th>
          <th>认领的控制范围</th>
          <th>设备编号</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="group in groups" :key="`${group['所属车站']}|${group['责任人']}`">
          <td>{{ group['所属车站'] }}</td>
          <td>{{ group['责任人'] }}</td>
          <td>{{ group['设备总数'] }}</td>
          <td>{{ group['运用正常'] }}</td>
          <td>{{ group['降级使用'] }}</td>
          <td>{{ group['待检修'] }}</td>
          <td>{{ group['已停用'] }}</td>
          <td>
            <span v-for="scope in group['控制范围']" :key="String(scope)" class="scope-tag">{{ scope }}</span>
          </td>
          <td>
            <RouterLink
              v-for="code in group['设备编号']"
              :key="String(code)"
              class="link device-link"
              to="/interlock"
            >
              {{ code }}
            </RouterLink>
          </td>
        </tr>
        <tr v-if="!groups.length">
          <td colspan="9" class="empty-state">暂无归属数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ groups.length }} 个车站/责任人归属组</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type OwnerGroup = {
  所属车站: string
  责任人: string
  设备总数: number
  运用正常: number
  降级使用: number
  待检修: number
  已停用: number
  设备编号: (string | number)[]
  控制范围: (string | number)[]
}

const groups = ref<OwnerGroup[]>([])
const errorMessage = ref('')

onMounted(async () => {
  errorMessage.value = ''
  try {
    const response = await request('/api/interlock/owners')
    if (!response.ok) {
      throw new Error('责任人归属数据读取失败')
    }
    const payload = await response.json() as { items?: OwnerGroup[] }
    groups.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '责任人归属数据读取失败'
  }
})
</script>

<style scoped>
.scope-tag {
  display: inline-block;
  margin: 2px 4px 2px 0;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 12px;
  background: #f1f5f9;
}
.device-link {
  margin-right: 8px;
  white-space: nowrap;
}
</style>
