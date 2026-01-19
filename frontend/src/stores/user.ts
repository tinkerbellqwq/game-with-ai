import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, logout as apiLogout, getProfile, type UserProfile, type LoginParams } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserProfile | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value)

  const login = async (params: LoginParams) => {
    loading.value = true
    try {
      const response = await apiLogin(params)
      token.value = response.data.access_token
      localStorage.setItem('token', response.data.access_token)
      await fetchProfile()
      return { success: true }
    } catch (error: any) {
      return {
        success: false,
        message: error.response?.data?.detail || '登录失败'
      }
    } finally {
      loading.value = false
    }
  }

  const logout = async () => {
    try {
      await apiLogout()
    } catch {
      // 忽略登出错误
    } finally {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
    }
  }

  const fetchProfile = async () => {
    if (!token.value) return
    try {
      const response = await getProfile()
      user.value = response.data
    } catch {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
    }
  }

  // 初始化时获取用户信息
  const init = async () => {
    if (token.value) {
      await fetchProfile()
    }
  }

  return {
    token,
    user,
    loading,
    isLoggedIn,
    login,
    logout,
    fetchProfile,
    init
  }
})
