<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { providerStatus } from '../api/client'
const providers = ref<Array<{name: string; status: string; mode: string}>>([])
const error = ref('')
const loading = ref(true)
function statusLabel(status: string): string {
  if (status === 'available') return '可用'
  if (status === 'not_connected') return '尚未接入'
  return `状态：${status}`
}
function modeLabel(mode: string): string {
  if (mode === 'mock') return 'Mock 演示模式'
  if (mode === 'live') return 'Live 服务模式'
  return `模式：${mode}`
}
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try { providers.value = (await providerStatus()).providers }
  catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) }
  finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <div class="page-head">
    <div><span class="eyebrow">SERVICE MODE</span><h1>模型与服务状态</h1><p>这里说明当前演示使用哪些服务，以及哪些真实服务还没有接入。</p></div>
    <span class="badge"><span class="badge-dot" aria-hidden="true"></span>本地演示 · MOCK</span>
  </div>
  <div v-if="error" class="alert" role="alert">无法读取服务状态：{{ error }} <button class="secondary" :disabled="loading" @click="load">重新加载</button></div>
  <div v-if="loading" class="card load-state" role="status" aria-live="polite">正在读取模型与服务状态…</div>
  <div v-else-if="!error && !providers.length" class="card empty-state" role="status">当前没有服务状态记录。</div>
  <div v-else-if="!error" class="metrics">
    <section v-for="provider in providers" :key="provider.name" class="card">
      <small>{{ provider.mode === 'mock' ? '当前演示服务' : '服务状态' }}</small>
      <h2>{{ provider.name === 'Mock' ? '演示模型' : provider.name }}</h2>
      <strong>{{ statusLabel(provider.status) }} · {{ modeLabel(provider.mode) }}</strong>
      <p class="provider-description">{{ provider.mode === 'mock' ? '回答来自项目内的固定演示逻辑，不会发送到外部模型。' : provider.mode === 'live' ? '当前阶段不会调用 Live 服务，也不需要填写 API Key。' : '此服务的具体说明以当前返回的服务状态为准。' }}</p>
    </section>
  </div>
</template>
