import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import LobbyView from '@/views/LobbyView.vue'
import RoomView from '@/views/RoomView.vue'
import LeaderboardView from '@/views/LeaderboardView.vue'
import ProfileView from '@/views/ProfileView.vue'
import AiManageView from '@/views/AiManageView.vue'
import WordManageView from '@/views/WordManageView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'login',
      component: LoginView
    },
    {
      path: '/lobby',
      name: 'lobby',
      component: LobbyView
    },
    {
      path: '/room/:id?',
      name: 'room',
      component: RoomView
    },
    {
      path: '/leaderboard',
      name: 'leaderboard',
      component: LeaderboardView
    },
    {
      path: '/profile',
      name: 'profile',
      component: ProfileView
    },
    {
      path: '/ai-manage',
      name: 'ai-manage',
      component: AiManageView
    },
    {
      path: '/word-manage',
      name: 'word-manage',
      component: WordManageView
    }
  ]
})

export default router
