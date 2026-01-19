export interface Player {
  id: string
  name: string
  type: 'Human' | 'AI'
  status: 'Ready' | 'Syncing' | 'Waiting' | 'Eliminated' | 'Speaking'
  avatar: string
}

export interface Message {
  id: string
  sender: string
  senderAvatar?: string
  text: string
  type: 'system' | 'user' | 'ai'
  timestamp: string
}

export interface Room {
  id: string
  name: string
  players: Player[]
  maxPlayers: number
  status: 'waiting' | 'playing' | 'finished'
}

export interface User {
  id: string
  username: string
  email: string
  avatar?: string
  level: number
  winRate: number
  gamesPlayed: number
  totalWins: number
}
