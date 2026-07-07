<template>
  <section class="refund-review-page" v-loading="loading">
    <header class="refund-review-header">
      <div class="refund-review-header__copy">
        <p class="refund-review-page__eyebrow">退款审核</p>
        <h2>处理退款售后工单</h2>
        <p>集中查看退款售后队列，在详情中复用后端规则生成的退款方案并完成审核。</p>
      </div>
      <el-button :icon="Refresh" @click="loadRefundTickets">刷新</el-button>
    </header>

    <div class="refund-review-toolbar">
      <el-input
        v-model.trim="queryForm.keyword"
        clearable
        placeholder="搜索工单标题、描述、编号或账号名称"
        class="refund-review-toolbar__search"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="queryForm.status"
        clearable
        placeholder="全部工单状态"
        class="refund-review-toolbar__status"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-button type="primary" class="refund-review-toolbar__button" @click="handleSearch">查询</el-button>
    </div>

    <div class="refund-review-table">
      <el-table :data="tickets" row-key="id" stripe empty-text="暂无退款售后工单">
        <el-table-column label="序号" width="72">
          <template #default="{ $index }">
            {{ (page.pageNum - 1) * page.pageSize + $index + 1 }}
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编号" width="120" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="accountName" label="账号" width="150" show-overflow-tooltip />
        <el-table-column label="优先级" width="100">
          <template #default="{ row }">
            <span class="refund-review-priority" :class="toPriorityMeta(row.priority).className">
              {{ toPriorityMeta(row.priority).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <span class="refund-review-status" :class="toStatusMeta(row.status).className">
              {{ toStatusMeta(row.status).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openReviewDialog(row)">审核</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="refund-review-pagination">
        <el-pagination
          v-model:current-page="page.pageNum"
          v-model:page-size="page.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="page.total"
          background
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handleCurrentChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-dialog
      v-model="detailDialogVisible"
      title="退款审核"
      width="min(860px, calc(100vw - 24px))"
      append-to-body
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <template v-if="selectedTicket">
        <div class="refund-review-detail" v-loading="detailLoading">
          <section class="refund-review-detail__summary">
            <span class="refund-review-detail__icon">
              <el-icon><DocumentChecked /></el-icon>
            </span>
            <div class="refund-review-detail__main">
              <div class="refund-review-detail__code">{{ selectedTicket.code }}</div>
              <h3>{{ selectedTicket.title || '未命名退款工单' }}</h3>
              <p>{{ selectedTicket.description || '暂无工单描述' }}</p>
              <div class="refund-review-detail__meta">
                <span>{{ selectedTicket.accountName || '--' }}</span>
                <span>{{ formatTicketTime(selectedTicket.updatedAt) }}</span>
                <span class="refund-review-status" :class="toStatusMeta(selectedTicket.status).className">
                  {{ toStatusMeta(selectedTicket.status).label }}
                </span>
              </div>
            </div>
          </section>

          <RefundReviewPanel
            :ticket-id="selectedTicket.id"
            :ticket-category="selectedTicket.category || REFUND_CATEGORY"
            @reply-draft-ready="handleReplyDraft"
            @updated="handleRefundUpdated"
          />

          <section v-if="replyDraft" class="refund-review-draft">
            <div class="refund-review-draft__header">
              <div>
                <p class="refund-review-page__eyebrow">回复草稿</p>
                <h4>退款处理说明</h4>
              </div>
              <el-button :icon="CopyDocument" @click="copyReplyDraft">复制</el-button>
            </div>
            <el-input
              :model-value="replyDraft"
              type="textarea"
              readonly
              :autosize="{ minRows: 3, maxRows: 6 }"
            />
          </section>
        </div>
      </template>

      <template v-else>
        <div class="refund-review-empty">请选择一条退款售后工单。</div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, DocumentChecked, Refresh, Search } from '@element-plus/icons-vue'
import RefundReviewPanel from '../components/biz/RefundReviewPanel.vue'
import { getWorkOrderDetail, pageWorkOrders } from '../api/workOrder'
import {
  formatTicketTime,
  mapTicketStatus,
  TICKET_STATUS_OPTIONS,
  toPriorityMeta,
  toStatusMeta
} from '../utils/ticket'

const REFUND_CATEGORY = '退款售后'

const loading = ref(false)
const detailLoading = ref(false)
const tickets = ref([])
const selectedTicket = ref(null)
const detailDialogVisible = ref(false)
const replyDraft = ref('')
const queryForm = reactive({ keyword: '', status: '' })
const page = reactive({ pageNum: 1, pageSize: 20, total: 0 })

function normalizeTicket(item = {}) {
  return {
    id: item.id,
    code: item.code,
    title: item.title,
    description: item.description,
    category: item.category || REFUND_CATEGORY,
    priority: item.priority || '中',
    status: mapTicketStatus(item.status),
    accountName: item.accountName || item.assignee || '未分配',
    updatedAt: formatTicketTime(item.updatedAt),
    createdAt: formatTicketTime(item.createdAt)
  }
}

async function loadRefundTickets() {
  loading.value = true
  try {
    // 独立页只聚焦退款售后分类，退款金额和执行状态仍由后端审核接口负责。
    const response = await pageWorkOrders({
      keyword: queryForm.keyword || undefined,
      category: REFUND_CATEGORY,
      status: queryForm.status || undefined,
      pageNum: page.pageNum,
      pageSize: page.pageSize
    })
    const records = Array.isArray(response?.data?.records) ? response.data.records.map(normalizeTicket) : []
    tickets.value = records
    page.total = Number(response?.data?.total || records.length) || 0
  } catch (error) {
    tickets.value = []
    page.total = 0
    ElMessage.error(error.message || '退款售后工单加载失败')
  } finally {
    loading.value = false
  }
}

async function loadTicketDetail(id) {
  if (!id) {
    selectedTicket.value = null
    return
  }

  detailLoading.value = true
  try {
    const response = await getWorkOrderDetail(id)
    selectedTicket.value = response?.data ? normalizeTicket(response.data) : null
  } catch (error) {
    selectedTicket.value = null
    ElMessage.error(error.message || '退款工单详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function handleSearch() {
  page.pageNum = 1
  loadRefundTickets()
}

function handleCurrentChange(value) {
  page.pageNum = value
  loadRefundTickets()
}

function handleSizeChange(value) {
  page.pageSize = value
  page.pageNum = 1
  loadRefundTickets()
}

async function openReviewDialog(row) {
  replyDraft.value = ''
  selectedTicket.value = row
  detailDialogVisible.value = true
  await loadTicketDetail(row.id)
}

function handleReplyDraft(content) {
  replyDraft.value = content || ''
}

async function handleRefundUpdated() {
  const currentId = selectedTicket.value?.id
  await loadRefundTickets()
  if (currentId) {
    await loadTicketDetail(currentId)
  }
}

function handleDialogClosed() {
  selectedTicket.value = null
  replyDraft.value = ''
}

async function copyReplyDraft() {
  if (!replyDraft.value) return

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(replyDraft.value)
    } else {
      fallbackCopy(replyDraft.value)
    }
    ElMessage.success('回复草稿已复制')
  } catch (error) {
    ElMessage.error('回复草稿复制失败')
  }
}

function fallbackCopy(text) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'readonly')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

onMounted(loadRefundTickets)
</script>

<style scoped>
.refund-review-page {
  display: grid;
  gap: 16px;
  width: 100%;
  max-width: 100%;
  min-height: calc(100vh - 64px);
  margin: 0;
  padding: 0 40px 32px;
  background: linear-gradient(135deg, #eef5ff 0%, #ffffff 62%, #f7fbf4 100%);
  color: #16233f;
}

.refund-review-header,
.refund-review-toolbar,
.refund-review-table {
  border: 1px solid #dde7f4;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 14px 34px rgba(21, 46, 80, 0.07);
}

.refund-review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px;
}

.refund-review-header h2,
.refund-review-draft h4 {
  margin: 0;
  color: #17294f;
}

.refund-review-header__copy p:last-child {
  max-width: 640px;
  margin: 8px 0 0;
  color: #586b83;
  line-height: 1.7;
}

.refund-review-page__eyebrow {
  margin: 0 0 6px;
  color: #617895;
  font-size: 12px;
  font-weight: 650;
}

.refund-review-toolbar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 180px auto;
  gap: 12px;
  align-items: center;
  padding: 16px;
}

.refund-review-toolbar__button {
  min-width: 88px;
}

.refund-review-table {
  padding: 14px 16px 18px;
}

.refund-review-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.refund-review-priority,
.refund-review-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.2;
}

.refund-review-priority.is-low {
  background: #eef3f8;
  color: #5d6b7c;
}

.refund-review-priority.is-medium {
  background: #eaf2ff;
  color: #2d66ea;
}

.refund-review-priority.is-high {
  background: #fff4df;
  color: #a36a00;
}

.refund-review-priority.is-urgent {
  background: #fff0f0;
  color: #c45656;
}

.refund-review-status.is-pending {
  background: #fff7df;
  color: #996c00;
}

.refund-review-status.is-processing {
  background: #eaf2ff;
  color: #2d66ea;
}

.refund-review-status.is-solved {
  background: #e8faef;
  color: #17995c;
}

.refund-review-status.is-closed {
  background: #f1f3f7;
  color: #7f8898;
}

.refund-review-detail {
  display: grid;
  gap: 16px;
}

.refund-review-detail__summary {
  display: flex;
  gap: 14px;
  padding: 16px;
  border: 1px solid #e2eaf5;
  border-radius: 8px;
  background: #fbfdff;
}

.refund-review-detail__icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  place-items: center;
  border-radius: 8px;
  background: #17325f;
  color: #fff;
  font-size: 20px;
}

.refund-review-detail__main {
  min-width: 0;
}

.refund-review-detail__code {
  color: #73839a;
  font-size: 12px;
}

.refund-review-detail__main h3 {
  margin: 4px 0 0;
  color: #17294f;
  font-size: 18px;
}

.refund-review-detail__main p {
  margin: 8px 0 0;
  color: #586b83;
  line-height: 1.7;
}

.refund-review-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
  color: #7b8798;
  font-size: 12px;
}

.refund-review-draft {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid #dfe8f3;
  border-radius: 8px;
  background: #fff;
}

.refund-review-draft__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.refund-review-empty {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: #7a879d;
}

@media (max-width: 860px) {
  .refund-review-page {
    padding: 0 16px 24px;
  }

  .refund-review-header,
  .refund-review-toolbar {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .refund-review-header {
    display: grid;
  }

  .refund-review-pagination {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
