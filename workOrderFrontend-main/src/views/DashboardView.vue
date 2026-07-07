<template>
  <section class="dashboard-page" v-loading="loading">
    <header class="dashboard-hero">
      <div class="dashboard-hero__copy">
        <p class="dashboard-eyebrow">{{ roleLabel }}工作台</p>
        <h2>智能客服系统</h2>
        <p class="dashboard-hero__lead">{{ heroLead }}</p>
      </div>

      <div class="dashboard-hero__rail">
        <div class="dashboard-flow">
          <span>AI 分流</span>
          <span>资料核实</span>
          <span>人工跟进</span>
        </div>
        <el-button class="dashboard-hero__button" type="primary" @click="go(primaryAction.path)">
          <el-icon><component :is="primaryAction.icon" /></el-icon>
          {{ primaryAction.label }}
        </el-button>
      </div>
    </header>

    <section class="dashboard-stats" :aria-label="`${roleLabel}摘要`">
      <article v-for="item in statCards" :key="item.key" class="dashboard-stat" :class="item.className">
        <div class="dashboard-stat__label">{{ item.label }}</div>
        <div class="dashboard-stat__value">{{ item.value }}</div>
        <div class="dashboard-stat__hint">{{ item.hint }}</div>
      </article>
    </section>

    <section class="dashboard-layout">
      <div class="dashboard-panel dashboard-panel--actions">
        <div class="dashboard-panel__header">
          <div>
            <p class="dashboard-eyebrow">快捷入口</p>
            <h3>{{ actionTitle }}</h3>
          </div>
          <span v-if="dataError" class="dashboard-status">数据暂不可用</span>
        </div>

        <div class="dashboard-actions">
          <button
            v-for="item in actionCards"
            :key="item.path + item.title"
            type="button"
            class="dashboard-action"
            :class="{ 'is-primary': item.primary }"
            @click="go(item.path)"
          >
            <span class="dashboard-action__icon">
              <el-icon><component :is="item.icon" /></el-icon>
            </span>
            <span class="dashboard-action__body">
              <span class="dashboard-action__title">{{ item.title }}</span>
              <span class="dashboard-action__desc">{{ item.desc }}</span>
            </span>
          </button>
        </div>
      </div>

      <div class="dashboard-panel">
        <div class="dashboard-panel__header">
          <div>
            <p class="dashboard-eyebrow">最近事项</p>
            <h3>{{ recentTitle }}</h3>
          </div>
          <el-button link type="primary" @click="go(recentMorePath)">查看全部</el-button>
        </div>

        <div v-if="dataError" class="dashboard-empty">数据暂不可用，快捷入口仍可使用。</div>
        <div v-else-if="!recentItems.length" class="dashboard-empty">{{ emptyText }}</div>
        <div v-else class="dashboard-list">
          <button
            v-for="item in recentItems"
            :key="item.id"
            type="button"
            class="dashboard-list__item"
            @click="go(item.path)"
          >
            <span class="dashboard-list__main">
              <span class="dashboard-list__title">{{ item.title }}</span>
              <span class="dashboard-list__meta">{{ item.meta }}</span>
            </span>
            <span class="dashboard-list__status" :class="item.statusClass">{{ item.statusLabel }}</span>
          </button>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound,
  CircleCheckFilled,
  Document,
  DocumentChecked,
  Promotion,
  Search
} from '@element-plus/icons-vue'
import { pageFeedback } from '../api/feedback'
import { getMyOrders } from '../api/order'
import { getWorkOrderSummary, pageWorkOrders } from '../api/workOrder'
import { sessionState } from '../store/session'
import { normalizeRole } from '../utils/auth'
import { mapTicketStatus, toStatusMeta } from '../utils/ticket'

const router = useRouter()
const loading = ref(false)
const dataError = ref(false)
const orders = ref([])
const feedbacks = ref([])
const workOrders = ref([])
const workOrderSummary = reactive({
  total: 0,
  pending: 0,
  processing: 0,
  solved: 0,
  closed: 0
})

const role = computed(() => normalizeRole(sessionState.user?.role))
const isAdmin = computed(() => role.value === 'admin')
const roleLabel = computed(() => (isAdmin.value ? '管理端' : '用户端'))

const heroLead = computed(() => isAdmin.value
  ? '集中处理用户反馈、AI 建议和退款售后，让每个工单都有明确下一步。'
  : '先和 AI 客服描述问题，系统会查询知识库、订单和使用记录，必要时再转人工。')

const primaryAction = computed(() => isAdmin.value
  ? { label: '进入工单管理', path: '/work-order', icon: DocumentChecked }
  : { label: '开始 AI 客服对话', path: '/assistant', icon: ChatDotRound })

const actionTitle = computed(() => isAdmin.value ? '处理队列' : '我要办理')
const recentTitle = computed(() => isAdmin.value ? '最近工单' : '最近反馈')
const recentMorePath = computed(() => isAdmin.value ? '/work-order' : '/feedback')
const emptyText = computed(() => isAdmin.value ? '暂无工单记录。' : '暂无反馈记录，可以先从 AI 客服开始描述问题。')

const actionCards = computed(() => isAdmin.value
  ? [
      {
        title: '进入工单管理',
        desc: '查看待处理、处理中和已解决工单。',
        path: '/work-order',
        icon: DocumentChecked,
        primary: true
      },
      {
        title: '知识库维护',
        desc: '管理客服回答可引用的知识资料。',
        path: '/knowledge',
        icon: Search
      },
      {
        title: 'AI 回复建议',
        desc: '在工单详情内生成可审核的回复草稿。',
        path: '/work-order',
        icon: Promotion
      },
      {
        title: '退款审核',
        desc: '退款售后工单由后台规则核验后处理。',
        path: '/refund-review',
        icon: CircleCheckFilled
      }
    ]
  : [
      {
        title: '开始 AI 客服对话',
        desc: '先说明问题，AI 会分流到知识、订单或售后。',
        path: '/assistant',
        icon: ChatDotRound,
        primary: true
      },
      {
        title: '我的订单',
        desc: '查看订单状态、物流和可售后线索。',
        path: '/orders',
        icon: Document
      },
      {
        title: '我的反馈',
        desc: '查看已提交问题和人工客服回复。',
        path: '/feedback',
        icon: DocumentChecked
      },
      {
        title: '知识问答',
        desc: '查询产品使用、保养和常见问题。',
        path: '/knowledge',
        icon: Search
      }
    ])

const statCards = computed(() => {
  if (isAdmin.value) {
    return [
      { key: 'pending', label: '待处理', value: workOrderSummary.pending, hint: '需要优先分派', className: 'is-warn' },
      { key: 'processing', label: '处理中', value: workOrderSummary.processing, hint: '正在跟进', className: 'is-info' },
      { key: 'solved', label: '已解决', value: workOrderSummary.solved, hint: '本系统累计', className: 'is-ok' },
      { key: 'total', label: '工单总数', value: workOrderSummary.total, hint: '全部记录', className: 'is-neutral' }
    ]
  }

  const activeFeedbackCount = feedbacks.value.filter(item => ['PENDING', 'PROCESSING'].includes(mapTicketStatus(item.status))).length
  const solvedFeedbackCount = feedbacks.value.filter(item => mapTicketStatus(item.status) === 'SOLVED').length
  return [
    { key: 'orders', label: '我的订单', value: orders.value.length, hint: '当前账号', className: 'is-info' },
    { key: 'active', label: '跟进中反馈', value: activeFeedbackCount, hint: '待处理/处理中', className: 'is-warn' },
    { key: 'solved', label: '已解决反馈', value: solvedFeedbackCount, hint: '最近记录', className: 'is-ok' },
    { key: 'assistant', label: 'AI 客服', value: '在线', hint: '先对话再转人工', className: 'is-neutral' }
  ]
})

const recentItems = computed(() => {
  const source = isAdmin.value ? workOrders.value : feedbacks.value
  return source.slice(0, 5).map(item => {
    const status = mapTicketStatus(item.status)
    const meta = [item.code, formatTime(item.updatedAt || item.createdAt)].filter(Boolean).join(' · ')
    return {
      id: item.id,
      title: item.title || '未命名事项',
      meta: meta || '--',
      path: isAdmin.value ? '/work-order' : '/feedback',
      statusLabel: toStatusMeta(status).label,
      statusClass: toStatusMeta(status).className
    }
  })
})

async function loadDashboardData() {
  loading.value = true
  dataError.value = false
  try {
    if (isAdmin.value) {
      const [summaryRes, listRes] = await Promise.all([
        getWorkOrderSummary(),
        pageWorkOrders({ pageNum: 1, pageSize: 5 })
      ])
      const summary = summaryRes?.data || {}
      workOrderSummary.total = Number(summary.total || 0) || 0
      workOrderSummary.pending = Number(summary.pending || 0) || 0
      workOrderSummary.processing = Number(summary.processing || 0) || 0
      workOrderSummary.solved = Number(summary.solved || 0) || 0
      workOrderSummary.closed = Number(summary.closed || 0) || 0
      workOrders.value = Array.isArray(listRes?.data?.records) ? listRes.data.records : []
    } else {
      const [orderRes, feedbackRes] = await Promise.all([
        getMyOrders(),
        pageFeedback({ pageNum: 1, pageSize: 5 })
      ])
      orders.value = Array.isArray(orderRes?.data) ? orderRes.data : []
      feedbacks.value = Array.isArray(feedbackRes?.data?.records) ? feedbackRes.data.records : []
    }
  } catch (error) {
    dataError.value = true
    orders.value = []
    feedbacks.value = []
    workOrders.value = []
    workOrderSummary.total = 0
    workOrderSummary.pending = 0
    workOrderSummary.processing = 0
    workOrderSummary.solved = 0
    workOrderSummary.closed = 0
  } finally {
    loading.value = false
  }
}

function formatTime(value) {
  if (!value) {
    return ''
  }
  return String(value).slice(5, 16)
}

function go(path) {
  router.push(path)
}

onMounted(loadDashboardData)
</script>

<style scoped>
.dashboard-page {
  display: grid;
  gap: 16px;
  color: #16233f;
}

.dashboard-hero,
.dashboard-panel,
.dashboard-stat {
  border: 1px solid #dde7f4;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 14px 34px rgba(21, 46, 80, 0.07);
}

.dashboard-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: center;
  padding: 24px;
}

.dashboard-eyebrow {
  margin: 0 0 6px;
  color: #617895;
  font-size: 12px;
  font-weight: 650;
}

.dashboard-hero h2,
.dashboard-panel h3 {
  margin: 0;
  color: #17294f;
}

.dashboard-hero h2 {
  font-size: 30px;
  font-weight: 750;
}

.dashboard-hero__lead {
  max-width: 680px;
  margin: 10px 0 0;
  color: #536780;
  line-height: 1.7;
}

.dashboard-hero__rail {
  display: grid;
  gap: 14px;
  justify-items: end;
}

.dashboard-flow {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #5c6f88;
  font-size: 12px;
}

.dashboard-flow span {
  min-height: 26px;
  padding: 5px 9px;
  border: 1px solid #dbe5f2;
  border-radius: 6px;
  background: #f7faff;
}

.dashboard-hero__button {
  min-height: 40px;
  border-radius: 8px;
}

.dashboard-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.dashboard-stat {
  padding: 16px;
  border-left-width: 4px;
}

.dashboard-stat.is-warn {
  border-left-color: #f3b123;
}

.dashboard-stat.is-info {
  border-left-color: #3a86ff;
}

.dashboard-stat.is-ok {
  border-left-color: #1cc965;
}

.dashboard-stat.is-neutral {
  border-left-color: #8b9bb2;
}

.dashboard-stat__label {
  color: #65758c;
  font-size: 12px;
}

.dashboard-stat__value {
  margin-top: 6px;
  color: #17294f;
  font-size: 28px;
  font-weight: 750;
  line-height: 1;
}

.dashboard-stat__hint {
  margin-top: 8px;
  color: #7f8ca2;
  font-size: 12px;
}

.dashboard-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.92fr);
  gap: 16px;
  align-items: start;
}

.dashboard-panel {
  padding: 18px;
}

.dashboard-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.dashboard-status {
  padding: 4px 8px;
  border-radius: 6px;
  background: #fff7df;
  color: #996c00;
  font-size: 12px;
}

.dashboard-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.dashboard-action,
.dashboard-list__item {
  width: 100%;
  border: 1px solid #e2eaf5;
  border-radius: 8px;
  background: #fff;
  color: inherit;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.dashboard-action {
  display: flex;
  gap: 12px;
  min-height: 104px;
  padding: 14px;
}

.dashboard-action:hover,
.dashboard-list__item:hover {
  border-color: #b7c9e4;
  box-shadow: 0 10px 24px rgba(21, 46, 80, 0.08);
  transform: translateY(-1px);
}

.dashboard-action.is-primary {
  border-color: #17325f;
  background: #f4f8ff;
}

.dashboard-action__icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  place-items: center;
  border-radius: 8px;
  background: #17325f;
  color: #fff;
  font-size: 18px;
}

.dashboard-action:not(.is-primary) .dashboard-action__icon {
  background: #eef4ff;
  color: #285ca8;
}

.dashboard-action__body {
  display: grid;
  gap: 6px;
}

.dashboard-action__title {
  color: #233654;
  font-size: 15px;
  font-weight: 700;
}

.dashboard-action__desc {
  color: #66758b;
  font-size: 13px;
  line-height: 1.55;
}

.dashboard-list {
  display: grid;
  gap: 10px;
}

.dashboard-list__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 68px;
  padding: 12px;
}

.dashboard-list__main {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.dashboard-list__title,
.dashboard-list__meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-list__title {
  color: #233654;
  font-weight: 650;
}

.dashboard-list__meta {
  color: #7a879d;
  font-size: 12px;
}

.dashboard-list__status {
  min-width: 66px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  text-align: center;
}

.dashboard-list__status.is-pending {
  background: #fff7df;
  color: #996c00;
}

.dashboard-list__status.is-processing {
  background: #eaf2ff;
  color: #2d66ea;
}

.dashboard-list__status.is-solved {
  background: #e8faef;
  color: #17995c;
}

.dashboard-list__status.is-closed {
  background: #f1f3f7;
  color: #7f8898;
}

.dashboard-empty {
  min-height: 160px;
  display: grid;
  place-items: center;
  padding: 20px;
  border: 1px dashed #d8e2f0;
  border-radius: 8px;
  background: #fbfdff;
  color: #7a879d;
  text-align: center;
}

@media (max-width: 1180px) {
  .dashboard-layout,
  .dashboard-hero {
    grid-template-columns: 1fr;
  }

  .dashboard-hero__rail {
    justify-items: start;
  }
}

@media (max-width: 760px) {
  .dashboard-stats,
  .dashboard-actions {
    grid-template-columns: 1fr;
  }

  .dashboard-flow {
    flex-wrap: wrap;
  }

  .dashboard-list__item {
    grid-template-columns: 1fr;
  }
}
</style>
