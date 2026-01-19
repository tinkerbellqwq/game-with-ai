import api from './index'

export interface RoomCreate {
  name: string
  max_players?: number
  ai_count?: number
  password?: string
  ai_template_ids?: string[]
  settings?: Record<string, any>
}

export interface RoomInfo {
  id: number
  name: string
  creator_id: number
  creator_name?: string
  max_players: number
  current_player_count: number
  ai_count: number
  has_password?: boolean
  status: 'waiting' | 'playing' | 'finished'
  created_at: string
}

export interface RoomDetail extends RoomInfo {
  players: {
    id: number
    username: string
    is_ai: boolean
    is_ready: boolean
  }[]
}

export interface RoomListResponse {
  rooms: RoomInfo[]
  total: number
  page: number
  page_size: number
}

// 获取房间列表
export const getRooms = (params?: { status?: string; page?: number; search?: string }) => {
  return api.get<RoomListResponse>('/rooms/', { params })
}

// 创建房间
export const createRoom = (data: RoomCreate) => {
  return api.post<RoomInfo>('/rooms/', data)
}

// 获取房间详情
export const getRoomDetail = (roomId: number) => {
  return api.get<RoomDetail>(`/rooms/${roomId}`)
}

// 加入房间
export const joinRoom = (roomId: number, password?: string) => {
  return api.post(`/rooms/${roomId}/join`, { password })
}

// 离开房间
export const leaveRoom = (roomId: number) => {
  return api.post(`/rooms/${roomId}/leave`)
}

// 房间操作 (开始游戏、踢人等)
export const roomAction = (roomId: number, action: string, payload?: any) => {
  return api.post(`/rooms/${roomId}/action`, { action, ...payload })
}

// 获取我创建的房间
export const getMyRooms = () => {
  return api.get<RoomInfo[]>('/rooms/my-rooms')
}

// 获取我加入的房间
export const getJoinedRooms = () => {
  return api.get<RoomInfo[]>('/rooms/joined-rooms')
}
