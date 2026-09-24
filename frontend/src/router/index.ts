import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '../pages/ChatPage.vue'
import RunPage from '../pages/RunPage.vue'
import ProvidersPage from '../pages/ProvidersPage.vue'
import CatalogPage from '../pages/CatalogPage.vue'

export const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', component: ChatPage },
  { path: '/runs/:id', component: RunPage },
  { path: '/providers', component: ProvidersPage },
  { path: '/catalog', component: CatalogPage }
] })
