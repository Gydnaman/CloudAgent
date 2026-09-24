<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { providerStatus } from '../api/client'
const providers = ref<Array<{name: string; status: string; mode: string}>>([])
const error = ref('')
async function load(): Promise<void> { try { providers.value = (await providerStatus()).providers } catch (caught) { error.value = String(caught instanceof Error ? caught.message : caught) } }
onMounted(load)
</script>
<template><div class="page-head"><div><span class="eyebrow">ADAPTERS</span><h1>Provider 状态</h1><p>阶段 A 仅运行本地固定 Mock。</p></div><span class="badge">DEMO / MOCK</span></div><div v-if="error" class="alert" role="alert">{{ error }} <button @click="load">重试</button></div><div class="metrics"><div v-for="provider in providers" :key="provider.name" class="card"><small>{{ provider.mode }}</small><h2>{{ provider.name }}</h2><strong>{{ provider.status === 'available' ? '可用 · Mock' : '尚未接入' }}</strong></div></div></template>
