<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getAIPlayers, type AIPlayer } from '@/api/ai-players'

const emit = defineEmits<{
  close: []
  create: [data: {
    name: string
    max_players: number
    ai_count: number
    password?: string
    ai_template_ids?: string[]
  }]
}>()

const props = defineProps<{
  show: boolean
  userName?: string
}>()

// 表单状态
const roomName = ref('')
const maxPlayers = ref(4)
const aiCount = ref(2)
const password = ref('')
const usePassword = ref(false)
const aiSelectionMode = ref<'random' | 'specific'>('random')
const selectedAIs = ref<string[]>([])

// AI 列表
const aiPlayers = ref<AIPlayer[]>([])
const loadingAIs = ref(false)

// 创建中状态
const creating = ref(false)

// 可选的 AI 数量选项
const aiOptions = computed(() => {
  const max = maxPlayers.value - 1 // 至少留一个位置给真人玩家
  return Array.from({ length: max + 1 }, (_, i) => i)
})

// 验证表单
const isValid = computed(() => {
  if (!roomName.value.trim()) return false
  if (aiSelectionMode.value === 'specific' && selectedAIs.value.length !== aiCount.value) return false
  return true
})

// 获取 AI 列表
const fetchAIPlayers = async () => {
  loadingAIs.value = true
  try {
    const response = await getAIPlayers(true)
    aiPlayers.value = response.data.ai_players || []
  } catch {
    aiPlayers.value = []
  } finally {
    loadingAIs.value = false
  }
}

// 切换 AI 选择
const toggleAI = (id: string) => {
  const idx = selectedAIs.value.indexOf(id)
  if (idx >= 0) {
    selectedAIs.value.splice(idx, 1)
  } else if (selectedAIs.value.length < aiCount.value) {
    selectedAIs.value.push(id)
  }
}

// 提交创建
const handleCreate = () => {
  if (!isValid.value || creating.value) return

  creating.value = true

  const data: {
    name: string
    max_players: number
    ai_count: number
    password?: string
    ai_template_ids?: string[]
  } = {
    name: roomName.value.trim(),
    max_players: maxPlayers.value,
    ai_count: aiCount.value
  }

  if (usePassword.value && password.value.trim()) {
    data.password = password.value.trim()
  }

  if (aiSelectionMode.value === 'specific' && selectedAIs.value.length > 0) {
    data.ai_template_ids = selectedAIs.value
  }

  emit('create', data)
}

// 关闭模态框
const handleClose = () => {
  if (!creating.value) {
    emit('close')
  }
}

// 初始化
onMounted(() => {
  if (props.userName) {
    roomName.value = `${props.userName}的房间`
  }
  fetchAIPlayers()
})
</script>

<template>
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
        v-if="show"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        @click.self="handleClose"
      >
        <Transition
          enter-active-class="transition-all duration-300"
          enter-from-class="opacity-0 scale-95 translate-y-4"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition-all duration-200"
          leave-from-class="opacity-100 scale-100"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="show"
            class="bg-white rounded-3xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
          >
            <!-- 头部 -->
            <div class="p-6 border-b border-border-light bg-gradient-to-r from-primary/5 to-transparent">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <div class="w-10 h-10 rounded-xl bg-primary flex items-center justify-center text-white">
                    <span class="material-symbols-outlined">meeting_room</span>
                  </div>
                  <div>
                    <h3 class="text-lg font-bold">创建房间</h3>
                    <p class="text-xs text-text-muted">设置游戏参数并邀请好友</p>
                  </div>
                </div>
                <button
                  @click="handleClose"
                  :disabled="creating"
                  class="p-2 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
                >
                  <span class="material-symbols-outlined text-text-muted">close</span>
                </button>
              </div>
            </div>

            <!-- 表单内容 -->
            <div class="p-6 space-y-6 max-h-[60vh] overflow-y-auto custom-scrollbar">
              <!-- 房间名称 -->
              <div>
                <label class="block text-sm font-bold text-text-main mb-2">
                  房间名称
                </label>
                <input
                  v-model="roomName"
                  type="text"
                  class="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none transition-all"
                  placeholder="输入房间名称..."
                />
              </div>

              <!-- 玩家人数 -->
              <div>
                <label class="block text-sm font-bold text-text-main mb-2">
                  最大玩家数
                </label>
                <div class="flex gap-2">
                  <button
                    v-for="n in [3, 4, 5, 6]"
                    :key="n"
                    @click="maxPlayers = n; if(aiCount > n-1) aiCount = n-1"
                    :class="[
                      'flex-1 py-3 rounded-xl font-bold transition-all',
                      maxPlayers === n
                        ? 'bg-primary text-white shadow-lg shadow-primary/20'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    ]"
                  >
                    {{ n }} 人
                  </button>
                </div>
              </div>

              <!-- AI 数量 -->
              <div>
                <label class="block text-sm font-bold text-text-main mb-2">
                  AI 玩家数量
                  <span class="text-xs text-text-muted font-normal ml-1">(剩余位置给真人玩家)</span>
                </label>
                <div class="flex gap-2 flex-wrap">
                  <button
                    v-for="n in aiOptions"
                    :key="n"
                    @click="aiCount = n; if(n < selectedAIs.length) selectedAIs = selectedAIs.slice(0, n)"
                    :class="[
                      'px-4 py-2.5 rounded-xl font-bold transition-all',
                      aiCount === n
                        ? 'bg-purple-500 text-white shadow-lg shadow-purple-500/20'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    ]"
                  >
                    {{ n }}
                  </button>
                </div>
              </div>

              <!-- AI 选择模式 -->
              <div v-if="aiCount > 0">
                <label class="block text-sm font-bold text-text-main mb-2">
                  AI 选择方式
                </label>
                <div class="flex gap-3">
                  <button
                    @click="aiSelectionMode = 'random'"
                    :class="[
                      'flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all border-2',
                      aiSelectionMode === 'random'
                        ? 'bg-primary/10 border-primary text-primary'
                        : 'bg-slate-50 border-transparent text-slate-600 hover:bg-slate-100'
                    ]"
                  >
                    <span class="material-symbols-outlined text-lg">shuffle</span>
                    随机分配
                  </button>
                  <button
                    @click="aiSelectionMode = 'specific'"
                    :class="[
                      'flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all border-2',
                      aiSelectionMode === 'specific'
                        ? 'bg-primary/10 border-primary text-primary'
                        : 'bg-slate-50 border-transparent text-slate-600 hover:bg-slate-100'
                    ]"
                  >
                    <span class="material-symbols-outlined text-lg">checklist</span>
                    指定 AI
                  </button>
                </div>

                <!-- AI 列表 -->
                <div v-if="aiSelectionMode === 'specific'" class="mt-4">
                  <div v-if="loadingAIs" class="text-center py-4 text-text-muted">
                    <span class="material-symbols-outlined animate-spin">progress_activity</span>
                    <p class="text-sm mt-1">加载 AI 列表...</p>
                  </div>
                  <div v-else-if="aiPlayers.length === 0" class="text-center py-4 text-text-muted">
                    <span class="material-symbols-outlined text-3xl">smart_toy</span>
                    <p class="text-sm mt-1">暂无可用的 AI 玩家</p>
                    <p class="text-xs">请先在 AI 管理页面创建 AI</p>
                  </div>
                  <div v-else class="space-y-2">
                    <p class="text-xs text-text-muted mb-2">
                      已选择 {{ selectedAIs.length }}/{{ aiCount }} 个 AI
                    </p>
                    <div
                      v-for="ai in aiPlayers"
                      :key="ai.id"
                      @click="toggleAI(ai.id)"
                      :class="[
                        'p-3 rounded-xl border-2 cursor-pointer transition-all flex items-center gap-3',
                        selectedAIs.includes(ai.id)
                          ? 'bg-purple-50 border-purple-300'
                          : 'bg-slate-50 border-transparent hover:bg-slate-100'
                      ]"
                    >
                      <div
                        :class="[
                          'w-8 h-8 rounded-lg flex items-center justify-center',
                          selectedAIs.includes(ai.id) ? 'bg-purple-500 text-white' : 'bg-slate-200 text-slate-500'
                        ]"
                      >
                        <span class="material-symbols-outlined text-lg">smart_toy</span>
                      </div>
                      <div class="flex-1">
                        <p class="font-bold text-sm">{{ ai.name }}</p>
                        <p class="text-[10px] text-text-muted">
                          {{ ai.difficulty }} • {{ ai.personality }}
                        </p>
                      </div>
                      <span
                        v-if="selectedAIs.includes(ai.id)"
                        class="material-symbols-outlined text-purple-500"
                      >
                        check_circle
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 房间密码 -->
              <div>
                <div class="flex items-center justify-between mb-2">
                  <label class="text-sm font-bold text-text-main">房间密码</label>
                  <button
                    @click="usePassword = !usePassword"
                    :class="[
                      'relative w-11 h-6 rounded-full transition-all',
                      usePassword ? 'bg-primary' : 'bg-slate-300'
                    ]"
                  >
                    <span
                      :class="[
                        'absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-all',
                        usePassword ? 'left-[22px]' : 'left-0.5'
                      ]"
                    />
                  </button>
                </div>
                <Transition
                  enter-active-class="transition-all duration-200"
                  enter-from-class="opacity-0 -translate-y-2"
                  enter-to-class="opacity-100 translate-y-0"
                  leave-active-class="transition-all duration-150"
                  leave-from-class="opacity-100"
                  leave-to-class="opacity-0"
                >
                  <input
                    v-if="usePassword"
                    v-model="password"
                    type="text"
                    class="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-primary/20 outline-none transition-all"
                    placeholder="设置房间密码（可选）"
                  />
                </Transition>
                <p class="text-xs text-text-muted mt-1">
                  {{ usePassword ? '只有知道密码的玩家才能加入' : '任何人都可以加入房间' }}
                </p>
              </div>
            </div>

            <!-- 底部按钮 -->
            <div class="p-6 border-t border-border-light bg-slate-50 flex gap-3">
              <button
                @click="handleClose"
                :disabled="creating"
                class="flex-1 py-3 bg-white border border-slate-200 text-slate-600 font-bold rounded-xl hover:bg-slate-100 transition-all disabled:opacity-50"
              >
                取消
              </button>
              <button
                @click="handleCreate"
                :disabled="!isValid || creating"
                class="flex-1 py-3 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover disabled:opacity-50 transition-all flex items-center justify-center gap-2"
              >
                <span v-if="creating" class="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                <span>{{ creating ? '创建中...' : '创建房间' }}</span>
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
