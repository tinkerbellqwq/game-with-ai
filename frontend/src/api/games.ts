import api from './index'

export interface GamePlayer {
  id: string
  username: string
  is_ai: boolean
  is_alive: boolean
  is_ready: boolean
}

export interface VoteInfo {
  voter_id: string
  voter_name: string
  target_id: string
  is_ai: boolean
}

export interface VoteResultData {
  target_id: string
  target_name: string
  vote_count: number
  is_eliminated: boolean
  voters: VoteInfo[]
}

export interface GameState {
  id: string
  room_id: string
  current_phase: 'WAITING' | 'PREPARING' | 'SPEAKING' | 'VOTING' | 'RESULT' | 'FINISHED'
  round_number: number
  current_speaker?: string
  current_speaker_username?: string
  current_speaker_id?: string  // 兼容旧版
  current_voter?: string  // 后端返回
  current_voter_id?: string  // 兼容
  current_voter_username?: string
  alive_players: string[]
  eliminated_players: string[]
  players: GamePlayer[]
  winner_role?: 'civilian' | 'undercover'
  winner_players?: string[]
  user_role?: string
  user_word?: string
  // 投票结果（投票阶段结束后）
  last_vote_results?: VoteResultData[]
  last_eliminated_player?: string
  last_eliminated_player_name?: string
}

export interface Speech {
  id: number
  player_id: number
  player_name: string
  content: string
  round_number: number
  created_at: string
}

export interface GameResult {
  winner_role: string
  winner_players: { id: number; username: string }[]
  loser_players: { id: number; username: string }[]
  score_changes: { user_id: number; change: number }[]
}

// 创建游戏
export const createGame = (roomId: number, difficulty?: string) => {
  return api.post('/games/', { room_id: roomId, difficulty })
}

// 开始游戏
export const startGame = (gameId: number) => {
  return api.post(`/games/${gameId}/start`)
}

// 获取游戏状态
export const getGameState = (gameId: number) => {
  return api.get<GameState>(`/games/${gameId}`)
}

// 玩家准备
export const playerReady = (gameId: number, ready = true) => {
  return api.post(`/games/${gameId}/ready`, null, { params: { ready } })
}

// 提交发言
export const submitSpeech = (gameId: number, content: string) => {
  return api.post(`/games/${gameId}/speech`, { content })
}

// 提交投票
export const submitVote = (gameId: number, targetId: number) => {
  return api.post(`/games/${gameId}/vote`, { target_id: targetId })
}

// 获取游戏结果
export const getGameResult = (gameId: number) => {
  return api.get<GameResult>(`/games/${gameId}/result`)
}

// 获取发言记录
export const getSpeeches = (gameId: number, roundNumber?: number) => {
  return api.get<{ speeches: Speech[] }>(`/games/${gameId}/speeches`, {
    params: roundNumber ? { round_number: roundNumber } : {}
  })
}

// 手动触发 AI
export const triggerAI = (gameId: number) => {
  return api.post(`/games/${gameId}/trigger-ai`)
}
