<script setup lang="ts">
import { ref, watch, computed } from 'vue'

export interface GameNotificationData {
  type: 'phase_change' | 'player_eliminated' | 'game_end' | 'round_start' | 'your_turn' | 'ai_speaking'
  title: string
  message: string
  icon?: string
  color?: 'primary' | 'success' | 'warning' | 'danger'
  duration?: number
  playerName?: string
  winnerRole?: string
}

const props = defineProps<{
  notification: GameNotificationData | null
}>()

const emit = defineEmits<{
  close: []
}>()

const visible = ref(false)
const currentNotification = ref<GameNotificationData | null>(null)

watch(() => props.notification, (newVal) => {
  if (newVal) {
    currentNotification.value = newVal
    visible.value = true

    // 自动关闭
    const duration = newVal.duration ?? 3000
    if (duration > 0) {
      setTimeout(() => {
        visible.value = false
        emit('close')
      }, duration)
    }
  }
}, { immediate: true })

const iconName = computed(() => {
  if (currentNotification.value?.icon) return currentNotification.value.icon

  switch (currentNotification.value?.type) {
    case 'phase_change': return 'swap_horiz'
    case 'player_eliminated': return 'person_remove'
    case 'game_end': return 'emoji_events'
    case 'round_start': return 'restart_alt'
    case 'your_turn': return 'mic'
    case 'ai_speaking': return 'smart_toy'
    default: return 'info'
  }
})

const colorClass = computed(() => {
  const color = currentNotification.value?.color || 'primary'
  switch (color) {
    case 'success': return 'bg-green-500'
    case 'warning': return 'bg-amber-500'
    case 'danger': return 'bg-red-500'
    default: return 'bg-primary'
  }
})

const bgClass = computed(() => {
  const color = currentNotification.value?.color || 'primary'
  switch (color) {
    case 'success': return 'bg-green-50 border-green-200'
    case 'warning': return 'bg-amber-50 border-amber-200'
    case 'danger': return 'bg-red-50 border-red-200'
    default: return 'bg-blue-50 border-blue-200'
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 scale-95 translate-y-4"
      enter-to-class="opacity-100 scale-100 translate-y-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="visible && currentNotification"
        class="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
      >
        <!-- 背景遮罩（仅在重要通知时显示） -->
        <div
          v-if="currentNotification.type === 'game_end' || currentNotification.type === 'player_eliminated'"
          class="absolute inset-0 bg-black/20 pointer-events-auto"
          @click="visible = false; emit('close')"
        />

        <!-- 通知卡片 -->
        <div
          :class="[
            'relative pointer-events-auto',
            'p-8 rounded-3xl border-2 shadow-2xl',
            'min-w-[320px] max-w-[480px]',
            'text-center',
            bgClass
          ]"
        >
          <!-- 图标 -->
          <div
            :class="[
              'w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4',
              colorClass
            ]"
          >
            <span class="material-symbols-outlined text-4xl text-white">
              {{ iconName }}
            </span>
          </div>

          <!-- 标题 -->
          <h3 class="text-2xl font-bold mb-2 text-slate-800">
            {{ currentNotification.title }}
          </h3>

          <!-- 消息 -->
          <p class="text-slate-600 text-lg">
            {{ currentNotification.message }}
          </p>

          <!-- 玩家名称（如果有） -->
          <div
            v-if="currentNotification.playerName"
            class="mt-4 py-2 px-4 bg-white/50 rounded-xl inline-block"
          >
            <span class="font-bold text-xl">{{ currentNotification.playerName }}</span>
          </div>

          <!-- 胜利方（游戏结束时） -->
          <div
            v-if="currentNotification.type === 'game_end' && currentNotification.winnerRole"
            class="mt-6"
          >
            <span
              :class="[
                'px-6 py-3 rounded-full text-lg font-bold',
                currentNotification.winnerRole === 'undercover'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-green-100 text-green-700'
              ]"
            >
              {{ currentNotification.winnerRole === 'undercover' ? '卧底获胜' : '平民获胜' }}
            </span>
          </div>

          <!-- 关闭按钮 -->
          <button
            @click="visible = false; emit('close')"
            class="absolute top-4 right-4 p-2 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
