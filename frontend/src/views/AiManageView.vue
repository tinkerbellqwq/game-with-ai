<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getAIPlayers,
  createAIPlayer,
  updateAIPlayer,
  deleteAIPlayer,
  toggleAIPlayerStatus,
  getAvailableModels,
  testAIPlayerAPI,
  type AIPlayer,
  type CreateAIPlayerParams,
  type ModelInfo
} from '@/api/ai-players'

const router = useRouter()

const aiPlayers = ref<AIPlayer[]>([])
const loading = ref(false)
const showModal = ref(false)
const modalMode = ref<'create' | 'edit'>('create')
const editingPlayer = ref<AIPlayer | null>(null)
const showActiveOnly = ref(false)

// 表单数据
const formData = ref<CreateAIPlayerParams>({
  name: '',
  model_name: '',
  difficulty: 'normal',
  personality: 'normal',
  api_base_url: '',
  api_key: '',
  is_active: true
})

const errorMsg = ref('')
const successMsg = ref('')

// 测试状态管理
const testingPlayers = ref<Set<string>>(new Set())
const testResults = ref<Map<string, { success: boolean; message: string; latency?: number }>>(new Map())

// 可用模型列表（动态加载）
const availableModels = ref<ModelInfo[]>([])
const modelsLoading = ref(false)
const modelsSource = ref<'api' | 'config'>('config')

const difficultyOptions = [
  { value: 'beginner', label: '初级', color: 'bg-green-100 text-green-700' },
  { value: 'normal', label: '普通', color: 'bg-blue-100 text-blue-700' },
  { value: 'expert', label: '专家', color: 'bg-purple-100 text-purple-700' }
]

const personalityOptions = [
  { value: 'cautious', label: '谨慎', desc: '保守策略，发言小心' },
  { value: 'normal', label: '普通', desc: '平衡策略，正常发挥' },
  { value: 'aggressive', label: '激进', desc: '大胆发言，主动进攻' },
  { value: 'random', label: '随机', desc: '不可预测，随机行为' }
]

const getDifficultyClass = (difficulty: string) => {
  const option = difficultyOptions.find(o => o.value === difficulty)
  return option?.color || 'bg-slate-100 text-slate-700'
}

const getDifficultyLabel = (difficulty: string) => {
  const option = difficultyOptions.find(o => o.value === difficulty)
  return option?.label || difficulty
}

const getPersonalityLabel = (personality: string) => {
  const option = personalityOptions.find(o => o.value === personality)
  return option?.label || personality
}

const formatWinRate = (rate: number) => {
  return `${rate.toFixed(1)}%`
}

// 获取可用模型列表
const fetchAvailableModels = async (useFormConfig = false) => {
  modelsLoading.value = true
  try {
    let apiBaseUrl: string | undefined
    let apiKey: string | undefined
    let aiPlayerId: string | undefined

    if (useFormConfig) {
      // 编辑模式下，传递 AI 玩家 ID 让后端从数据库获取完整配置
      if (modalMode.value === 'edit' && editingPlayer.value) {
        aiPlayerId = editingPlayer.value.id
        console.log('Edit mode: using AI player ID:', aiPlayerId)
      }

      // 同时传递表单中的配置（用于新建模式或覆盖）
      apiBaseUrl = formData.value.api_base_url || undefined
      apiKey = formData.value.api_key || undefined
      console.log('Using form config:', { apiBaseUrl, apiKey: apiKey ? '***' : undefined })
    }

    const response = await getAvailableModels(apiBaseUrl, apiKey, aiPlayerId)
    availableModels.value = response.data.models || []
    modelsSource.value = response.data.source
    console.log('Models fetched:', { total: response.data.total, source: response.data.source })
  } catch (err) {
    console.error('Failed to fetch models:', err)
    availableModels.value = []
  } finally {
    modelsLoading.value = false
  }
}

// 使用当前表单配置刷新模型列表
const refreshModelsWithFormConfig = () => {
  // 总是使用表单配置，后端会处理空值情况
  fetchAvailableModels(true)
}

const fetchAIPlayers = async () => {
  loading.value = true
  try {
    const response = await getAIPlayers(showActiveOnly.value)
    aiPlayers.value = response.data.ai_players || []
  } catch {
    aiPlayers.value = []
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  modalMode.value = 'create'
  editingPlayer.value = null
  formData.value = {
    name: '',
    model_name: '',
    difficulty: 'normal',
    personality: 'normal',
    api_base_url: '',
    api_key: '',
    is_active: true
  }
  errorMsg.value = ''
  successMsg.value = ''
  showModal.value = true
}

const openEditModal = (player: AIPlayer) => {
  modalMode.value = 'edit'
  editingPlayer.value = player
  formData.value = {
    name: player.name,
    model_name: player.model_name || '',
    difficulty: player.difficulty,
    personality: player.personality,
    api_base_url: player.api_base_url || '',
    api_key: player.api_key || '',
    is_active: player.is_active
  }
  errorMsg.value = ''
  successMsg.value = ''
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  editingPlayer.value = null
}

const handleSubmit = async () => {
  errorMsg.value = ''
  successMsg.value = ''

  if (!formData.value.name.trim()) {
    errorMsg.value = '请输入 AI 名称'
    return
  }

  if (!formData.value.model_name) {
    errorMsg.value = '请选择模型'
    return
  }

  try {
    if (modalMode.value === 'create') {
      await createAIPlayer(formData.value)
      successMsg.value = 'AI 玩家创建成功'
    } else if (editingPlayer.value) {
      await updateAIPlayer(editingPlayer.value.id, formData.value)
      successMsg.value = 'AI 玩家更新成功'
    }
    await fetchAIPlayers()
    setTimeout(() => {
      closeModal()
    }, 1000)
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || '操作失败'
  }
}

const handleDelete = async (player: AIPlayer) => {
  if (!confirm(`确定要删除 AI 玩家「${player.name}」吗？`)) return

  try {
    await deleteAIPlayer(player.id)
    await fetchAIPlayers()
  } catch (err: any) {
    alert(err.response?.data?.detail || '删除失败')
  }
}

const handleToggleStatus = async (player: AIPlayer) => {
  try {
    await toggleAIPlayerStatus(player.id)
    await fetchAIPlayers()
  } catch (err: any) {
    alert(err.response?.data?.detail || '切换状态失败')
  }
}

// 测试 AI 玩家 API 可用性
const handleTestAPI = async (player: AIPlayer) => {
  testingPlayers.value.add(player.id)
  testResults.value.delete(player.id)

  try {
    const response = await testAIPlayerAPI(player.id)
    testResults.value.set(player.id, {
      success: response.data.success,
      message: response.data.message,
      latency: response.data.latency_ms
    })
  } catch (err: any) {
    testResults.value.set(player.id, {
      success: false,
      message: err.response?.data?.detail || '测试请求失败'
    })
  } finally {
    testingPlayers.value.delete(player.id)
  }
}

const goBack = () => {
  router.push('/lobby')
}

onMounted(() => {
  fetchAIPlayers()
  fetchAvailableModels()
})
</script>

<template>
  <div class="min-h-screen bg-bg-main overflow-x-hidden">
    <!-- 顶部导航 -->
    <header class="flex items-center justify-between border-b border-border-light px-10 py-4 sticky top-0 bg-white/90 backdrop-blur-md z-50">
      <div class="flex items-center gap-2 text-primary">
        <span class="material-symbols-outlined text-3xl font-bold">smart_toy</span>
        <h2 class="text-text-main text-xl font-extrabold tracking-tight">AI 玩家管理</h2>
      </div>
      <div class="flex items-center gap-4">
        <button
          @click="openCreateModal"
          class="flex items-center gap-2 px-5 py-2 bg-primary text-white rounded-xl text-sm font-bold hover:bg-primary-hover transition-all"
        >
          <span class="material-symbols-outlined text-lg">add</span> 新建 AI
        </button>
        <button
          @click="goBack"
          class="flex items-center gap-2 px-5 py-2 bg-white border border-border-light rounded-xl text-sm font-bold hover:bg-slate-50 transition-all"
        >
          <span class="material-symbols-outlined text-lg">arrow_back</span> 返回大厅
        </button>
      </div>
    </header>

    <main class="max-w-[1200px] mx-auto w-full px-6 py-12">
      <!-- 统计卡片 -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-8">
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">AI 总数</p>
            <span class="material-symbols-outlined text-primary">groups</span>
          </div>
          <p class="text-3xl font-bold">{{ aiPlayers.length }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">激活数量</p>
            <span class="material-symbols-outlined text-green-500">check_circle</span>
          </div>
          <p class="text-3xl font-bold">{{ aiPlayers.filter(p => p.is_active).length }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">总对局数</p>
            <span class="material-symbols-outlined text-blue-500">sports_esports</span>
          </div>
          <p class="text-3xl font-bold">{{ aiPlayers.reduce((sum, p) => sum + p.games_played, 0) }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">平均胜率</p>
            <span class="material-symbols-outlined text-purple-500">trending_up</span>
          </div>
          <p class="text-3xl font-bold">
            {{ aiPlayers.length > 0 ? formatWinRate(aiPlayers.reduce((sum, p) => sum + p.win_rate, 0) / aiPlayers.length) : '0%' }}
          </p>
        </div>
      </div>

      <!-- 筛选控制 -->
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-bold">AI 玩家列表</h3>
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            v-model="showActiveOnly"
            @change="fetchAIPlayers"
            class="w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary"
          />
          <span class="text-sm text-text-muted">仅显示激活的</span>
        </label>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="flex justify-center py-20">
        <span class="material-symbols-outlined text-4xl text-primary animate-spin">progress_activity</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="aiPlayers.length === 0" class="text-center py-20 bg-white rounded-2xl border border-border-light">
        <span class="material-symbols-outlined text-6xl text-slate-300 mb-4">smart_toy</span>
        <p class="text-lg text-text-muted mb-4">暂无 AI 玩家</p>
        <button
          @click="openCreateModal"
          class="px-6 py-2 bg-primary text-white rounded-xl font-bold hover:bg-primary-hover"
        >
          创建第一个 AI
        </button>
      </div>

      <!-- AI 玩家列表 -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="player in aiPlayers"
          :key="player.id"
          class="bg-white rounded-2xl border border-border-light p-6 hover:border-primary/30 transition-all cursor-pointer"
        >
          <!-- 头部 -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex items-center gap-3">
              <div
                :class="[
                  'w-12 h-12 rounded-xl flex items-center justify-center',
                  player.is_active ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'
                ]"
              >
                <span class="material-symbols-outlined text-2xl">smart_toy</span>
              </div>
              <div>
                <h4 class="font-bold text-lg">{{ player.name }}</h4>
                <p class="text-xs text-text-muted">{{ player.model_name || '未配置模型' }}</p>
              </div>
            </div>
            <div
              :class="[
                'w-3 h-3 rounded-full',
                player.is_active ? 'bg-green-500' : 'bg-slate-300'
              ]"
              :title="player.is_active ? '激活' : '未激活'"
            ></div>
          </div>

          <!-- 标签 -->
          <div class="flex flex-wrap gap-2 mb-4">
            <span :class="['px-2 py-1 rounded text-[10px] font-bold uppercase', getDifficultyClass(player.difficulty)]">
              {{ getDifficultyLabel(player.difficulty) }}
            </span>
            <span class="px-2 py-1 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-600">
              {{ getPersonalityLabel(player.personality) }}
            </span>
          </div>

          <!-- 统计 -->
          <div class="grid grid-cols-3 gap-2 mb-4 py-3 border-t border-b border-border-light">
            <div class="text-center">
              <p class="text-xs text-text-muted">对局</p>
              <p class="font-bold">{{ player.games_played }}</p>
            </div>
            <div class="text-center">
              <p class="text-xs text-text-muted">胜利</p>
              <p class="font-bold text-green-600">{{ player.games_won }}</p>
            </div>
            <div class="text-center">
              <p class="text-xs text-text-muted">胜率</p>
              <p class="font-bold text-primary">{{ formatWinRate(player.win_rate) }}</p>
            </div>
          </div>

          <!-- 测试结果提示 -->
          <div
            v-if="testResults.get(player.id)"
            :class="[
              'mb-3 p-2 rounded-lg text-xs',
              testResults.get(player.id)?.success
                ? 'bg-green-50 text-green-700 border border-green-200'
                : 'bg-red-50 text-red-700 border border-red-200'
            ]"
          >
            <div class="flex items-center gap-1">
              <span class="material-symbols-outlined text-sm">
                {{ testResults.get(player.id)?.success ? 'check_circle' : 'error' }}
              </span>
              <span class="font-medium">{{ testResults.get(player.id)?.message }}</span>
              <span v-if="testResults.get(player.id)?.latency" class="text-slate-500 ml-auto">
                {{ testResults.get(player.id)?.latency }}ms
              </span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-2">
            <button
              @click="handleTestAPI(player)"
              :disabled="testingPlayers.has(player.id)"
              class="py-2 px-3 bg-blue-100 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-200 transition-colors disabled:opacity-50 flex items-center gap-1"
              title="测试 API 可用性"
            >
              <span class="material-symbols-outlined text-sm" :class="{ 'animate-spin': testingPlayers.has(player.id) }">
                {{ testingPlayers.has(player.id) ? 'progress_activity' : 'network_check' }}
              </span>
            </button>
            <button
              @click="openEditModal(player)"
              class="flex-1 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors flex items-center justify-center gap-1"
            >
              <span class="material-symbols-outlined text-sm">edit</span> 编辑
            </button>
            <button
              @click="handleToggleStatus(player)"
              :class="[
                'flex-1 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-1',
                player.is_active
                  ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                  : 'bg-green-100 text-green-700 hover:bg-green-200'
              ]"
            >
              <span class="material-symbols-outlined text-sm">{{ player.is_active ? 'pause' : 'play_arrow' }}</span>
              {{ player.is_active ? '停用' : '启用' }}
            </button>
            <button
              @click="handleDelete(player)"
              class="py-2 px-3 bg-red-100 text-red-600 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors"
            >
              <span class="material-symbols-outlined text-sm">delete</span>
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 模态框 -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <!-- 遮罩 -->
        <div class="absolute inset-0 bg-black/50" @click="closeModal"></div>

        <!-- 弹窗内容 -->
        <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <div class="p-6 border-b border-border-light flex items-center justify-between">
            <h3 class="text-xl font-bold">{{ modalMode === 'create' ? '新建 AI 玩家' : '编辑 AI 玩家' }}</h3>
            <button @click="closeModal" class="p-2 hover:bg-slate-100 rounded-lg transition-colors">
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>

          <form @submit.prevent="handleSubmit" class="p-6 space-y-5">
            <!-- 错误/成功提示 -->
            <div v-if="errorMsg" class="p-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
              {{ errorMsg }}
            </div>
            <div v-if="successMsg" class="p-3 bg-green-50 border border-green-200 rounded-xl text-green-600 text-sm">
              {{ successMsg }}
            </div>

            <!-- AI 名称 -->
            <div class="space-y-2">
              <label class="text-sm font-semibold text-slate-700">AI 名称 *</label>
              <input
                v-model="formData.name"
                type="text"
                class="w-full px-4 h-12 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-primary/20"
                placeholder="例如：智能助手 Alpha"
                required
              />
            </div>

            <!-- API 配置 -->
            <div class="space-y-4 pt-4 border-t border-border-light">
              <div class="flex items-center justify-between">
                <p class="text-sm font-semibold text-slate-700">API 配置（可选，留空使用默认）</p>
              </div>

              <div class="space-y-2">
                <label class="text-xs text-text-muted">API Base URL</label>
                <input
                  v-model="formData.api_base_url"
                  type="text"
                  class="w-full px-4 h-10 bg-slate-50 border border-slate-200 rounded-lg outline-none text-sm"
                  placeholder="https://api.openai.com/v1"
                />
              </div>

              <div class="space-y-2">
                <label class="text-xs text-text-muted">API Key</label>
                <input
                  v-model="formData.api_key"
                  type="password"
                  class="w-full px-4 h-10 bg-slate-50 border border-slate-200 rounded-lg outline-none text-sm"
                  placeholder="sk-..."
                />
              </div>

              <button
                type="button"
                @click="refreshModelsWithFormConfig"
                :disabled="modelsLoading"
                class="w-full py-2 bg-slate-100 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-200 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span class="material-symbols-outlined text-sm" :class="{ 'animate-spin': modelsLoading }">
                  {{ modelsLoading ? 'progress_activity' : 'refresh' }}
                </span>
                {{ modelsLoading ? '获取中...' : '获取可用模型' }}
              </button>
            </div>

            <!-- 模型选择 -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-semibold text-slate-700">LLM 模型 *</label>
                <span v-if="modelsSource === 'api'" class="text-[10px] text-green-600 font-bold">API 实时获取</span>
                <span v-else class="text-[10px] text-slate-400 font-bold">配置文件</span>
              </div>
              <div class="relative">
                <select
                  v-model="formData.model_name"
                  class="w-full px-4 h-12 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-primary/20"
                  :disabled="modelsLoading"
                  required
                >
                  <option value="">{{ modelsLoading ? '加载中...' : '请选择模型' }}</option>
                  <option v-for="model in availableModels" :key="model.id" :value="model.id">
                    {{ model.name }}
                  </option>
                </select>
                <span v-if="modelsLoading" class="absolute right-4 top-1/2 -translate-y-1/2">
                  <span class="material-symbols-outlined text-slate-400 animate-spin text-lg">progress_activity</span>
                </span>
              </div>
              <p class="text-xs text-text-muted">共 {{ availableModels.length }} 个可用模型</p>
            </div>

            <!-- 难度选择 -->
            <div class="space-y-2">
              <label class="text-sm font-semibold text-slate-700">难度等级</label>
              <div class="flex gap-3">
                <label
                  v-for="option in difficultyOptions"
                  :key="option.value"
                  class="flex-1 cursor-pointer"
                >
                  <input
                    type="radio"
                    v-model="formData.difficulty"
                    :value="option.value"
                    class="sr-only peer"
                  />
                  <div class="p-3 border-2 border-slate-200 rounded-xl text-center transition-all peer-checked:border-primary peer-checked:bg-primary/5">
                    <span :class="['px-2 py-0.5 rounded text-xs font-bold', option.color]">
                      {{ option.label }}
                    </span>
                  </div>
                </label>
              </div>
            </div>

            <!-- 性格选择 -->
            <div class="space-y-2">
              <label class="text-sm font-semibold text-slate-700">AI 性格</label>
              <div class="grid grid-cols-2 gap-3">
                <label
                  v-for="option in personalityOptions"
                  :key="option.value"
                  class="cursor-pointer"
                >
                  <input
                    type="radio"
                    v-model="formData.personality"
                    :value="option.value"
                    class="sr-only peer"
                  />
                  <div class="p-3 border-2 border-slate-200 rounded-xl transition-all peer-checked:border-primary peer-checked:bg-primary/5">
                    <p class="font-medium text-sm">{{ option.label }}</p>
                    <p class="text-xs text-text-muted">{{ option.desc }}</p>
                  </div>
                </label>
              </div>
            </div>

            <!-- 激活状态 -->
            <div class="flex items-center justify-between pt-4 border-t border-border-light">
              <div>
                <p class="font-medium text-sm">激活状态</p>
                <p class="text-xs text-text-muted">停用的 AI 不会参与游戏匹配</p>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" v-model="formData.is_active" class="sr-only peer" />
                <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>

            <!-- 提交按钮 -->
            <div class="flex gap-3 pt-4">
              <button
                type="button"
                @click="closeModal"
                class="flex-1 py-3 bg-slate-100 text-slate-700 font-bold rounded-xl hover:bg-slate-200 transition-colors"
              >
                取消
              </button>
              <button
                type="submit"
                class="flex-1 py-3 bg-primary text-white font-bold rounded-xl hover:bg-primary-hover transition-colors"
              >
                {{ modalMode === 'create' ? '创建' : '保存' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>
