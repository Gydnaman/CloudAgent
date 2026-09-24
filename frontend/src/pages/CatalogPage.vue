<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { catalog } from '../api/client'
const knowledge = ref<Array<{id: string; name: string; type: string; status: string}>>([])
const tools = ref<Array<{name: string; type: string; status: string}>>([])
const error = ref('')
async function load(): Promise<void> { try { const result = await catalog(); knowledge.value = result.knowledge; tools.value = result.tools } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) } }
onMounted(load)
</script>
<template><div class="page-head"><div><span class="eyebrow">FIXTURES</span><h1>知识源与工具</h1><p>仅展示本地合成资料与只读 adapter。</p></div><span class="badge">DEMO / MOCK</span></div><div v-if="error" class="alert" role="alert">{{ error }} <button @click="load">重试</button></div><div class="metrics"><section class="card"><h2>知识源</h2><p v-if="!knowledge.length" class="empty">暂无知识源</p><div v-for="source in knowledge" :key="source.id" class="result"><strong>{{ source.name }}</strong><p>{{ source.id }} · {{ source.type }}</p></div></section><section class="card"><h2>工具</h2><p v-if="!tools.length" class="empty">暂无工具</p><div v-for="tool in tools" :key="tool.name" class="result"><strong>{{ tool.name }}</strong><p>{{ tool.type }} · 只读</p></div></section></div></template>
