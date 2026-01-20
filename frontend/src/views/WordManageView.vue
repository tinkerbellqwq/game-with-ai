<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getWordPairs,
  getWordPairStats,
  getWordCategories,
  createWordPair,
  updateWordPair,
  deleteWordPair,
  batchCreateWordPairs,
  adminLogin,
  type WordPair,
  type WordPairCreateParams,
  type WordPairStats
} from '@/api/words'

const router = useRouter()

// 状态
const wordPairs = ref<WordPair[]>([])
const stats = ref<WordPairStats | null>(null)
const categories = ref<string[]>([])
const loading = ref(false)
const showModal = ref(false)
const showBatchModal = ref(false)
const showLoginModal = ref(false)
const modalMode = ref<'create' | 'edit'>('create')
const editingWord = ref<WordPair | null>(null)

// 管理员认证
const isAdminAuthenticated = ref(false)
const adminPassword = ref('')
const loginError = ref('')

// 分页和筛选
const currentPage = ref(1)
const pageSize = ref(20)
const totalItems = ref(0)
const hasNext = ref(false)
const filterCategory = ref('')
const filterDifficulty = ref<number | null>(null)
const searchKeyword = ref('')

// 表单数据
const formData = ref<WordPairCreateParams>({
  civilian_word: '',
  undercover_word: '',
  category: '',
  difficulty: 3
})

// 批量添加
const batchText = ref('')
const batchCategory = ref('')
const batchDifficulty = ref(3)

const errorMsg = ref('')
const successMsg = ref('')

// 难度选项
const difficultyOptions = [
  { value: 1, label: '1 - 非常简单', color: 'bg-green-100 text-green-700' },
  { value: 2, label: '2 - 简单', color: 'bg-lime-100 text-lime-700' },
  { value: 3, label: '3 - 普通', color: 'bg-blue-100 text-blue-700' },
  { value: 4, label: '4 - 困难', color: 'bg-orange-100 text-orange-700' },
  { value: 5, label: '5 - 非常困难', color: 'bg-red-100 text-red-700' }
]

const getDifficultyClass = (difficulty: number) => {
  const option = difficultyOptions.find(o => o.value === difficulty)
  return option?.color || 'bg-slate-100 text-slate-700'
}

const getDifficultyLabel = (difficulty: number) => {
  return `难度 ${difficulty}`
}

// 管理员登录
const handleAdminLogin = async () => {
  loginError.value = ''
  try {
    const response = await adminLogin(adminPassword.value)
    if (response.data.success) {
      localStorage.setItem('adminToken', response.data.token)
      isAdminAuthenticated.value = true
      showLoginModal.value = false
      await fetchData()
    } else {
      loginError.value = response.data.message || '登录失败'
    }
  } catch (err: any) {
    loginError.value = err.response?.data?.detail || '登录失败'
  }
}

// 获取数据
const fetchData = async () => {
  loading.value = true
  try {
    const [pairsRes, statsRes, categoriesRes] = await Promise.all([
      getWordPairs({
        page: currentPage.value,
        page_size: pageSize.value,
        category: filterCategory.value || undefined,
        difficulty: filterDifficulty.value || undefined,
        search: searchKeyword.value || undefined
      }),
      getWordPairStats(),
      getWordCategories()
    ])

    wordPairs.value = pairsRes.data.word_pairs
    totalItems.value = pairsRes.data.total
    hasNext.value = pairsRes.data.has_next
    stats.value = statsRes.data
    categories.value = categoriesRes.data.categories
  } catch (err: any) {
    if (err.response?.status === 401) {
      isAdminAuthenticated.value = false
      showLoginModal.value = true
    }
  } finally {
    loading.value = false
  }
}

// 搜索防抖
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(searchKeyword, () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    currentPage.value = 1
    fetchData()
  }, 300)
})

watch([filterCategory, filterDifficulty], () => {
  currentPage.value = 1
  fetchData()
})

// 分页
const totalPages = computed(() => Math.ceil(totalItems.value / pageSize.value))

const goToPage = (page: number) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchData()
  }
}

// 模态框操作
const openCreateModal = () => {
  modalMode.value = 'create'
  editingWord.value = null
  formData.value = {
    civilian_word: '',
    undercover_word: '',
    category: categories.value[0] || '',
    difficulty: 3
  }
  errorMsg.value = ''
  successMsg.value = ''
  showModal.value = true
}

const openEditModal = (word: WordPair) => {
  modalMode.value = 'edit'
  editingWord.value = word
  formData.value = {
    civilian_word: word.civilian_word,
    undercover_word: word.undercover_word,
    category: word.category,
    difficulty: word.difficulty
  }
  errorMsg.value = ''
  successMsg.value = ''
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  editingWord.value = null
}

// 提交表单
const handleSubmit = async () => {
  errorMsg.value = ''
  successMsg.value = ''

  if (!formData.value.civilian_word.trim()) {
    errorMsg.value = '请输入平民词汇'
    return
  }
  if (!formData.value.undercover_word.trim()) {
    errorMsg.value = '请输入卧底词汇'
    return
  }
  if (!formData.value.category.trim()) {
    errorMsg.value = '请输入类别'
    return
  }

  try {
    if (modalMode.value === 'create') {
      await createWordPair(formData.value)
      successMsg.value = '词汇对创建成功'
    } else if (editingWord.value) {
      await updateWordPair(editingWord.value.id, formData.value)
      successMsg.value = '词汇对更新成功'
    }
    await fetchData()
    setTimeout(() => {
      closeModal()
    }, 1000)
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || '操作失败'
  }
}

// 删除
const handleDelete = async (word: WordPair) => {
  if (!confirm(`确定要删除词汇对「${word.civilian_word} / ${word.undercover_word}」吗？`)) return

  try {
    await deleteWordPair(word.id)
    await fetchData()
  } catch (err: any) {
    alert(err.response?.data?.detail || '删除失败')
  }
}

// 批量添加
const openBatchModal = () => {
  batchText.value = ''
  batchCategory.value = categories.value[0] || '其他'
  batchDifficulty.value = 3
  showBatchModal.value = true
}

const handleBatchSubmit = async () => {
  errorMsg.value = ''
  successMsg.value = ''

  const lines = batchText.value.split('\n').filter(line => line.trim())
  if (lines.length === 0) {
    errorMsg.value = '请输入词汇对'
    return
  }

  const wordPairsToCreate: WordPairCreateParams[] = []
  const errors: string[] = []

  for (const line of lines) {
    // 支持多种分隔符: / | , 空格
    const parts = line.split(/[\/\|,\s]+/).filter(p => p.trim())
    if (parts.length >= 2) {
      wordPairsToCreate.push({
        civilian_word: parts[0].trim(),
        undercover_word: parts[1].trim(),
        category: batchCategory.value,
        difficulty: batchDifficulty.value
      })
    } else {
      errors.push(`格式错误: ${line}`)
    }
  }

  if (wordPairsToCreate.length === 0) {
    errorMsg.value = '没有有效的词汇对。格式: 平民词/卧底词'
    return
  }

  try {
    const result = await batchCreateWordPairs(wordPairsToCreate)
    successMsg.value = result.data.message
    if (errors.length > 0) {
      successMsg.value += `\n格式错误: ${errors.length} 行`
    }
    await fetchData()
    setTimeout(() => {
      showBatchModal.value = false
    }, 2000)
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || '批量添加失败'
  }
}

const goBack = () => {
  router.push('/lobby')
}

onMounted(async () => {
  // 检查是否已有管理员 token
  const token = localStorage.getItem('adminToken')
  if (token) {
    isAdminAuthenticated.value = true
    await fetchData()
  } else {
    showLoginModal.value = true
  }
})
</script>

<template>
  <div class="min-h-screen bg-bg-main overflow-x-hidden">
    <!-- 管理员登录模态框 -->
    <div v-if="showLoginModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-2xl p-8 w-full max-w-md shadow-xl">
        <h3 class="text-xl font-bold text-text-main mb-6">管理员验证</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">管理员密码</label>
            <input
              v-model="adminPassword"
              type="password"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="请输入管理员密码"
              @keyup.enter="handleAdminLogin"
            />
          </div>
          <p v-if="loginError" class="text-red-500 text-sm">{{ loginError }}</p>
          <div class="flex gap-3">
            <button
              @click="goBack"
              class="flex-1 px-4 py-3 border border-border-light rounded-xl font-medium hover:bg-slate-50"
            >
              返回
            </button>
            <button
              @click="handleAdminLogin"
              class="flex-1 px-4 py-3 bg-primary text-white rounded-xl font-medium hover:bg-primary-hover"
            >
              登录
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 顶部导航 -->
    <header class="flex items-center justify-between border-b border-border-light px-10 py-4 sticky top-0 bg-white/90 backdrop-blur-md z-40">
      <div class="flex items-center gap-2 text-primary">
        <span class="material-symbols-outlined text-3xl font-bold">dictionary</span>
        <h2 class="text-text-main text-xl font-extrabold tracking-tight">词汇管理</h2>
      </div>
      <div class="flex items-center gap-4">
        <button
          @click="openBatchModal"
          class="flex items-center gap-2 px-5 py-2 bg-green-500 text-white rounded-xl text-sm font-bold hover:bg-green-600 transition-all"
        >
          <span class="material-symbols-outlined text-lg">playlist_add</span> 批量添加
        </button>
        <button
          @click="openCreateModal"
          class="flex items-center gap-2 px-5 py-2 bg-primary text-white rounded-xl text-sm font-bold hover:bg-primary-hover transition-all"
        >
          <span class="material-symbols-outlined text-lg">add</span> 新建词汇
        </button>
        <button
          @click="goBack"
          class="flex items-center gap-2 px-5 py-2 bg-white border border-border-light rounded-xl text-sm font-bold hover:bg-slate-50 transition-all"
        >
          <span class="material-symbols-outlined text-lg">arrow_back</span> 返回大厅
        </button>
      </div>
    </header>

    <main class="max-w-[1400px] mx-auto w-full px-6 py-8">
      <!-- 统计卡片 -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-8" v-if="stats">
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">词汇总数</p>
            <span class="material-symbols-outlined text-primary">library_books</span>
          </div>
          <p class="text-3xl font-bold">{{ stats.total_pairs }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">类别数量</p>
            <span class="material-symbols-outlined text-green-500">category</span>
          </div>
          <p class="text-3xl font-bold">{{ stats.categories.length }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">简单词汇</p>
            <span class="material-symbols-outlined text-lime-500">sentiment_satisfied</span>
          </div>
          <p class="text-3xl font-bold">{{ (stats.difficulty_distribution[1] || 0) + (stats.difficulty_distribution[2] || 0) }}</p>
        </div>
        <div class="bg-white p-6 rounded-xl border border-border-light">
          <div class="flex justify-between mb-2">
            <p class="text-sm font-semibold text-text-muted">困难词汇</p>
            <span class="material-symbols-outlined text-red-500">psychology</span>
          </div>
          <p class="text-3xl font-bold">{{ (stats.difficulty_distribution[4] || 0) + (stats.difficulty_distribution[5] || 0) }}</p>
        </div>
      </div>

      <!-- 筛选和搜索 -->
      <div class="bg-white p-4 rounded-xl border border-border-light mb-6 flex flex-wrap gap-4 items-center">
        <div class="flex-1 min-w-[200px]">
          <input
            v-model="searchKeyword"
            type="text"
            class="w-full px-4 py-2 border border-border-light rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary"
            placeholder="搜索词汇..."
          />
        </div>
        <div class="flex gap-3">
          <select
            v-model="filterCategory"
            class="px-4 py-2 border border-border-light rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary"
          >
            <option value="">所有类别</option>
            <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
          </select>
          <select
            v-model="filterDifficulty"
            class="px-4 py-2 border border-border-light rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary"
          >
            <option :value="null">所有难度</option>
            <option v-for="d in difficultyOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
          </select>
        </div>
      </div>

      <!-- 词汇列表 -->
      <div class="bg-white rounded-xl border border-border-light overflow-hidden">
        <table class="w-full">
          <thead class="bg-slate-50 border-b border-border-light">
            <tr>
              <th class="px-6 py-4 text-left text-sm font-semibold text-text-muted">平民词汇</th>
              <th class="px-6 py-4 text-left text-sm font-semibold text-text-muted">卧底词汇</th>
              <th class="px-6 py-4 text-left text-sm font-semibold text-text-muted">类别</th>
              <th class="px-6 py-4 text-left text-sm font-semibold text-text-muted">难度</th>
              <th class="px-6 py-4 text-right text-sm font-semibold text-text-muted">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border-light">
            <tr v-if="loading" class="text-center">
              <td colspan="5" class="px-6 py-12 text-text-muted">加载中...</td>
            </tr>
            <tr v-else-if="wordPairs.length === 0" class="text-center">
              <td colspan="5" class="px-6 py-12 text-text-muted">暂无词汇</td>
            </tr>
            <tr v-for="word in wordPairs" :key="word.id" class="hover:bg-slate-50">
              <td class="px-6 py-4 font-medium text-text-main">{{ word.civilian_word }}</td>
              <td class="px-6 py-4 text-text-main">{{ word.undercover_word }}</td>
              <td class="px-6 py-4">
                <span class="px-3 py-1 bg-slate-100 text-slate-700 rounded-full text-sm">{{ word.category }}</span>
              </td>
              <td class="px-6 py-4">
                <span :class="[getDifficultyClass(word.difficulty), 'px-3 py-1 rounded-full text-sm']">
                  {{ getDifficultyLabel(word.difficulty) }}
                </span>
              </td>
              <td class="px-6 py-4 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    @click="openEditModal(word)"
                    class="p-2 text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                    title="编辑"
                  >
                    <span class="material-symbols-outlined text-xl">edit</span>
                  </button>
                  <button
                    @click="handleDelete(word)"
                    class="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    title="删除"
                  >
                    <span class="material-symbols-outlined text-xl">delete</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="flex items-center justify-between px-6 py-4 border-t border-border-light bg-slate-50">
          <p class="text-sm text-text-muted">
            共 {{ totalItems }} 条，第 {{ currentPage }} / {{ totalPages }} 页
          </p>
          <div class="flex gap-2">
            <button
              @click="goToPage(currentPage - 1)"
              :disabled="currentPage === 1"
              class="px-4 py-2 border border-border-light rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              上一页
            </button>
            <button
              @click="goToPage(currentPage + 1)"
              :disabled="!hasNext"
              class="px-4 py-2 border border-border-light rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 创建/编辑模态框 -->
    <div v-if="showModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="closeModal">
      <div class="bg-white rounded-2xl p-8 w-full max-w-lg shadow-xl">
        <h3 class="text-xl font-bold text-text-main mb-6">
          {{ modalMode === 'create' ? '新建词汇对' : '编辑词汇对' }}
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">平民词汇</label>
            <input
              v-model="formData.civilian_word"
              type="text"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="例如: 电脑"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">卧底词汇</label>
            <input
              v-model="formData.undercover_word"
              type="text"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="例如: 笔记本"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">类别</label>
            <input
              v-model="formData.category"
              type="text"
              list="category-list"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
              placeholder="例如: 电子产品"
            />
            <datalist id="category-list">
              <option v-for="cat in categories" :key="cat" :value="cat" />
            </datalist>
          </div>

          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">难度</label>
            <select
              v-model="formData.difficulty"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
            >
              <option v-for="d in difficultyOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
            </select>
          </div>

          <p v-if="errorMsg" class="text-red-500 text-sm">{{ errorMsg }}</p>
          <p v-if="successMsg" class="text-green-500 text-sm">{{ successMsg }}</p>

          <div class="flex gap-3 pt-4">
            <button
              @click="closeModal"
              class="flex-1 px-4 py-3 border border-border-light rounded-xl font-medium hover:bg-slate-50"
            >
              取消
            </button>
            <button
              @click="handleSubmit"
              class="flex-1 px-4 py-3 bg-primary text-white rounded-xl font-medium hover:bg-primary-hover"
            >
              {{ modalMode === 'create' ? '创建' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量添加模态框 -->
    <div v-if="showBatchModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="showBatchModal = false">
      <div class="bg-white rounded-2xl p-8 w-full max-w-2xl shadow-xl">
        <h3 class="text-xl font-bold text-text-main mb-6">批量添加词汇</h3>

        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-text-muted mb-2">类别</label>
              <input
                v-model="batchCategory"
                type="text"
                list="batch-category-list"
                class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
                placeholder="例如: 电子产品"
              />
              <datalist id="batch-category-list">
                <option v-for="cat in categories" :key="cat" :value="cat" />
              </datalist>
            </div>
            <div>
              <label class="block text-sm font-medium text-text-muted mb-2">难度</label>
              <select
                v-model="batchDifficulty"
                class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary"
              >
                <option v-for="d in difficultyOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-text-muted mb-2">
              词汇对列表 (每行一对，格式: 平民词/卧底词)
            </label>
            <textarea
              v-model="batchText"
              rows="10"
              class="w-full px-4 py-3 border border-border-light rounded-xl focus:ring-2 focus:ring-primary/20 focus:border-primary font-mono text-sm"
              placeholder="电脑/笔记本
苹果/梨子
手机/平板
..."
            ></textarea>
            <p class="text-xs text-text-muted mt-1">支持分隔符: / | , 或空格</p>
          </div>

          <p v-if="errorMsg" class="text-red-500 text-sm">{{ errorMsg }}</p>
          <p v-if="successMsg" class="text-green-500 text-sm whitespace-pre-line">{{ successMsg }}</p>

          <div class="flex gap-3 pt-4">
            <button
              @click="showBatchModal = false"
              class="flex-1 px-4 py-3 border border-border-light rounded-xl font-medium hover:bg-slate-50"
            >
              取消
            </button>
            <button
              @click="handleBatchSubmit"
              class="flex-1 px-4 py-3 bg-green-500 text-white rounded-xl font-medium hover:bg-green-600"
            >
              批量添加
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
