<script setup lang="ts">
import { computed } from 'vue'

export interface VoteResult {
  targetId: string
  targetName: string
  voteCount: number
  isEliminated: boolean
  voters: Array<{ id: string; name: string; isAI: boolean }>
}

const props = defineProps<{
  results: VoteResult[]
  totalVoters: number
}>()

const sortedResults = computed(() => {
  return [...props.results].sort((a, b) => b.voteCount - a.voteCount)
})

const eliminatedPlayer = computed(() => {
  return props.results.find(r => r.isEliminated)
})
</script>

<template>
  <div class="bg-white rounded-2xl border border-border-light overflow-hidden">
    <!-- 标题 -->
    <div class="p-4 border-b border-border-light bg-slate-50">
      <h4 class="font-bold flex items-center gap-2">
        <span class="material-symbols-outlined text-amber-500">how_to_vote</span>
        投票结果
      </h4>
    </div>

    <!-- 结果列表 -->
    <div class="p-4 space-y-3">
      <div
        v-for="result in sortedResults"
        :key="result.targetId"
        :class="[
          'p-3 rounded-xl border-2 transition-all',
          result.isEliminated
            ? 'bg-red-50 border-red-300'
            : 'bg-slate-50 border-transparent'
        ]"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span class="font-bold">{{ result.targetName }}</span>
            <span
              v-if="result.isEliminated"
              class="px-2 py-0.5 bg-red-500 text-white text-[10px] rounded-full font-bold"
            >
              淘汰
            </span>
          </div>
          <span class="font-bold text-lg">{{ result.voteCount }} 票</span>
        </div>

        <!-- 投票者 -->
        <div v-if="result.voters.length > 0" class="flex flex-wrap gap-1">
          <span
            v-for="voter in result.voters"
            :key="voter.id"
            :class="[
              'px-2 py-0.5 rounded-full text-[10px] font-medium',
              voter.isAI
                ? 'bg-purple-100 text-purple-700'
                : 'bg-blue-100 text-blue-700'
            ]"
          >
            {{ voter.name }}
          </span>
        </div>

        <!-- 票数进度条 -->
        <div class="mt-2 h-1.5 bg-slate-200 rounded-full overflow-hidden">
          <div
            :class="[
              'h-full transition-all duration-500 rounded-full',
              result.isEliminated ? 'bg-red-500' : 'bg-slate-400'
            ]"
            :style="{ width: `${(result.voteCount / totalVoters) * 100}%` }"
          />
        </div>
      </div>
    </div>

    <!-- 淘汰提示 -->
    <div
      v-if="eliminatedPlayer"
      class="p-4 bg-red-50 border-t border-red-200 text-center"
    >
      <p class="text-red-700">
        <span class="font-bold">{{ eliminatedPlayer.targetName }}</span> 被淘汰出局
      </p>
    </div>
  </div>
</template>
