import api from './index'

export interface AIPlayer {
  id: string
  name: string
  model_name: string | null
  difficulty: 'beginner' | 'normal' | 'expert'
  personality: 'cautious' | 'aggressive' | 'normal' | 'random'
  games_played: number
  games_won: number
  win_rate: number
  is_active: boolean
  api_base_url?: string
  api_key?: string
}

export interface AIPlayerListResponse {
  ai_players: AIPlayer[]
  total: number
}

export interface CreateAIPlayerParams {
  name: string
  model_name: string
  difficulty: string
  personality: string
  api_base_url?: string
  api_key?: string
  is_active?: boolean
}

export interface UpdateAIPlayerParams {
  name?: string
  model_name?: string
  difficulty?: string
  personality?: string
  api_base_url?: string
  api_key?: string
  is_active?: boolean
}

// 获取 AI 玩家列表
export const getAIPlayers = (activeOnly = false) => {
  return api.get<AIPlayerListResponse>('/ai-players/', {
    params: { active_only: activeOnly }
  })
}

// 获取单个 AI 玩家
export const getAIPlayer = (id: string) => {
  return api.get<AIPlayer>(`/ai-players/${id}`)
}

// 创建 AI 玩家
export const createAIPlayer = (params: CreateAIPlayerParams) => {
  return api.post<AIPlayer>('/ai-players/', params)
}

// 更新 AI 玩家
export const updateAIPlayer = (id: string, params: UpdateAIPlayerParams) => {
  return api.put<AIPlayer>(`/ai-players/${id}`, params)
}

// 删除 AI 玩家
export const deleteAIPlayer = (id: string) => {
  return api.delete(`/ai-players/${id}`)
}

// 切换 AI 玩家状态
export const toggleAIPlayerStatus = (id: string) => {
  return api.post<AIPlayer>(`/ai-players/${id}/toggle-status`)
}

// 模型信息
export interface ModelInfo {
  id: string
  name: string
  owned_by: string | null
}

export interface AvailableModelsResponse {
  models: ModelInfo[]
  total: number
  source: 'api' | 'config'
}

// 测试 AI 玩家 API 可用性响应
export interface TestAPIResponse {
  success: boolean
  message: string
  latency_ms?: number
  model_response?: string
}

// 测试 AI 玩家 API 可用性
export const testAIPlayerAPI = (id: string) => {
  return api.post<TestAPIResponse>(`/ai-players/${id}/test-api`)
}

// 获取可用模型列表（使用指定的 API 配置或 AI 玩家 ID）
export const getAvailableModels = (apiBaseUrl?: string, apiKey?: string, aiPlayerId?: string) => {
  const payload: { api_base_url?: string; api_key?: string; ai_player_id?: string } = {}

  // 如果提供了 AI 玩家 ID，优先使用（编辑模式下从数据库获取完整配置）
  if (aiPlayerId) {
    payload.ai_player_id = aiPlayerId
  }

  // 只有非空字符串才添加到请求体
  if (apiBaseUrl && apiBaseUrl.trim()) {
    payload.api_base_url = apiBaseUrl.trim()
  }
  if (apiKey && apiKey.trim()) {
    payload.api_key = apiKey.trim()
  }

  console.log('Fetching models with config:', {
    api_base_url: payload.api_base_url,
    api_key: payload.api_key ? '***' : undefined,
    ai_player_id: payload.ai_player_id
  })

  return api.post<AvailableModelsResponse>('/ai-players/fetch-models', payload)
}
