<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getRooms, createRoom, joinRoom, type RoomInfo } from '@/api/rooms'
import CreateRoomModal from '@/components/CreateRoomModal.vue'

const router = useRouter()
const userStore = useUserStore()

const rooms = ref<RoomInfo[]>([])
const loading = ref(false)
const showCreateModal = ref(false)

// 加入房间相关
const showJoinPasswordModal = ref(false)
const joiningRoom = ref<RoomInfo | null>(null)
const joinPassword = ref('')
const joinError = ref('')
const joining = ref(false)

interface MissionCardProps {
  title: string
  players: string
  desc: string
  img: string
}

const missions: MissionCardProps[] = [
  {
    title: 'AI 狼人杀',
    players: '8-12 玩家',
    desc: '与训练有素的 AI 进行社交推理对决',
    img: '/images/card1.png'
  },
  {
    title: '神经画谜',
    players: '4-8 玩家',
    desc: '猜测 AI 艺术家的提示词',
    img: '/images/card2.png'
  },
  {
    title: '二进制谎言',
    players: '热门',
    desc: '辨别真相与幻觉',
    img: '/images/card3.png'
  }
]

const navigateTo = (route: string) => {
  router.push(route)
}

const handleLogout = async () => {
  await userStore.logout()
  router.push('/')
}

const fetchRooms = async () => {
  loading.value = true
  try {
    const response = await getRooms({ status: 'waiting' })
    rooms.value = response.data.rooms || []
  } catch {
    rooms.value = []
  } finally {
    loading.value = false
  }
}

// 创建房间
const handleCreateRoom = async (data: {
  name: string
  max_players: number
  ai_count: number
  password?: string
  ai_template_ids?: string[]
}) => {
  try {
    const response = await createRoom(data)
    showCreateModal.value = false
    router.push(`/room/${response.data.id}`)
  } catch (e: any) {
    console.error('创建房间失败:', e)
  }
}

// 加入房间
const handleJoinRoom = async (room: RoomInfo) => {
  if (room.has_password) {
    joiningRoom.value = room
    joinPassword.value = ''
    joinError.value = ''
    showJoinPasswordModal.value = true
  } else {
    await doJoinRoom(room.id)
  }
}

// 执行加入房间
const doJoinRoom = async (roomId: number, password?: string) => {
  joining.value = true
  joinError.value = ''
  try {
    const response = await joinRoom(roomId, password)
    if (response.data.success) {
      showJoinPasswordModal.value = false
      router.push(`/room/${roomId}`)
    } else {
      joinError.value = response.data.message || '加入失败'
    }
  } catch (e: any) {
    joinError.value = e.response?.data?.detail || '加入房间失败'
  } finally {
    joining.value = false
  }
}

// 提交密码加入
const handlePasswordJoin = async () => {
  if (!joiningRoom.value) return
  await doJoinRoom(joiningRoom.value.id, joinPassword.value)
}

onMounted(() => {
  userStore.init()
  fetchRooms()
})
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-bg-main">
    <!-- 左侧导航栏 -->
    <aside class="w-64 border-r border-border-light bg-white flex flex-col">
      <div class="p-6">
        <div class="flex items-center gap-2 mb-8 text-primary">
          <span class="material-symbols-outlined text-2xl font-bold">radar</span>
          <h1 class="text-xl font-bold tracking-tight text-text-main">SPY.NET</h1>
        </div>
        <nav class="space-y-1">
          <button class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl bg-primary/10 text-primary font-semibold">
            <span class="material-symbols-outlined">dashboard</span> 大厅
          </button>
          <button
            @click="navigateTo('/leaderboard')"
            class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-text-muted hover:bg-slate-50 transition-colors"
          >
            <span class="material-symbols-outlined">leaderboard</span> 排行榜
          </button>
          <button
            @click="navigateTo('/profile')"
            class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-text-muted hover:bg-slate-50 transition-colors"
          >
            <span class="material-symbols-outlined">person</span> 个人资料
          </button>
          <button
            @click="navigateTo('/ai-manage')"
            class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-text-muted hover:bg-slate-50 transition-colors"
          >
            <span class="material-symbols-outlined">smart_toy</span> AI 管理
          </button>
          <!-- 词汇管理 - 仅 admin 用户可见 -->
          <button
            v-if="userStore.user?.username === 'admin'"
            @click="navigateTo('/word-manage')"
            class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-text-muted hover:bg-slate-50 transition-colors"
          >
            <span class="material-symbols-outlined">dictionary</span> 词汇管理
          </button>
        </nav>
      </div>
      <div class="mt-auto p-6">
        <div class="bg-slate-50 rounded-2xl p-4 border border-border-light">
          <p class="text-[10px] font-bold text-slate-400 uppercase mb-2">系统状态</p>
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-green-500"></div>
            <span class="text-xs font-medium text-slate-600">服务器运行正常</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="flex-1 overflow-y-auto p-8 custom-scrollbar">
      <header class="flex justify-between items-center mb-8">
        <div>
          <h2 class="text-2xl font-extrabold">欢迎回来，{{ userStore.user?.username || '特工' }}</h2>
          <p class="text-text-muted text-sm">探索最新的 AI 推理游戏</p>
        </div>
        <div class="flex items-center gap-4">
          <button
            @click="showCreateModal = true"
            class="bg-primary hover:bg-primary-hover text-white px-6 py-2.5 rounded-xl font-bold shadow-lg shadow-primary/20 flex items-center gap-2"
          >
            <span class="material-symbols-outlined">add</span> 创建房间
          </button>
          <button
            @click="handleLogout"
            class="text-text-muted hover:text-red-500 transition-colors p-2"
            title="退出登录"
          >
            <span class="material-symbols-outlined">logout</span>
          </button>
        </div>
      </header>

      <!-- 横幅区域 -->
      <section
        class="relative rounded-[2rem] overflow-hidden mb-12 h-80 bg-cover bg-center"
        :style="{
          backgroundImage: `linear-gradient(to right, white 30%, transparent), url('/images/Banner.png')`
        }"
      >
        <div class="relative h-full flex flex-col justify-center px-12 max-w-xl">
          <div class="inline-flex items-center gap-2 bg-primary/10 text-primary text-[10px] font-bold px-3 py-1 rounded-full mb-6 w-fit">
            新赛季开启
          </div>
          <h3 class="text-5xl font-black text-slate-900 leading-tight mb-4">
            谁是<span class="text-primary italic">卧底？</span>
          </h3>
          <p class="text-slate-600 text-lg mb-8 leading-relaxed">揭露神经网络伪装者。挑战高级 AI 对手。</p>
          <div class="flex gap-4">
            <button
              @click="showCreateModal = true"
              class="bg-primary text-white px-8 py-3 rounded-2xl font-bold transition-all hover:bg-primary-hover shadow-lg shadow-primary/20"
            >
              快速开始
            </button>
          </div>
        </div>
      </section>

      <!-- 任务卡片区 -->
      <section class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
        <div
          v-for="mission in missions"
          :key="mission.title"
          class="bg-white border border-border-light rounded-[1.5rem] overflow-hidden shadow-sm hover:-translate-y-1 transition-all"
        >
          <div class="h-44 overflow-hidden">
            <img :alt="mission.title" class="w-full h-full object-cover" :src="mission.img" />
          </div>
          <div class="p-5">
            <div class="flex justify-between items-start mb-2">
              <h5 class="text-lg font-bold">{{ mission.title }}</h5>
              <span class="bg-blue-50 text-primary text-[10px] font-bold px-2 py-0.5 rounded">
                {{ mission.players }}
              </span>
            </div>
            <p class="text-text-muted text-sm mb-4">{{ mission.desc }}</p>
            <div class="flex justify-between pt-4 border-t border-slate-50">
              <span class="text-xs text-slate-400 font-semibold flex items-center gap-1">
                <span class="material-symbols-outlined text-sm">psychology</span> GPT-4o 集成
              </span>
              <button class="text-primary font-bold text-sm">快速开始</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 房间列表 -->
      <section>
        <div class="flex items-center justify-between mb-6">
          <h4 class="text-xl font-bold flex items-center gap-2">
            <span class="material-symbols-outlined text-primary">meeting_room</span>
            可加入的房间
          </h4>
          <button
            @click="fetchRooms"
            :disabled="loading"
            class="flex items-center gap-1 text-sm text-text-muted hover:text-primary transition-colors"
          >
            <span :class="['material-symbols-outlined text-lg', loading && 'animate-spin']">refresh</span>
            刷新
          </button>
        </div>

        <div v-if="loading" class="text-center py-12 text-text-muted">
          <span class="material-symbols-outlined text-4xl animate-spin">progress_activity</span>
          <p class="mt-2">加载中...</p>
        </div>

        <div v-else-if="rooms.length === 0" class="text-center py-12 bg-white rounded-2xl border border-border-light">
          <span class="material-symbols-outlined text-5xl text-slate-300">meeting_room</span>
          <p class="text-text-muted mt-2">暂无可加入的房间</p>
          <button
            @click="showCreateModal = true"
            class="mt-4 px-6 py-2 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover transition-colors"
          >
            创建一个房间
          </button>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="room in rooms"
            :key="room.id"
            class="bg-white border border-border-light rounded-2xl p-5 hover:shadow-lg hover:-translate-y-0.5 transition-all"
          >
            <div class="flex items-start justify-between mb-3">
              <div class="flex items-center gap-2">
                <div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
                  <span class="material-symbols-outlined">sports_esports</span>
                </div>
                <div>
                  <h5 class="font-bold text-sm">{{ room.name }}</h5>
                  <p class="text-[10px] text-text-muted">创建者: {{ room.creator_name }}</p>
                </div>
              </div>
              <span
                v-if="room.has_password"
                class="text-amber-500"
                title="需要密码"
              >
                <span class="material-symbols-outlined text-lg">lock</span>
              </span>
            </div>

            <div class="flex items-center gap-4 text-xs text-text-muted mb-4">
              <span class="flex items-center gap-1">
                <span class="material-symbols-outlined text-sm">group</span>
                {{ room.current_player_count }}/{{ room.max_players }}
              </span>
              <span class="flex items-center gap-1">
                <span class="material-symbols-outlined text-sm">smart_toy</span>
                {{ room.ai_count }} AI
              </span>
            </div>

            <button
              @click="handleJoinRoom(room)"
              class="w-full py-2.5 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover transition-colors flex items-center justify-center gap-2"
            >
              <span class="material-symbols-outlined text-lg">login</span>
              加入房间
            </button>
          </div>
        </div>
      </section>
    </main>

    <!-- 创建房间模态框 -->
    <CreateRoomModal
      :show="showCreateModal"
      :user-name="userStore.user?.username"
      @close="showCreateModal = false"
      @create="handleCreateRoom"
    />

    <!-- 密码输入模态框 -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-all duration-300"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-all duration-200"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showJoinPasswordModal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          @click.self="showJoinPasswordModal = false"
        >
          <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-6">
            <div class="flex items-center gap-3 mb-4">
              <div class="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center text-amber-600">
                <span class="material-symbols-outlined">lock</span>
              </div>
              <div>
                <h3 class="font-bold">输入房间密码</h3>
                <p class="text-xs text-text-muted">{{ joiningRoom?.name }}</p>
              </div>
            </div>

            <input
              v-model="joinPassword"
              type="password"
              class="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none mb-4"
              placeholder="请输入密码"
              @keyup.enter="handlePasswordJoin"
            />

            <p v-if="joinError" class="text-red-500 text-sm mb-4">{{ joinError }}</p>

            <div class="flex gap-3">
              <button
                @click="showJoinPasswordModal = false"
                :disabled="joining"
                class="flex-1 py-2.5 bg-slate-100 text-slate-600 font-bold rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                @click="handlePasswordJoin"
                :disabled="joining"
                class="flex-1 py-2.5 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <span v-if="joining" class="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                加入
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
