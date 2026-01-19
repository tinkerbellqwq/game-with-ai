import api from './index'

export interface LeaderboardEntry {
  rank: number
  user_id: number
  username: string
  score: number
  games_played: number
  games_won: number
  win_rate: number
  last_game_at?: string
  is_ai?: boolean
}

export interface LeaderboardResponse {
  entries: LeaderboardEntry[]
  total: number
  page: number
  page_size: number
}

export interface UserRankInfo {
  user_id: number
  username: string
  current_rank: number
  score: number
  games_played: number
  games_won: number
  win_rate: number
  rank_change?: number
}

export interface PersonalStats {
  user_id: number
  username: string
  score: number
  games_played: number
  games_won: number
  games_lost: number
  win_rate: number
  spy_games: number
  spy_wins: number
  civilian_games: number
  civilian_wins: number
  recent_games: any[]
}

// 获取排行榜
export const getLeaderboard = (page = 1, sortBy = 'score', order = 'desc') => {
  return api.get<LeaderboardResponse>('/leaderboard/', {
    params: { page, sort_by: sortBy, order }
  })
}

// 获取当前用户排名
export const getMyRank = () => {
  return api.get<UserRankInfo>('/leaderboard/my-rank')
}

// 获取指定用户排名
export const getUserRank = (userId: number) => {
  return api.get<UserRankInfo>(`/leaderboard/user/${userId}/rank`)
}

// 获取当前用户统计
export const getMyStats = () => {
  return api.get<PersonalStats>('/leaderboard/my-stats')
}

// 获取指定用户统计
export const getUserStats = (userId: number) => {
  return api.get<PersonalStats>(`/leaderboard/user/${userId}/stats`)
}
