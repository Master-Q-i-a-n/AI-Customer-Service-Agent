<template>
  <section class="assistant-page" v-loading="initializing">
    <aside class="assistant-history">
      <div class="assistant-history__header">
        <span>历史会话</span>
        <el-button link type="primary" :loading="initializing" @click="startNewSession">新建</el-button>
      </div>

      <div v-if="historyFallback" class="assistant-history__empty">历史列表接口暂不可用，已显示本机缓存会话</div>
      <div v-else-if="historyUnavailable" class="assistant-history__empty">历史会话接口暂不可用，当前会话仍可使用</div>
      <div v-else-if="!sessionList.length" class="assistant-history__empty">暂无历史会话</div>
      <button
        v-for="item in sessionList"
        :key="item.id"
        type="button"
        class="assistant-history__item"
        :class="{ 'is-active': session?.id === item.id }"
        @click="selectSession(item.id)"
      >
        <span class="assistant-history__title">{{ sessionTitle(item) }}</span>
        <span class="assistant-history__meta">
          {{ routeLabel(item.route) }} · {{ formatMessageTime(item.updatedAt) }}
        </span>
      </button>
    </aside>

    <div class="assistant-panel">
      <div class="assistant-panel__header">
        <div>
          <p class="assistant-page__eyebrow">AI 客服</p>
          <h2 class="assistant-page__title">先对话，再转人工</h2>
        </div>
        <el-button class="assistant-panel__reset" :loading="initializing" @click="startNewSession">
          <el-icon><Refresh /></el-icon>
          新会话
        </el-button>
      </div>

      <div ref="messageList" class="assistant-messages">
        <div v-if="!messages.length" class="assistant-empty">
          <div class="assistant-empty__mark">AI</div>
          <p>可以直接描述商品咨询、订单物流、使用记录、故障或退款诉求。</p>
        </div>

        <article
          v-for="message in messages"
          :key="message.id"
          class="assistant-message"
          :class="{ 'is-assistant': message.role === 'assistant' }"
        >
          <div class="assistant-message__avatar">
            {{ message.role === 'assistant' ? 'AI' : '我' }}
          </div>
          <div class="assistant-message__body">
            <div class="assistant-message__meta">
              <span>{{ message.role === 'assistant' ? routeLabel(message.metadata?.route) : '用户消息' }}</span>
              <span>{{ formatMessageTime(message.createdAt) }}</span>
            </div>
            <div class="assistant-message__content">{{ message.content }}</div>
            <div v-if="message.metadata?.sources?.length" class="assistant-sources">
              <span class="assistant-sources__label">来源</span>
              <span
                v-for="source in message.metadata.sources"
                :key="source.id || source.document_id || source.title"
                class="assistant-sources__item"
              >
                {{ source.title || '知识库文档' }}
              </span>
            </div>
          </div>
        </article>
      </div>

      <div v-if="pendingDraft && !createdTicketId" class="assistant-ticket">
        <div>
          <p class="assistant-ticket__label">待确认工单</p>
          <h3 class="assistant-ticket__title">{{ pendingDraft.title }}</h3>
          <p class="assistant-ticket__desc">{{ pendingDraft.description }}</p>
        </div>
        <el-button type="primary" :loading="creatingTicket" @click="confirmTicket">
          <el-icon><DocumentChecked /></el-icon>
          生成工单
        </el-button>
      </div>

      <div v-else-if="createdTicketId" class="assistant-ticket is-created">
        <div>
          <p class="assistant-ticket__label">已转人工</p>
          <h3 class="assistant-ticket__title">工单已生成</h3>
          <p class="assistant-ticket__desc">人工客服会在“我的反馈”中继续处理。</p>
        </div>
        <el-button type="primary" plain @click="router.push('/feedback')">查看反馈</el-button>
      </div>

      <div class="assistant-composer">
        <el-input
          v-model.trim="draftMessage"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="500"
          show-word-limit
          placeholder="请输入你的问题..."
          @keydown.ctrl.enter.prevent="sendMessage"
        />
        <div class="assistant-composer__actions">
          <span class="assistant-composer__hint">Ctrl + Enter 发送</span>
          <el-button type="primary" :loading="sending" @click="sendMessage">
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, Promotion, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import {
  confirmAssistantTicket,
  createAssistantSession,
  getAssistantSession,
  listAssistantSessions,
  sendAssistantMessage
} from '../api/assistant'
import { sessionState } from '../store/session'

const router = useRouter()
const LOCAL_HISTORY_LIMIT = 20
const initializing = ref(false)
const sending = ref(false)
const creatingTicket = ref(false)
const draftMessage = ref('')
const session = ref(null)
const sessionList = ref([])
const historyUnavailable = ref(false)
const historyFallback = ref(false)
const messageList = ref(null)

const messages = computed(() => Array.isArray(session.value?.messages) ? session.value.messages : [])
const pendingDraft = computed(() => {
  const draft = session.value?.pendingTicketDraft
  return draft && Object.keys(draft).length ? draft : null
})
const createdTicketId = computed(() => session.value?.ticketId || '')

const routeTextMap = {
  GENERAL_CHAT: 'AI 客服',
  PRESALE: '售前咨询',
  KNOWLEDGE_QA: '知识答疑',
  ORDER_QUERY: '订单查询',
  USER_RECORD: '使用记录',
  AFTER_SALES_FAULT: '售后故障',
  REFUND_AFTER_SALES: '退款售后',
  CLARIFY: '补充信息',
  OUT_OF_SCOPE: '范围外'
}

async function startNewSession() {
  initializing.value = true
  try {
    const res = await createAssistantSession()
    session.value = res?.data || null
    rememberLocalSession(session.value?.id)
    await loadSessionList()
    await scrollToLatest()
  } catch (error) {
    session.value = null
    ElMessage.error(error.message || 'AI 客服会话创建失败')
  } finally {
    initializing.value = false
  }
}

async function loadSessionList() {
  try {
    const res = await listAssistantSessions()
    sessionList.value = Array.isArray(res?.data) ? res.data : []
    historyUnavailable.value = false
    historyFallback.value = false
    return true
  } catch (error) {
    // 历史列表是增强能力，接口暂未加载时不影响用户继续发起当前对话。
    if (isHistoryEndpointUnavailable(error)) {
      const loadedLocalHistory = await loadLocalSessionList()
      historyUnavailable.value = !loadedLocalHistory
      historyFallback.value = loadedLocalHistory
      return loadedLocalHistory
    }
    throw error
  }
}

async function loadInitialSession() {
  initializing.value = true
  try {
    const historyLoaded = await loadSessionList()
    if (historyLoaded && sessionList.value.length) {
      await selectSession(sessionList.value[0].id)
    } else {
      await startNewSession()
    }
  } catch (error) {
    ElMessage.error(error.message || 'AI 客服历史加载失败')
  } finally {
    initializing.value = false
  }
}

async function selectSession(id) {
  if (!id || session.value?.id === id) {
    return
  }
  initializing.value = true
  try {
    const res = await getAssistantSession(id)
    session.value = res?.data || null
    await scrollToLatest()
  } catch (error) {
    ElMessage.error(error.message || '会话加载失败')
  } finally {
    initializing.value = false
  }
}

async function sendMessage() {
  const content = draftMessage.value.trim()
  if (!content || sending.value) {
    return
  }
  if (!session.value?.id) {
    await startNewSession()
  }
  if (!session.value?.id) {
    return
  }

  sending.value = true
  draftMessage.value = ''
  try {
    const res = await sendAssistantMessage(session.value.id, content)
    session.value = res?.data || session.value
    rememberLocalSession(session.value?.id)
    await loadSessionList()
  } catch (error) {
    ElMessage.error(error.message || '消息发送失败')
  } finally {
    sending.value = false
    await scrollToLatest()
  }
}

async function confirmTicket() {
  if (!session.value?.id || !pendingDraft.value) {
    return
  }
  creatingTicket.value = true
  try {
    const res = await confirmAssistantTicket(session.value.id)
    session.value = res?.data || session.value
    rememberLocalSession(session.value?.id)
    await loadSessionList()
    ElMessage.success('工单已生成')
  } catch (error) {
    ElMessage.error(error.message || '工单生成失败')
  } finally {
    creatingTicket.value = false
    await scrollToLatest()
  }
}

function routeLabel(route) {
  return routeTextMap[route] || 'AI 回复'
}

function sessionTitle(item) {
  const draftTitle = item.pendingTicketDraft?.title
  return item.summary || draftTitle || '新的 AI 客服会话'
}

function formatMessageTime(value) {
  if (!value) {
    return ''
  }
  return String(value).slice(5, 16)
}

async function loadLocalSessionList() {
  const ids = readLocalSessionIds()
  const items = []
  for (const id of ids) {
    try {
      const res = await getAssistantSession(id)
      if (res?.data?.id) {
        items.push({ ...res.data, messages: [] })
      }
    } catch (error) {
      forgetLocalSession(id)
    }
  }
  sessionList.value = items
  return items.length > 0
}

function historyStorageKey() {
  const username = sessionState.user?.username || 'anonymous'
  return `workorder.assistant.sessions.${username}`
}

function readLocalSessionIds() {
  try {
    const value = JSON.parse(window.localStorage.getItem(historyStorageKey()) || '[]')
    return Array.isArray(value) ? value.filter(Boolean).slice(0, LOCAL_HISTORY_LIMIT) : []
  } catch (error) {
    return []
  }
}

function writeLocalSessionIds(ids) {
  try {
    window.localStorage.setItem(historyStorageKey(), JSON.stringify(ids.slice(0, LOCAL_HISTORY_LIMIT)))
  } catch (error) {
    // 本机缓存失败不影响后端会话落库。
  }
}

function rememberLocalSession(id) {
  if (!id) {
    return
  }
  const ids = readLocalSessionIds().filter(item => item !== id)
  writeLocalSessionIds([id, ...ids])
}

function forgetLocalSession(id) {
  writeLocalSessionIds(readLocalSessionIds().filter(item => item !== id))
}

function isHistoryEndpointUnavailable(error) {
  const responseMessage = error?.response?.data?.msg || error?.response?.data?.message || ''
  const message = `${error?.message || ''} ${responseMessage}`
  return error?.response?.status === 405 ||
    message.includes("Request method 'GET' is not supported") ||
    message.includes('No static resource api/assistant/sessions')
}

async function scrollToLatest() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

onMounted(loadInitialSession)
</script>

<style scoped>
.assistant-page {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  min-height: calc(100vh - 150px);
  color: #16233f;
}

.assistant-history {
  min-height: calc(100vh - 170px);
  overflow: hidden;
  border: 1px solid #e3eaf4;
  border-radius: 10px;
  background: #fff;
}

.assistant-history__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #e8eef7;
  color: #17294f;
  font-weight: 650;
}

.assistant-history__empty {
  padding: 18px 16px;
  color: #8390a7;
  font-size: 13px;
}

.assistant-history__item {
  display: grid;
  width: 100%;
  gap: 6px;
  padding: 13px 16px;
  border: 0;
  border-bottom: 1px solid #f0f4fa;
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.assistant-history__item:hover,
.assistant-history__item.is-active {
  background: #f1f6ff;
}

.assistant-history__title {
  overflow: hidden;
  color: #233654;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-history__meta {
  overflow: hidden;
  color: #7a879d;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-panel {
  display: flex;
  min-height: calc(100vh - 170px);
  flex-direction: column;
  border: 1px solid #e3eaf4;
  border-radius: 10px;
  background: #fbfdff;
  overflow: hidden;
}

.assistant-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 20px;
  border-bottom: 1px solid #e8eef7;
  background: #fff;
}

.assistant-page__eyebrow {
  margin: 0 0 4px;
  color: #697895;
  font-size: 12px;
}

.assistant-page__title {
  margin: 0;
  color: #17294f;
  font-size: 21px;
  font-weight: 650;
}

.assistant-panel__reset {
  border-radius: 8px;
}

.assistant-messages {
  display: flex;
  flex: 1;
  min-height: 360px;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding: 20px;
}

.assistant-empty {
  display: grid;
  min-height: 300px;
  place-items: center;
  align-content: center;
  gap: 14px;
  color: #748199;
  text-align: center;
}

.assistant-empty__mark {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  border-radius: 12px;
  background: #14305c;
  color: #fff;
  font-weight: 700;
}

.assistant-empty p {
  margin: 0;
}

.assistant-message {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.assistant-message.is-assistant {
  justify-content: flex-start;
}

.assistant-message__avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  place-items: center;
  border-radius: 8px;
  background: #dce9fa;
  color: #285ca8;
  font-size: 12px;
  font-weight: 700;
  order: 2;
}

.assistant-message.is-assistant .assistant-message__avatar {
  background: #e6f6ee;
  color: #16865a;
  order: 0;
}

.assistant-message__body {
  max-width: min(720px, calc(100% - 48px));
  padding: 13px 15px;
  border: 1px solid #dce7f6;
  border-radius: 8px;
  background: #fff;
}

.assistant-message:not(.is-assistant) .assistant-message__body {
  background: #eef5ff;
}

.assistant-message__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #7a879d;
  font-size: 12px;
}

.assistant-message__content {
  color: #2f405f;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.assistant-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.assistant-sources__label {
  color: #7a879d;
  font-size: 12px;
}

.assistant-sources__item {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  background: #f1f4f8;
  color: #4f6079;
  font-size: 12px;
}

.assistant-ticket {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 0 20px 16px;
  padding: 16px;
  border: 1px solid #f0d59e;
  border-radius: 8px;
  background: #fff9ec;
}

.assistant-ticket.is-created {
  border-color: #bfe6d0;
  background: #f0fbf5;
}

.assistant-ticket__label {
  margin: 0 0 4px;
  color: #8a6a22;
  font-size: 12px;
}

.assistant-ticket__title {
  margin: 0;
  color: #233654;
  font-size: 16px;
  font-weight: 650;
}

.assistant-ticket__desc {
  display: -webkit-box;
  margin: 8px 0 0;
  overflow: hidden;
  color: #5c6980;
  line-height: 1.7;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.assistant-composer {
  padding: 18px 20px;
  border-top: 1px solid #e8eef7;
  background: #fff;
}

.assistant-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.assistant-composer__hint {
  color: #7a879d;
  font-size: 12px;
}

:deep(.el-button--primary) {
  background: #17325f;
  border-color: #17325f;
}

:deep(.el-textarea__inner) {
  border-radius: 8px;
}

@media (max-width: 760px) {
  .assistant-page {
    grid-template-columns: 1fr;
  }

  .assistant-history {
    min-height: auto;
  }

  .assistant-panel__header,
  .assistant-ticket,
  .assistant-composer__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .assistant-message__body {
    max-width: calc(100% - 46px);
  }
}
</style>
