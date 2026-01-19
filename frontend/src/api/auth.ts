import api from './index'

export interface LoginParams {
  username: string
  password: string
}

export interface RegisterParams {
  username: string
  email: string
  password: string
}

export interface UserToken {
  access_token: string
  token_type: string
}

export interface UserProfile {
  id: number
  username: string
  email: string
  score: number
  games_played: number
  games_won: number
  created_at: string
}

// 登录
export const login = (params: LoginParams) => {
  return api.post<UserToken>('/auth/login', params)
}

// 注册
export const register = (params: RegisterParams) => {
  return api.post('/auth/register', params)
}

// 登出
export const logout = () => {
  return api.post('/auth/logout')
}

// 获取用户资料
export const getProfile = () => {
  return api.get<UserProfile>('/auth/profile')
}

// 验证 token
export const verifyToken = () => {
  return api.get('/auth/verify')
}

// 刷新会话
export const refreshSession = () => {
  return api.post('/auth/refresh')
}
