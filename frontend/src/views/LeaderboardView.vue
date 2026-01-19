<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getLeaderboard, type LeaderboardEntry } from '@/api/leaderboard'

const router = useRouter()

const leaderboardData = ref<LeaderboardEntry[]>([])
const loading = ref(false)

// 默认头像图片
const defaultAvatars = [
  '/images/Cipher_X.png',
  '/images/Ghost_Logic.png',
  '/images/Void_Runner.png'
]

const getAvatar = (index: number) => {
  return defaultAvatars[index % defaultAvatars.length]
}

// 前3名玩家（领奖台）
const podiumPlayers = computed(() => {
  const top3 = leaderboardData.value.slice(0, 3)
  // 重新排列为 [第2, 第1, 第3] 的顺序显示
  if (top3.length >= 3) {
    return [top3[1], top3[0], top3[2]]
  }
  return top3
})

// 第4名及之后的玩家
const rankPlayers = computed(() => {
  return leaderboardData.value.slice(3)
})

const formatWinRate = (rate: number) => {
  // win_rate 从后端返回时已经是百分比格式 (0-100)
  return `${rate.toFixed(1)}%`
}

const formatScore = (score: number) => {
  return score.toLocaleString()
}

const fetchLeaderboard = async () => {
  loading.value = true
  try {
    const response = await getLeaderboard(1, 'score', 'desc')
    leaderboardData.value = response.data.entries || []
  } catch {
    leaderboardData.value = []
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/lobby')
}

onMounted(() => {
  fetchLeaderboard()
})
</script>

<template>
  <div class="min-h-screen bg-bg-main overflow-x-hidden">
    <!-- 顶部导航 -->
    <header class="flex items-center justify-between border-b border-border-light px-10 py-4 sticky top-0 bg-white/90 backdrop-blur-md z-50">
      <div class="flex items-center gap-2 text-primary">
        <span class="material-symbols-outlined text-3xl font-bold">radar</span>
        <h2 class="text-text-main text-xl font-extrabold tracking-tight">INFILTRATE.AI</h2>
      </div>
      <button
        @click="goBack"
        class="flex items-center gap-2 px-5 py-2 bg-white border border-border-light rounded-xl text-sm font-bold hover:bg-slate-50 transition-all"
      >
        <span class="material-symbols-outlined text-lg">arrow_back</span> 返回大厅
      </button>
    </header>

    <main class="max-w-[1200px] mx-auto w-full px-6 py-12">
      <!-- 标题区 -->
      <div class="mb-12">
        <span class="px-3 py-1 rounded-full bg-blue-50 text-primary text-[11px] font-bold uppercase tracking-wider">
          第 04 赛季进行中
        </span>
        <h1 class="text-5xl font-black tracking-tight mt-4">
          挑战者<span class="text-primary">排行榜</span>
        </h1>
        <p class="text-text-muted text-lg mt-2 font-medium">
          AI 欺骗战斗中最熟练玩家的全球排名
        </p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="flex justify-center py-20">
        <span class="material-symbols-outlined text-4xl text-primary animate-spin">progress_activity</span>
      </div>

      <template v-else>
        <!-- 领奖台 -->
        <div v-if="podiumPlayers.length > 0" class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16 items-end">
          <div
            v-for="(player, index) in podiumPlayers"
            :key="player.user_id"
            :class="[
              'bg-white border rounded-2xl flex flex-col items-center relative transition-all',
              player.rank === 1
                ? 'border-2 border-primary p-10 transform scale-105 z-10 shadow-xl'
                : 'border-border-light p-8 shadow-sm hover:border-primary/30'
            ]"
          >
            <div
              :class="[
                'absolute -top-4 px-4 py-1 rounded-full text-[11px] font-black uppercase tracking-widest border',
                player.rank === 1
                  ? 'bg-primary text-white border-primary'
                  : 'bg-slate-100 text-slate-500 border-border-light'
              ]"
            >
              {{ player.rank === 1 ? `宗师 #0${player.rank}` : `排名 0${player.rank}` }}
            </div>
            <div
              :class="[
                'rounded-full border-4 mb-4 overflow-hidden p-1 bg-white',
                player.rank === 1 ? 'w-28 h-28 border-primary/20' : 'w-20 h-20 border-slate-200'
              ]"
            >
              <img class="w-full h-full rounded-full object-cover" :src="getAvatar(index)" :alt="player.username" />
            </div>
            <h3 :class="['font-bold mb-1', player.rank === 1 ? 'text-2xl' : 'text-xl']">
              {{ player.username }}
              <span v-if="player.is_ai" class="ml-1 text-xs px-1.5 py-0.5 bg-violet-100 text-violet-600 rounded-full font-medium">AI</span>
            </h3>
            <p class="text-primary text-sm font-bold mb-4">{{ formatWinRate(player.win_rate) }} 胜率</p>
            <div class="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
              <div class="bg-primary h-full rounded-full" :style="{ width: formatWinRate(player.win_rate) }"></div>
            </div>
          </div>
        </div>

        <!-- 无数据提示 -->
        <div v-else class="text-center py-20 text-text-muted">
          <span class="material-symbols-outlined text-6xl mb-4">leaderboard</span>
          <p class="text-lg">暂无排行榜数据</p>
        </div>

        <!-- 排名表格 -->
        <div v-if="rankPlayers.length > 0" class="bg-white rounded-2xl border border-border-light overflow-hidden shadow-sm">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 text-text-muted text-[11px] font-extrabold uppercase tracking-widest border-b border-border-light">
                <th class="px-8 py-5"># 排名</th>
                <th class="px-8 py-5">玩家名称</th>
                <th class="px-8 py-5">胜率</th>
                <th class="px-8 py-5 text-right">积分</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border-light">
              <tr
                v-for="player in rankPlayers"
                :key="player.user_id"
                class="hover:bg-blue-50/30 transition-all cursor-pointer"
              >
                <td class="px-8 py-6">
                  <div class="flex items-center gap-3">
                    <span class="text-lg font-black text-primary w-8">{{ String(player.rank).padStart(2, '0') }}</span>
                  </div>
                </td>
                <td class="px-8 py-6 font-bold">
                  {{ player.username }}
                  <span v-if="player.is_ai" class="ml-1 text-[10px] px-1.5 py-0.5 bg-violet-100 text-violet-600 rounded-full font-medium">AI</span>
                </td>
                <td class="px-8 py-6 text-primary font-bold">{{ formatWinRate(player.win_rate) }}</td>
                <td class="px-8 py-6 text-right font-black tracking-tight">{{ formatScore(player.score) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </main>
  </div>
</template>
