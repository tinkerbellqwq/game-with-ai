<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getMyStats, getMyRank, type PersonalStats, type UserRankInfo } from '@/api/leaderboard'

const router = useRouter()
const userStore = useUserStore()

const stats = ref<PersonalStats | null>(null)
const rankInfo = ref<UserRankInfo | null>(null)
const loading = ref(false)

const formatWinRate = (rate: number) => {
  // win_rate 从后端返回时已经是百分比格式 (0-100)
  return `${rate.toFixed(1)}%`
}

const statCards = computed(() => {
  if (!stats.value) return []
  return [
    {
      title: 'AI 对战胜率',
      value: formatWinRate(stats.value.win_rate),
      icon: 'query_stats'
    },
    {
      title: '游戏场次',
      value: String(stats.value.games_played),
      sub: `胜 ${stats.value.games_won} 负 ${stats.value.games_lost}`,
      icon: 'sports_esports'
    },
    {
      title: '总积分',
      value: stats.value.score.toLocaleString(),
      sub: rankInfo.value ? `排名 #${rankInfo.value.current_rank}` : '',
      icon: 'military_tech'
    }
  ]
})

const recentGames = computed(() => {
  if (!stats.value?.recent_games) return []
  return stats.value.recent_games.map((game: any) => ({
    date: new Date(game.created_at).toLocaleDateString('zh-CN'),
    role: game.role === 'spy' ? '卧底' : '平民',
    status: game.is_winner ? '胜利' : '失败',
    pts: game.score_change > 0 ? `+${game.score_change}` : String(game.score_change),
    loss: !game.is_winner
  }))
})

const getRoleClass = (role: string) => {
  if (role === '卧底') return 'bg-primary text-white'
  if (role === '平民') return 'bg-slate-100 text-slate-500'
  return 'bg-primary/20 text-primary'
}

const fetchData = async () => {
  loading.value = true
  try {
    const [statsRes, rankRes] = await Promise.all([
      getMyStats(),
      getMyRank()
    ])
    stats.value = statsRes.data
    rankInfo.value = rankRes.data
  } catch {
    // 忽略错误
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/lobby')
}

onMounted(() => {
  userStore.init()
  fetchData()
})
</script>

<template>
  <div class="min-h-screen bg-bg-main overflow-x-hidden font-sans">
    <!-- 顶部导航 -->
    <header class="sticky top-0 z-50 w-full border-b border-border-light bg-white/80 backdrop-blur-md">
      <div class="mx-auto flex max-w-[1280px] items-center justify-between px-6 py-3">
        <div class="flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded bg-primary text-white">
            <span class="material-symbols-outlined text-[20px]">fingerprint</span>
          </div>
          <h2 class="text-lg font-bold tracking-tight">卧底工作室资料</h2>
        </div>
        <button
          @click="goBack"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white shadow-sm hover:bg-primary/90"
        >
          <span class="material-symbols-outlined text-[18px]">arrow_back</span> 返回大厅
        </button>
      </div>
    </header>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex justify-center py-20">
      <span class="material-symbols-outlined text-4xl text-primary animate-spin">progress_activity</span>
    </div>

    <main v-else class="mx-auto max-w-[1280px] px-6 py-10 grid grid-cols-1 lg:grid-cols-12 gap-8">
      <!-- 左侧个人信息 -->
      <aside class="lg:col-span-3 space-y-6">
        <div class="flex flex-col items-center lg:items-start">
          <div class="relative mb-4">
            <div
              class="h-32 w-32 rounded-3xl border-4 border-white bg-cover bg-center shadow-xl"
              :style="{
                backgroundImage: `url('/images/Profile.png')`
              }"
            ></div>
            <div class="absolute -bottom-2 -right-2 flex h-8 w-8 items-center justify-center rounded-full bg-green-500 text-white border-2 border-white">
              <span class="material-symbols-outlined text-[16px]">bolt</span>
            </div>
          </div>
          <h1 class="text-2xl font-bold">{{ userStore.user?.username || '玩家' }}</h1>
          <p class="text-sm font-medium text-text-muted">@{{ userStore.user?.username || 'user' }}</p>
          <div class="mt-2 inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
            积分 {{ stats?.score?.toLocaleString() || 0 }}
          </div>
          <p class="mt-4 text-sm leading-relaxed text-text-muted text-center lg:text-left">
            策略爱好者和欺骗大师。{{ rankInfo ? `当前排名 #${rankInfo.current_rank}` : '努力提升中...' }}
          </p>
        </div>
      </aside>

      <!-- 右侧主内容 -->
      <div class="lg:col-span-9 space-y-8">
        <!-- 统计卡片 -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div
            v-for="stat in statCards"
            :key="stat.title"
            class="bg-white p-6 rounded-xl border border-border-light hover:border-primary transition-all shadow-sm"
          >
            <div class="flex justify-between mb-4">
              <p class="text-sm font-semibold text-text-muted">{{ stat.title }}</p>
              <span class="material-symbols-outlined text-primary">{{ stat.icon }}</span>
            </div>
            <div class="flex items-baseline gap-2">
              <p class="text-3xl font-bold">{{ stat.value }}</p>
              <p v-if="stat.sub" class="text-xs font-medium text-text-muted">{{ stat.sub }}</p>
            </div>
          </div>
        </div>

        <!-- 比赛历史 -->
        <div class="bg-white border border-border-light rounded-xl overflow-hidden">
          <div class="p-6 border-b border-border-light">
            <h3 class="font-bold">最近比赛记录</h3>
          </div>
          <div v-if="recentGames.length === 0" class="p-8 text-center text-text-muted">
            <span class="material-symbols-outlined text-4xl mb-2">sports_esports</span>
            <p>暂无比赛记录</p>
          </div>
          <table v-else class="w-full text-left text-sm">
            <thead class="bg-slate-50 text-[10px] font-bold uppercase tracking-widest text-text-muted">
              <tr>
                <th class="px-6 py-3">日期</th>
                <th class="px-6 py-3">角色</th>
                <th class="px-6 py-3">状态</th>
                <th class="px-6 py-3 text-right">积分</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border-light">
              <tr
                v-for="(match, index) in recentGames"
                :key="index"
                class="hover:bg-slate-50/50 transition-colors"
              >
                <td class="px-6 py-4 font-medium">{{ match.date }}</td>
                <td class="px-6 py-4">
                  <span
                    :class="[
                      'px-2 py-1 rounded text-[10px] font-bold uppercase',
                      getRoleClass(match.role)
                    ]"
                  >
                    {{ match.role }}
                  </span>
                </td>
                <td class="px-6 py-4">
                  <div
                    :class="[
                      'flex items-center gap-2 font-bold',
                      match.loss ? 'text-red-500' : 'text-green-600'
                    ]"
                  >
                    <span class="material-symbols-outlined text-[16px]">
                      {{ match.loss ? 'cancel' : 'check_circle' }}
                    </span>
                    {{ match.status }}
                  </div>
                </td>
                <td
                  :class="[
                    'px-6 py-4 text-right font-bold',
                    match.loss ? 'text-slate-400' : 'text-primary'
                  ]"
                >
                  {{ match.pts }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</template>
