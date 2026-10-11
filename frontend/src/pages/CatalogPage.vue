<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { catalog } from '../api/client'
const knowledge = ref<Array<{id: string; name: string; type: string; status: string}>>([])
const tools = ref<Array<{name: string; type: string; status: string}>>([])
const error = ref('')
const loading = ref(true)
function statusLabel(status: string): string {
  if (status === 'available') return '当前可用'
  if (status === 'unavailable') return '暂不可用'
  return `状态：${status}`
}
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await catalog()
    knowledge.value = result.knowledge
    tools.value = result.tools
  } catch (caught) {
    error.value = String(caught instanceof Error ? caught.message : caught)
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<template>
  <div class="page-head">
    <div><span class="eyebrow">LOCAL DEMO CAPABILITIES</span><h1>知识源与工具</h1><p>这里列出 Agent 在本地演示中能查到的资料，以及可以尝试的只读工具。</p></div>
    <span class="badge"><span class="badge-dot" aria-hidden="true"></span>本地演示 · MOCK</span>
  </div>
  <div class="notice"><strong>范围说明</strong><span>以下内容由项目提供的合成样例组成，不连接真实 RAG 知识库、账户系统或外部 API。</span></div>
  <div v-if="error" class="alert" role="alert">无法读取演示能力：{{ error }} <button class="secondary" :disabled="loading" @click="load">重新加载</button></div>
  <div v-if="loading" class="card load-state" role="status" aria-live="polite">正在读取演示资料和工具…</div>
  <div v-else-if="!error" class="metrics">
    <section class="card">
      <small>本地固定内容</small><h2>知识资料</h2>
      <p class="catalog-intro">产品问题会检索这些演示资料；没有匹配内容时，Agent 会说明缺少依据。</p>
      <p v-if="!knowledge.length" class="empty">当前没有可用的演示资料。</p>
      <div v-for="source in knowledge" :key="source.id" class="result"><strong>{{ source.name }}</strong><p>{{ source.id }} · {{ source.type === 'mock_fixture' ? '本地合成资料' : source.type }} · {{ statusLabel(source.status) }}</p></div>
    </section>
    <section class="card">
      <small>服务端权限校验</small><h2>只读工具</h2>
      <p class="catalog-intro">调用前会检查当前合成身份是否有权访问目标账户；拒绝后不会执行工具。</p>
      <p v-if="!tools.length" class="empty">当前没有可用的演示工具。</p>
      <div v-for="tool in tools" :key="tool.name" class="result"><strong>{{ tool.name === 'read_account_usage' ? '查询账户用量' : tool.name }}</strong><p>{{ tool.type === 'mock_read_only' ? '本地只读 Mock · 不修改任何数据' : tool.type }} · {{ statusLabel(tool.status) }}</p></div>
    </section>
  </div>
</template>
