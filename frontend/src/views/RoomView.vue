<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { getRoomDetail, joinRoom, leaveRoom, type RoomDetail } from '@/api/rooms'
import {
  createGame,
  startGame,
  getGameState,
  submitSpeech,
  submitVote,
  getSpeeches,
  type GameState,
  type Speech,
  type GamePlayer
} from '@/api/games'
import GameNotification, { type GameNotificationData } from '@/components/GameNotification.vue'
import GameProgress from '@/components/GameProgress.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 基础状态
const roomId = computed(() => route.params.id ? String(route.params.id) : null)
const room = ref<RoomDetail | null>(null)
const gameState = ref<GameState | null>(null)
const previousPhase = ref<string | null>(null)
const previousRound = ref<number>(1)
const speeches = ref<Speech[]>([])
const loading = ref(false)
const wordRevealed = ref(false)
const speechInput = ref('')

// 消息框容器引用（用于自动滚动）
const messagesContainer = ref<HTMLElement | null>(null)

// 投票记录
interface VoteRecord {
  voterId: string
  voterName: string
  targetId: string
  roundNumber: number
  isAi: boolean
}
const voteRecords = ref<VoteRecord[]>([])

// 通知状态
const currentNotification = ref<GameNotificationData | null>(null)
const notificationQueue = ref<GameNotificationData[]>([])

// WebSocket
const ws = ref<WebSocket | null>(null)
const wsConnected = ref(false)

// 玩家列表
const players = computed(() => {
  // 优先使用游戏状态中的玩家列表
  if (gameState.value?.players) {
    return gameState.value.players.map(p => ({
      id: p.id,
      name: p.username,
      type: p.is_ai ? 'AI' as const : 'Human' as const,
      status: p.is_alive ? (p.is_ready ? 'Ready' : 'Alive') : 'Eliminated',
      isAlive: p.is_alive,
      active: gameState.value?.current_speaker === p.id || gameState.value?.current_speaker_id === p.id
    }))
  }
  // 回退到房间玩家列表
  if (!room.value?.players) return []
  return room.value.players.map(p => ({
    id: p.id,
    name: p.username,
    type: p.is_ai ? 'AI' as const : 'Human' as const,
    status: p.is_ready ? 'Ready' : 'Waiting',
    isAlive: true,
    active: false
  }))
})

// 存活玩家
const alivePlayers = computed(() => players.value.filter(p => p.isAlive))

// 当前发言者索引
const currentSpeakerIndex = computed(() => {
  if (!gameState.value?.current_speaker && !gameState.value?.current_speaker_id) return -1
  const speakerId = gameState.value.current_speaker || gameState.value.current_speaker_id
  return alivePlayers.value.findIndex(p => p.id === speakerId)
})

// 当前发言者信息
const currentSpeaker = computed(() => {
  const speakerId = gameState.value?.current_speaker || gameState.value?.current_speaker_id
  if (!speakerId) return null
  return players.value.find(p => p.id === speakerId)
})

// 聊天消息（发言记录）
const messages = computed(() => {
  return speeches.value.map(s => ({
    sender: s.player_name,
    text: s.content,
    round: s.round_number,
    type: players.value.find(p => String(p.id) === String(s.player_id))?.type === 'AI' ? 'ai' as const : 'user' as const
  }))
})

// 所有需要显示的回合号（包括当前回合，即使没有消息）
const displayRounds = computed(() => {
  const messageRounds = new Set(messages.value.map(m => m.round))
  // 添加当前回合（如果游戏进行中）
  const currentRound = gameState.value?.round_number
  if (currentRound && currentRound > 0) {
    messageRounds.add(currentRound)
  }
  // 添加投票记录中的回合
  voteRecords.value.forEach(v => messageRounds.add(v.roundNumber))
  return [...messageRounds].sort((a, b) => a - b)
})

// 是否是房主
const isOwner = computed(() => {
  return room.value?.creator_id === userStore.user?.id
})

// 当前阶段（标准化为大写）
const currentPhase = computed(() => {
  return gameState.value?.current_phase?.toUpperCase() || ''
})

// 当前阶段显示
const phaseText = computed(() => {
  if (!gameState.value) return '等待中'
  switch (currentPhase.value) {
    case 'WAITING': return '准备阶段'
    case 'PREPARING': return '准备阶段'
    case 'SPEAKING': return '发言阶段'
    case 'VOTING': return '投票阶段'
    case 'RESULT': return '结果公布'
    case 'FINISHED': return '游戏结束'
    default: return '等待中'
  }
})

// 是否轮到当前用户发言
const isMyTurn = computed(() => {
  const speakerId = gameState.value?.current_speaker || gameState.value?.current_speaker_id
  return speakerId === userStore.user?.id
})

// 是否轮到当前用户投票
const isMyVote = computed(() => {
  // 后端返回 current_voter，前端类型定义可能是 current_voter_id
  const voterId = gameState.value?.current_voter || gameState.value?.current_voter_id
  return voterId === userStore.user?.id
})

// === 通知系统 ===
const showNotification = (notification: GameNotificationData) => {
  if (currentNotification.value) {
    notificationQueue.value.push(notification)
  } else {
    currentNotification.value = notification
  }
}

const handleNotificationClose = () => {
  currentNotification.value = null
  if (notificationQueue.value.length > 0) {
    setTimeout(() => {
      currentNotification.value = notificationQueue.value.shift() || null
    }, 300)
  }
}

// 自动滚动消息框到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    setTimeout(() => {
      messagesContainer.value?.scrollTo({
        top: messagesContainer.value.scrollHeight,
        behavior: 'smooth'
      })
    }, 100)
  }
}

// === WebSocket 连接 ===
const connectWebSocket = () => {
  if (!roomId.value || !userStore.token) return

  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = import.meta.env.VITE_WS_URL || `${wsProtocol}//${window.location.host}`
  const wsUrl = `${wsHost}/api/v1/ws/${roomId.value}?token=${userStore.token}`

  try {
    ws.value = new WebSocket(wsUrl)

    ws.value.onopen = () => {
      console.log('[WS] Connected')
      wsConnected.value = true
    }

    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(data)
      } catch (e) {
        console.error('[WS] Failed to parse message:', e)
      }
    }

    ws.value.onclose = () => {
      console.log('[WS] Disconnected')
      wsConnected.value = false
      // 尝试重连
      setTimeout(() => {
        if (roomId.value) connectWebSocket()
      }, 3000)
    }

    ws.value.onerror = (error) => {
      console.error('[WS] Error:', error)
    }
  } catch (e) {
    console.error('[WS] Failed to connect:', e)
  }
}

const handleWebSocketMessage = (data: any) => {
  console.log('[WS] Message:', data.type, data)

  switch (data.type) {
    case 'game_started':
      showNotification({
        type: 'phase_change',
        title: '游戏开始',
        message: '游戏已开始，准备发言！',
        color: 'primary',
        duration: 2000
      })
      fetchGameState()
      break

    case 'phase_changed':
      handlePhaseChange(data.data)
      break

    case 'round_started':
      // 新一轮开始，清空投票记录
      voteRecords.value = []
      showNotification({
        type: 'round_start',
        title: `第 ${data.data.round_number} 轮`,
        message: '新一轮发言开始',
        color: 'primary',
        duration: 2500
      })
      fetchGameState()
      fetchSpeeches()
      break

    case 'speech_submitted':
    case 'ai_speech':
    case 'game_speech':
      fetchSpeeches()
      fetchGameState()
      scrollToBottom()
      break

    case 'vote_submitted':
    case 'ai_vote':
    case 'game_vote':
      // 记录投票信息
      if (data.data) {
        const voterName = data.data.voter_name || players.value.find(p => p.id === data.data.voter_id)?.name || '未知玩家'
        voteRecords.value.push({
          voterId: data.data.voter_id,
          voterName: voterName,
          targetId: data.data.target_id,
          roundNumber: data.data.round_number || gameState.value?.round_number || 1,
          isAi: data.data.is_ai || false
        })
        scrollToBottom()
      }
      fetchGameState()
      break

    case 'player_eliminated':
      showNotification({
        type: 'player_eliminated',
        title: '玩家被淘汰',
        message: `${data.data.player_name} 被投票淘汰`,
        playerName: data.data.player_name,
        color: 'danger',
        duration: 4000
      })
      fetchGameState()
      break

    case 'round_ended':
      showNotification({
        type: 'round_start',
        title: `第 ${data.data.round_number} 轮结束`,
        message: '进入下一轮',
        color: 'primary',
        duration: 2000
      })
      break

    case 'game_ended':
      showNotification({
        type: 'game_end',
        title: '游戏结束',
        message: data.data.winner_role === 'undercover' ? '卧底获胜！' : '平民获胜！',
        winnerRole: data.data.winner_role,
        color: data.data.winner_role === 'undercover' ? 'danger' : 'success',
        duration: 0 // 不自动关闭
      })
      fetchGameState()
      break

    case 'player_joined':
      showNotification({
        type: 'phase_change',
        title: '玩家加入',
        message: `${data.data?.username || '新玩家'} 加入了房间`,
        color: 'primary',
        duration: 2000
      })
      fetchRoom()
      break

    case 'player_left':
      fetchRoom()
      break
  }
}

const handlePhaseChange = (data: any) => {
  const phase = data.new_phase || data.phase

  if (phase === 'SPEAKING') {
    showNotification({
      type: 'phase_change',
      title: '发言阶段',
      message: '请依次描述你的词汇',
      icon: 'mic',
      color: 'primary',
      duration: 2500
    })
  } else if (phase === 'VOTING') {
    showNotification({
      type: 'phase_change',
      title: '投票阶段',
      message: '请投票选出你认为的卧底',
      icon: 'how_to_vote',
      color: 'warning',
      duration: 2500
    })
  }

  fetchGameState()
}

// === 监听阶段变化（轮询模式下的备用方案） ===
watch(() => gameState.value?.current_phase, (newPhase, oldPhase) => {
  if (!newPhase || !oldPhase || newPhase === oldPhase) return
  if (wsConnected.value) return // WebSocket 已连接，不重复处理

  previousPhase.value = oldPhase

  // 标准化为大写比较
  const newPhaseUpper = newPhase.toUpperCase()
  const oldPhaseUpper = oldPhase.toUpperCase()

  if (oldPhaseUpper === 'SPEAKING' && newPhaseUpper === 'VOTING') {
    showNotification({
      type: 'phase_change',
      title: '发言结束',
      message: '进入投票阶段，请选择你认为的卧底',
      icon: 'how_to_vote',
      color: 'warning',
      duration: 3000
    })
  } else if (oldPhaseUpper === 'VOTING' && newPhaseUpper === 'SPEAKING') {
    // 新一轮开始，清空投票记录
    voteRecords.value = []
    showNotification({
      type: 'round_start',
      title: `第 ${gameState.value?.round_number || 1} 轮`,
      message: '新一轮发言开始',
      color: 'primary',
      duration: 2500
    })
  } else if (newPhaseUpper === 'FINISHED') {
    showNotification({
      type: 'game_end',
      title: '游戏结束',
      message: gameState.value?.winner_role === 'undercover' ? '卧底获胜！' : '平民获胜！',
      winnerRole: gameState.value?.winner_role,
      color: gameState.value?.winner_role === 'undercover' ? 'danger' : 'success',
      duration: 0
    })
  }
})

// 监听轮次变化
watch(() => gameState.value?.round_number, (newRound, oldRound) => {
  if (!newRound || !oldRound || newRound === oldRound) return
  if (wsConnected.value) return

  if (newRound > oldRound) {
    previousRound.value = oldRound
  }
})

// 监听当前发言者变化
watch(() => currentSpeaker.value, (newSpeaker, oldSpeaker) => {
  if (!newSpeaker || newSpeaker.id === oldSpeaker?.id) return

  if (newSpeaker.id === userStore.user?.id) {
    showNotification({
      type: 'your_turn',
      title: '轮到你了',
      message: '请描述你的词汇',
      icon: 'mic',
      color: 'primary',
      duration: 2500
    })
  } else if (newSpeaker.type === 'AI') {
    // AI 发言不需要通知，只在界面上显示
  }
})

// === API 调用 ===
const fetchRoom = async () => {
  if (!roomId.value) return
  try {
    const response = await getRoomDetail(roomId.value as any)
    room.value = response.data
  } catch {
    // 房间不存在
  }
}

const fetchGameState = async () => {
  if (!gameState.value?.id) return
  try {
    const response = await getGameState(gameState.value.id as any)
    // 后端返回 { success, game, current_user } 结构
    const data = response.data as any
    if (data.game) {
      gameState.value = {
        ...data.game,
        user_role: data.current_user?.role,
        user_word: data.current_user?.word
      }
    } else {
      gameState.value = data
    }
  } catch {
    // 忽略
  }
}

const fetchSpeeches = async () => {
  if (!gameState.value?.id) return
  try {
    const response = await getSpeeches(gameState.value.id as any)
    speeches.value = response.data.speeches || []
  } catch {
    // 忽略
  }
}

const handleStartGame = async () => {
  if (!roomId.value) return
  loading.value = true
  try {
    const createRes = await createGame(roomId.value as any)
    // 后端返回 game_id 而不是 id
    const gameId = createRes.data.game_id || createRes.data.id

    showNotification({
      type: 'phase_change',
      title: '游戏创建成功',
      message: '正在分配角色和词汇...',
      color: 'primary',
      duration: 2000
    })

    await startGame(gameId as any)

    // 获取完整的游戏状态
    const stateRes = await getGameState(gameId as any)
    // 后端返回 { success, game, current_user } 结构
    const stateData = stateRes.data as any
    if (stateData.game) {
      gameState.value = {
        ...stateData.game,
        user_role: stateData.current_user?.role,
        user_word: stateData.current_user?.word
      }
    } else {
      gameState.value = stateData
    }

    await fetchSpeeches()
  } catch (e: any) {
    showNotification({
      type: 'phase_change',
      title: '开始失败',
      message: e.response?.data?.detail || '无法开始游戏',
      color: 'danger',
      duration: 3000
    })
  } finally {
    loading.value = false
  }
}

const handleSpeech = async () => {
  if (!gameState.value?.id || !speechInput.value.trim()) return
  try {
    await submitSpeech(gameState.value.id as any, speechInput.value)
    speechInput.value = ''
    await fetchGameState()
    await fetchSpeeches()
  } catch {
    // 发言失败
  }
}

const handleVote = async (targetId: string) => {
  if (!gameState.value?.id) return
  try {
    await submitVote(gameState.value.id as any, targetId as any)
    await fetchGameState()
  } catch {
    // 投票失败
  }
}

const handleLeave = async () => {
  if (roomId.value) {
    try {
      await leaveRoom(roomId.value as any)
    } catch {
      // 忽略
    }
  }
  if (ws.value) {
    ws.value.close()
  }
  router.push('/lobby')
}

// 定时刷新（WebSocket 断开时的备用方案）
let refreshInterval: number | null = null

onMounted(async () => {
  await userStore.init()

  if (roomId.value) {
    await fetchRoom()
    connectWebSocket()
  } else {
    // 没有房间ID，返回大厅
    router.push('/lobby')
    return
  }

  // 定时刷新状态（备用）
  refreshInterval = window.setInterval(async () => {
    if (!wsConnected.value) {
      if (gameState.value) {
        await fetchGameState()
        await fetchSpeeches()
      } else if (roomId.value) {
        await fetchRoom()
      }
    }
  }, 3000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  if (ws.value) {
    ws.value.close()
  }
})
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <!-- 游戏通知 -->
    <GameNotification
      :notification="currentNotification"
      @close="handleNotificationClose"
    />

    <!-- 顶部导航 -->
    <header class="h-16 flex items-center justify-between border-b border-border-light px-6 bg-white shrink-0">
      <div class="flex items-center gap-6">
        <div class="flex items-center gap-2">
          <div class="size-8 bg-primary rounded-lg flex items-center justify-center text-white">
            <span class="material-symbols-outlined text-xl">psychology</span>
          </div>
          <h2 class="text-text-main text-lg font-bold tracking-tight">
            {{ room?.name || '卧底工作室' }}
          </h2>
        </div>
        <div class="h-8 w-px bg-border-light mx-2"></div>
        <div class="flex items-center gap-3">
          <div class="flex items-center bg-slate-100 rounded-full px-4 py-1.5 border border-border-light">
            <span class="material-symbols-outlined text-primary text-lg mr-2">info</span>
            <span class="text-primary font-bold text-sm">{{ phaseText }}</span>
          </div>
          <!-- 连接状态 -->
          <div
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold',
              wsConnected ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
            ]"
          >
            <span
              :class="[
                'w-2 h-2 rounded-full',
                wsConnected ? 'bg-green-500' : 'bg-amber-500 animate-pulse'
              ]"
            />
            {{ wsConnected ? '已连接' : '连接中...' }}
          </div>
        </div>
      </div>
      <div class="flex gap-4">
        <button @click="handleLeave" class="text-text-muted hover:text-red-500 transition-colors">
          <span class="material-symbols-outlined">logout</span>
        </button>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <!-- 左侧玩家列表 -->
      <aside class="w-72 border-r border-border-light bg-white flex flex-col p-4">
        <h3 class="text-xs font-bold text-text-muted uppercase mb-4">
          参与者 ({{ alivePlayers.length }}/{{ players.length }})
        </h3>
        <div class="space-y-3 flex-1 overflow-y-auto">
          <div
            v-for="player in players"
            :key="player.id"
            :class="[
              'p-3 rounded-xl border transition-all',
              !player.isAlive ? 'opacity-50 bg-slate-50 border-slate-200' :
              player.active ? 'bg-primary/5 border-primary/20 ring-2 ring-primary/20' : 'bg-white border-border-light'
            ]"
          >
            <div class="flex items-center gap-3">
              <div
                :class="[
                  'size-10 rounded-lg flex items-center justify-center relative',
                  !player.isAlive ? 'bg-slate-200 text-slate-400' :
                  player.active ? 'bg-primary/10 text-primary' :
                  player.type === 'AI' ? 'bg-purple-100 text-purple-600' : 'bg-slate-100 text-slate-400'
                ]"
              >
                <span class="material-symbols-outlined">
                  {{ player.type === 'AI' ? 'smart_toy' : 'person' }}
                </span>
                <!-- 当前发言指示器 -->
                <span
                  v-if="player.active && currentPhase === 'SPEAKING'"
                  class="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full animate-pulse"
                />
              </div>
              <div class="flex-1 min-w-0">
                <p :class="['text-sm font-bold truncate', player.active ? 'text-primary' : 'text-text-main']">
                  {{ player.name }}
                  <span v-if="!player.isAlive" class="text-red-500 ml-1">(已淘汰)</span>
                </p>
                <p class="text-[10px] text-slate-400 uppercase font-bold">
                  {{ player.type }} • {{ player.status }}
                </p>
              </div>
              <!-- 投票按钮 -->
              <button
                v-if="isMyVote && currentPhase === 'VOTING' && player.id !== userStore.user?.id && player.isAlive"
                @click="handleVote(player.id)"
                class="px-3 py-1.5 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600 font-bold transition-colors"
              >
                投票
              </button>
            </div>
          </div>
        </div>

        <!-- 游戏进度 -->
        <div v-if="gameState && currentPhase !== 'FINISHED'" class="mt-4">
          <GameProgress
            :phase="currentPhase"
            :current-player-name="currentSpeaker?.name"
            :current-player-index="currentSpeakerIndex"
            :total-players="alivePlayers.length"
            :is-a-i="currentSpeaker?.type === 'AI'"
          />
        </div>

        <!-- 开始游戏按钮 -->
        <div v-if="isOwner && !gameState" class="mt-4 pt-4 border-t border-border-light">
          <button
            @click="handleStartGame"
            :disabled="loading || (players.length < 3)"
            class="w-full py-3 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover disabled:opacity-50 transition-all"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <span class="material-symbols-outlined animate-spin">progress_activity</span>
              准备中...
            </span>
            <span v-else>开始游戏</span>
          </button>
          <p v-if="players.length < 3" class="text-xs text-amber-600 mt-2 text-center">
            至少需要 3 名玩家
          </p>
        </div>
      </aside>

      <!-- 中间游戏区域 -->
      <main class="flex-1 bg-bg-main p-8 overflow-y-auto">
        <div class="max-w-3xl mx-auto space-y-8">
          <!-- 秘密词卡片 -->
          <div class="bg-white p-12 rounded-[2.5rem] shadow-sm border border-border-light text-center relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-primary"></div>
            <div class="size-20 bg-accent-blue rounded-full flex items-center justify-center text-primary mx-auto mb-6">
              <span class="material-symbols-outlined text-4xl">
                {{ wordRevealed ? 'visibility' : 'visibility_off' }}
              </span>
            </div>
            <h3 class="text-xl font-bold mb-2">秘密词汇</h3>
            <p class="text-text-muted text-sm mb-8">这是你的秘密词汇。在投票阶段之前不要透露它。</p>

            <button
              v-if="!wordRevealed && gameState?.user_word"
              @click="wordRevealed = true"
              class="px-10 py-4 border-2 border-primary text-primary hover:bg-primary hover:text-white font-bold rounded-xl transition-all flex items-center gap-2 mx-auto"
            >
              <span class="material-symbols-outlined">lock_open</span> 点击查看词汇
            </button>
            <div v-else-if="wordRevealed && gameState?.user_word" class="space-y-4">
              <div class="text-4xl font-black text-primary tracking-widest">
                {{ gameState.user_word }}
              </div>
              <p class="text-sm text-text-muted">
                请用自己的方式描述这个词汇，不要直接说出来
              </p>
            </div>
            <div v-else class="text-text-muted">
              等待游戏开始...
            </div>
          </div>

          <!-- 发言输入框 -->
          <Transition
            enter-active-class="transition-all duration-300"
            enter-from-class="opacity-0 translate-y-4"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-200"
            leave-from-class="opacity-100"
            leave-to-class="opacity-0"
          >
            <div
              v-if="isMyTurn && currentPhase === 'SPEAKING'"
              class="bg-white p-6 rounded-2xl border-2 border-primary shadow-lg"
            >
              <div class="flex items-center gap-2 mb-4">
                <span class="material-symbols-outlined text-primary animate-pulse">mic</span>
                <h4 class="font-bold text-primary">轮到你发言了</h4>
              </div>
              <div class="flex gap-4">
                <input
                  v-model="speechInput"
                  class="flex-1 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none"
                  placeholder="描述你的词汇..."
                  @keyup.enter="handleSpeech"
                />
                <button
                  @click="handleSpeech"
                  :disabled="!speechInput.trim()"
                  class="px-6 py-3 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover disabled:opacity-50 transition-all"
                >
                  发言
                </button>
              </div>
            </div>
          </Transition>

          <!-- 等待其他玩家提示 -->
          <div
            v-if="currentPhase === 'SPEAKING' && !isMyTurn && currentSpeaker"
            class="bg-slate-50 p-6 rounded-2xl border border-slate-200 text-center"
          >
            <div class="flex items-center justify-center gap-3">
              <div
                :class="[
                  'w-10 h-10 rounded-full flex items-center justify-center',
                  currentSpeaker.type === 'AI' ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600'
                ]"
              >
                <span class="material-symbols-outlined">
                  {{ currentSpeaker.type === 'AI' ? 'smart_toy' : 'person' }}
                </span>
              </div>
              <p class="text-slate-600">
                <span class="font-bold">{{ currentSpeaker.name }}</span> 正在发言...
              </p>
              <div v-if="currentSpeaker.type === 'AI'" class="flex gap-1 ml-2">
                <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
              </div>
            </div>
          </div>

          <!-- 投票阶段提示 -->
          <div
            v-if="currentPhase === 'VOTING' && isMyVote"
            class="bg-amber-50 p-6 rounded-2xl border-2 border-amber-300 text-center"
          >
            <span class="material-symbols-outlined text-4xl text-amber-500 mb-2">how_to_vote</span>
            <h4 class="font-bold text-amber-700 mb-2">轮到你投票了</h4>
            <p class="text-amber-600 text-sm">请在左侧玩家列表中选择你认为的卧底</p>
          </div>

          <!-- 信息卡片 -->
          <div class="grid grid-cols-2 gap-4">
            <div class="p-6 bg-white border border-border-light rounded-2xl flex items-center gap-4">
              <span class="material-symbols-outlined text-primary">group</span>
              <div>
                <p class="text-xs font-bold text-slate-400 uppercase">存活玩家</p>
                <p class="text-sm font-bold">{{ alivePlayers.length }} / {{ players.length }} 人</p>
              </div>
            </div>
            <div class="p-6 bg-white border border-border-light rounded-2xl flex items-center gap-4">
              <span class="material-symbols-outlined text-primary">category</span>
              <div>
                <p class="text-xs font-bold text-slate-400 uppercase">当前回合</p>
                <p class="text-sm font-bold">第 {{ gameState?.round_number || 1 }} 轮</p>
              </div>
            </div>
          </div>

          <!-- 游戏结果 -->
          <Transition
            enter-active-class="transition-all duration-500"
            enter-from-class="opacity-0 scale-95"
            enter-to-class="opacity-100 scale-100"
          >
            <div v-if="currentPhase === 'FINISHED'" class="bg-white p-8 rounded-2xl border border-border-light">
              <div class="text-center mb-6">
                <span
                  :class="[
                    'material-symbols-outlined text-6xl mb-4',
                    gameState.winner_role === 'undercover' ? 'text-red-500' : 'text-green-500'
                  ]"
                >
                  emoji_events
                </span>
                <h3 class="text-2xl font-bold mb-2">游戏结束</h3>
                <p
                  :class="[
                    'text-xl font-bold px-6 py-2 rounded-full inline-block',
                    gameState.winner_role === 'undercover' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                  ]"
                >
                  {{ gameState.winner_role === 'undercover' ? '卧底获胜！' : '平民获胜！' }}
                </p>
              </div>

              <!-- 玩家身份揭晓 -->
              <div class="mt-6 border-t border-border-light pt-6">
                <h4 class="text-sm font-bold text-text-muted uppercase mb-4 text-center">身份揭晓</h4>
                <div class="grid grid-cols-2 gap-3">
                  <div
                    v-for="player in gameState.players"
                    :key="player.id"
                    :class="[
                      'p-3 rounded-xl border-2 flex items-center gap-3',
                      player.role === 'undercover'
                        ? 'bg-red-50 border-red-200'
                        : 'bg-green-50 border-green-200'
                    ]"
                  >
                    <div
                      :class="[
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        player.role === 'undercover' ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'
                      ]"
                    >
                      <span class="material-symbols-outlined">
                        {{ player.is_ai ? 'smart_toy' : 'person' }}
                      </span>
                    </div>
                    <div class="flex-1 min-w-0">
                      <p class="font-bold text-sm truncate">{{ player.username }}</p>
                      <div class="flex items-center gap-2">
                        <span
                          :class="[
                            'text-[10px] font-bold px-2 py-0.5 rounded',
                            player.role === 'undercover' ? 'bg-red-200 text-red-700' : 'bg-green-200 text-green-700'
                          ]"
                        >
                          {{ player.role === 'undercover' ? '卧底' : '平民' }}
                        </span>
                        <span class="text-[10px] text-text-muted">{{ player.word }}</span>
                      </div>
                    </div>
                    <span
                      v-if="!player.is_alive"
                      class="material-symbols-outlined text-slate-400 text-sm"
                      title="已淘汰"
                    >
                      cancel
                    </span>
                  </div>
                </div>
              </div>

              <div class="text-center mt-6">
                <button
                  @click="router.push('/lobby')"
                  class="px-8 py-3 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover"
                >
                  返回大厅
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </main>

      <!-- 右侧聊天区 -->
      <aside class="w-80 border-l border-border-light bg-white flex flex-col">
        <div class="p-4 border-b border-border-light flex justify-between items-center">
          <h3 class="text-sm font-bold">游戏发言</h3>
          <span
            :class="[
              'text-[10px] font-bold uppercase px-2 py-0.5 rounded-full',
              wsConnected ? 'bg-green-100 text-green-600' : 'bg-slate-100 text-slate-500'
            ]"
          >
            {{ wsConnected ? '实时' : '轮询' }}
          </span>
        </div>
        <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          <div class="bg-accent-blue p-3 rounded-2xl text-xs text-primary border border-primary/10">
            欢迎来到游戏房间。
          </div>

          <!-- 按轮次分组显示 -->
          <template v-for="round in displayRounds" :key="round">
            <div class="flex items-center gap-2 my-3">
              <div class="flex-1 h-px bg-slate-200"></div>
              <span class="text-[10px] text-slate-400 font-bold">第 {{ round }} 轮</span>
              <div class="flex-1 h-px bg-slate-200"></div>
            </div>

            <div
              v-for="(msg, index) in messages.filter(m => m.round === round)"
              :key="`${round}-${index}`"
              class="space-y-1"
            >
              <div
                :class="[
                  'p-3 rounded-2xl text-xs leading-relaxed',
                  msg.type === 'ai' ? 'bg-purple-50 border border-purple-100' : 'bg-slate-100'
                ]"
              >
                <div class="flex items-center gap-2 mb-1.5">
                  <span
                    :class="[
                      'material-symbols-outlined text-sm',
                      msg.type === 'ai' ? 'text-purple-500' : 'text-blue-500'
                    ]"
                  >
                    {{ msg.type === 'ai' ? 'smart_toy' : 'person' }}
                  </span>
                  <span
                    :class="[
                      'font-bold text-xs',
                      msg.type === 'ai' ? 'text-purple-600' : 'text-blue-600'
                    ]"
                  >{{ msg.sender }}</span>
                </div>
                <div class="text-text-main pl-5">{{ msg.text }}</div>
              </div>
            </div>

            <!-- 该轮投票记录 -->
            <div
              v-for="(vote, vIndex) in voteRecords.filter(v => v.roundNumber === round)"
              :key="`vote-${round}-${vIndex}`"
              class="flex items-center gap-2 text-xs py-1 px-2"
            >
              <span
                :class="[
                  'w-5 h-5 rounded-full flex items-center justify-center',
                  vote.isAi ? 'bg-violet-100 text-violet-500' : 'bg-amber-100 text-amber-500'
                ]"
              >
                <span class="material-symbols-outlined text-xs">{{ vote.isAi ? 'smart_toy' : 'person' }}</span>
              </span>
              <span class="text-slate-500">{{ vote.voterName }} 投票完毕</span>
            </div>
          </template>

          <div v-if="messages.length === 0" class="text-center text-text-muted text-sm py-8">
            暂无发言记录
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
