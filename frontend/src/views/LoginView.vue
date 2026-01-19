<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { register } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()

const isRegister = ref(false)
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMsg = ref('')
const successMsg = ref('')

const handleLogin = async () => {
  errorMsg.value = ''
  successMsg.value = ''
  const result = await userStore.login({
    username: username.value,
    password: password.value
  })
  if (result.success) {
    router.push('/lobby')
  } else {
    errorMsg.value = result.message || '登录失败'
  }
}

const handleRegister = async () => {
  errorMsg.value = ''
  successMsg.value = ''

  if (password.value !== confirmPassword.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }

  if (password.value.length < 6) {
    errorMsg.value = '密码长度至少6位'
    return
  }

  try {
    await register({
      username: username.value,
      email: email.value,
      password: password.value
    })
    successMsg.value = '注册成功，请登录'
    isRegister.value = false
    password.value = ''
    confirmPassword.value = ''
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || '注册失败'
  }
}

const toggleMode = () => {
  isRegister.value = !isRegister.value
  errorMsg.value = ''
  successMsg.value = ''
}
</script>

<template>
  <div class="flex min-h-screen font-display">
    <!-- 左侧展示区域 -->
    <div class="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-white border-r border-border-light">
      <div class="relative z-10 flex flex-col items-center justify-center w-full p-12">
        <div class="w-full max-w-lg">
          <div class="w-full aspect-square rounded-2xl flex items-center justify-center border border-slate-100 shadow-xl mb-12 overflow-hidden">
            <img
              src="/images/Login.png"
              class="w-full h-full object-cover"
              alt="AI Neural"
            />
          </div>
          <h2 class="text-4xl font-bold mb-4 leading-tight">
            人类直觉 vs. <br/>
            <span class="text-primary">机器逻辑</span>
          </h2>
          <p class="text-lg text-slate-500 font-light leading-relaxed">
            踏入高风险的社交推理竞技场。你能智胜神经网络吗？
          </p>
        </div>
      </div>
    </div>

    <!-- 右侧登录/注册区域 -->
    <div class="w-full lg:w-1/2 flex flex-col items-center justify-center p-6 bg-slate-50">
      <div class="w-full max-w-[460px] bg-white p-10 rounded-2xl shadow-sm border border-border-light">
        <div class="flex items-center gap-3 mb-10">
          <div class="size-10 bg-primary rounded-lg flex items-center justify-center text-white shadow-lg">
            <span class="material-symbols-outlined">radar</span>
          </div>
          <h1 class="text-xl font-bold tracking-tight">谁是卧底</h1>
        </div>

        <div class="mb-8">
          <h2 class="text-3xl font-bold mb-2">{{ isRegister ? '创建账号' : '进入游戏' }}</h2>
          <p class="text-slate-500">{{ isRegister ? '填写信息创建新账号' : '输入您的凭据开始游戏' }}</p>
        </div>

        <form class="space-y-5" @submit.prevent="isRegister ? handleRegister() : handleLogin()">
          <!-- 错误提示 -->
          <div v-if="errorMsg" class="p-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
            {{ errorMsg }}
          </div>

          <!-- 成功提示 -->
          <div v-if="successMsg" class="p-3 bg-green-50 border border-green-200 rounded-xl text-green-600 text-sm">
            {{ successMsg }}
          </div>

          <div class="space-y-2">
            <label class="text-sm font-semibold text-slate-700">用户名</label>
            <div class="relative">
              <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">person</span>
              <input
                v-model="username"
                class="w-full pl-12 h-14 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none"
                placeholder="请输入用户名"
                type="text"
                required
              />
            </div>
          </div>

          <!-- 邮箱（仅注册时显示） -->
          <div v-if="isRegister" class="space-y-2">
            <label class="text-sm font-semibold text-slate-700">邮箱</label>
            <div class="relative">
              <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">mail</span>
              <input
                v-model="email"
                class="w-full pl-12 h-14 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none"
                placeholder="请输入邮箱"
                type="email"
                required
              />
            </div>
          </div>

          <div class="space-y-2">
            <label class="text-sm font-semibold text-slate-700">密码</label>
            <div class="relative">
              <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">lock</span>
              <input
                v-model="password"
                class="w-full pl-12 h-14 bg-slate-50 border border-slate-200 rounded-xl outline-none"
                placeholder="••••••••"
                type="password"
                required
              />
            </div>
          </div>

          <!-- 确认密码（仅注册时显示） -->
          <div v-if="isRegister" class="space-y-2">
            <label class="text-sm font-semibold text-slate-700">确认密码</label>
            <div class="relative">
              <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">lock</span>
              <input
                v-model="confirmPassword"
                class="w-full pl-12 h-14 bg-slate-50 border border-slate-200 rounded-xl outline-none"
                placeholder="••••••••"
                type="password"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            :disabled="userStore.loading"
            class="w-full h-14 bg-primary hover:bg-primary-hover text-white font-bold rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <span v-if="userStore.loading" class="material-symbols-outlined animate-spin">progress_activity</span>
            <template v-else>
              {{ isRegister ? '注册' : '登录' }} <span class="material-symbols-outlined">arrow_forward</span>
            </template>
          </button>
        </form>

        <!-- 切换登录/注册 -->
        <div class="mt-6 text-center">
          <p class="text-slate-500 text-sm">
            {{ isRegister ? '已有账号？' : '还没有账号？' }}
            <button
              type="button"
              @click="toggleMode"
              class="text-primary font-semibold hover:underline"
            >
              {{ isRegister ? '立即登录' : '立即注册' }}
            </button>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
