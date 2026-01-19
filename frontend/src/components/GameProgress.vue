<script setup lang="ts">
defineProps<{
  phase: 'SPEAKING' | 'VOTING' | 'WAITING' | 'FINISHED' | string
  currentPlayerName?: string
  currentPlayerIndex?: number
  totalPlayers?: number
  isAI?: boolean
}>()

const phaseConfig = {
  WAITING: { label: '等待开始', icon: 'hourglass_empty', color: 'bg-slate-500' },
  SPEAKING: { label: '发言阶段', icon: 'mic', color: 'bg-blue-500' },
  VOTING: { label: '投票阶段', icon: 'how_to_vote', color: 'bg-amber-500' },
  FINISHED: { label: '游戏结束', icon: 'emoji_events', color: 'bg-green-500' }
}
</script>

<template>
  <div class="bg-white rounded-2xl border border-border-light p-4 shadow-sm">
    <!-- 阶段标题 -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <div
          :class="[
            'w-8 h-8 rounded-lg flex items-center justify-center text-white',
            phaseConfig[phase as keyof typeof phaseConfig]?.color || 'bg-slate-500'
          ]"
        >
          <span class="material-symbols-outlined text-lg">
            {{ phaseConfig[phase as keyof typeof phaseConfig]?.icon || 'info' }}
          </span>
        </div>
        <span class="font-bold text-sm">
          {{ phaseConfig[phase as keyof typeof phaseConfig]?.label || phase }}
        </span>
      </div>

      <!-- 进度 -->
      <span v-if="currentPlayerIndex !== undefined && totalPlayers" class="text-xs text-slate-500">
        {{ currentPlayerIndex + 1 }} / {{ totalPlayers }}
      </span>
    </div>

    <!-- 当前玩家 -->
    <div v-if="currentPlayerName && (phase === 'SPEAKING' || phase === 'VOTING')" class="flex items-center gap-3 p-3 bg-slate-50 rounded-xl">
      <div
        :class="[
          'w-10 h-10 rounded-full flex items-center justify-center',
          isAI ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600'
        ]"
      >
        <span class="material-symbols-outlined">
          {{ isAI ? 'smart_toy' : 'person' }}
        </span>
      </div>
      <div class="flex-1">
        <p class="text-xs text-slate-500">
          {{ phase === 'SPEAKING' ? '正在发言' : '正在投票' }}
        </p>
        <p class="font-bold">{{ currentPlayerName }}</p>
      </div>
      <!-- 加载动画 -->
      <div v-if="isAI" class="flex gap-1">
        <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
        <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
        <span class="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
      </div>
    </div>

    <!-- 进度条 -->
    <div v-if="currentPlayerIndex !== undefined && totalPlayers" class="mt-3">
      <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          class="h-full bg-primary transition-all duration-500 ease-out rounded-full"
          :style="{ width: `${((currentPlayerIndex + 1) / totalPlayers) * 100}%` }"
        />
      </div>
    </div>
  </div>
</template>
