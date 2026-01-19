import api from './index'

// === 类型定义 ===

export interface WordPair {
  id: string
  civilian_word: string
  undercover_word: string
  category: string
  difficulty: number
  created_at: string
  updated_at: string
}

export interface WordPairListResponse {
  word_pairs: WordPair[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}

export interface WordPairCreateParams {
  civilian_word: string
  undercover_word: string
  category: string
  difficulty: number
}

export interface WordPairUpdateParams {
  civilian_word?: string
  undercover_word?: string
  category?: string
  difficulty?: number
}

export interface WordPairStats {
  total_pairs: number
  categories: Array<{
    category: string
    count: number
    difficulties: number[]
  }>
  difficulty_distribution: Record<number, number>
}

export interface BatchCreateResult {
  created: number
  skipped: number
  errors: string[]
  message: string
}

// === API 函数 ===

// 获取管理员 token
const getAdminToken = () => localStorage.getItem('adminToken') || ''

// 添加管理员 token 到请求头
const withAdminAuth = () => ({
  headers: {
    'X-Admin-Token': getAdminToken()
  }
})

// 管理员登录
export const adminLogin = (password: string) =>
  api.post('/admin/login', { password })

// 获取词汇对列表
export const getWordPairs = (params?: {
  page?: number
  page_size?: number
  category?: string
  difficulty?: number
  search?: string
}) =>
  api.get<WordPairListResponse>('/admin/words', {
    params,
    ...withAdminAuth()
  })

// 获取词汇对统计
export const getWordPairStats = () =>
  api.get<WordPairStats>('/admin/words/stats', withAdminAuth())

// 获取所有类别
export const getWordCategories = () =>
  api.get<{ categories: string[] }>('/admin/words/categories', withAdminAuth())

// 创建词汇对
export const createWordPair = (data: WordPairCreateParams) =>
  api.post<WordPair>('/admin/words', data, withAdminAuth())

// 批量创建词汇对
export const batchCreateWordPairs = (wordPairs: WordPairCreateParams[]) =>
  api.post<BatchCreateResult>('/admin/words/batch', { word_pairs: wordPairs }, withAdminAuth())

// 更新词汇对
export const updateWordPair = (id: string, data: WordPairUpdateParams) =>
  api.put<WordPair>(`/admin/words/${id}`, data, withAdminAuth())

// 删除词汇对
export const deleteWordPair = (id: string) =>
  api.delete(`/admin/words/${id}`, withAdminAuth())

// 批量删除词汇对
export const batchDeleteWordPairs = (ids: string[]) =>
  api.delete('/admin/words/batch', { data: ids, ...withAdminAuth() })
