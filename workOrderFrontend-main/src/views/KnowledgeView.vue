<template>
  <section class="knowledge-page">
    <div class="knowledge-chat">
      <div class="knowledge-chat__header">
        <div>
          <p class="knowledge-page__eyebrow">知识问答</p>
          <h2 class="knowledge-page__title">基于知识库快速获取答案</h2>
        </div>
      </div>

      <div ref="messageList" class="knowledge-chat__messages">
        <div v-if="!messages.length" class="knowledge-chat__empty">
          输入问题后，系统会从知识库中检索并生成回答。
        </div>

        <article
          v-for="message in messages"
          :key="message.id"
          class="knowledge-message"
          :class="{ 'is-assistant': message.role === 'assistant' }"
        >
          <div class="knowledge-message__role">
            {{ message.role === 'assistant' ? 'AI' : '我' }}
          </div>
          <div class="knowledge-message__body">
            <div class="knowledge-message__content">{{ message.content }}</div>
            <div v-if="message.sources?.length" class="knowledge-message__sources">
              <span class="knowledge-message__source-label">来源</span>
              <span
                v-for="source in message.sources"
                :key="source.id"
                class="knowledge-message__source"
              >
                {{ source.title }}
              </span>
            </div>
          </div>
        </article>
      </div>

      <div class="knowledge-composer">
        <el-input
          v-model.trim="question"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="500"
          show-word-limit
          placeholder="请输入你的问题..."
          @keydown.ctrl.enter.prevent="sendQuestion"
        />
        <div class="knowledge-composer__actions">
          <span class="knowledge-composer__hint">Ctrl + Enter 发送</span>
          <el-button type="primary" :loading="asking" @click="sendQuestion">发送</el-button>
        </div>
      </div>
    </div>

    <aside v-if="isAdmin" class="knowledge-admin">
      <div class="knowledge-admin__header">
        <div>
          <p class="knowledge-page__eyebrow">知识库管理</p>
          <h3 class="knowledge-admin__title">文档</h3>
        </div>
        <el-button type="primary" :loading="uploading" @click="openFilePicker">
          <el-icon><Upload /></el-icon>
          上传
        </el-button>
      </div>

      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,.docx,.txt"
        class="knowledge-admin__file-input"
        @change="handleFileSelect"
      />

      <div v-loading="documentsLoading" class="knowledge-admin__list">
        <div v-if="!documents.length && !documentsLoading" class="knowledge-admin__empty">暂无文档</div>

        <div v-for="document in documents" :key="document.id" class="knowledge-document">
          <div class="knowledge-document__main">
            <div class="knowledge-document__title">{{ document.title }}</div>
            <div class="knowledge-document__meta">
              {{ document.fileName }} · {{ formatFileSize(document.fileSize) }} · {{ document.createdAt }}
            </div>
          </div>
          <el-button
            link
            type="danger"
            :loading="deletingId === document.id"
            @click="removeDocument(document)"
          >
            删除
          </el-button>
        </div>
      </div>
    </aside>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import {
  askKnowledge,
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
  uploadKnowledgeDocument
} from '../api/knowledge'
import { sessionState } from '../store/session'
import { normalizeRole } from '../utils/auth'

const question = ref('')
const asking = ref(false)
const messages = ref([])
const documents = ref([])
const documentsLoading = ref(false)
const uploading = ref(false)
const deletingId = ref('')
const fileInputRef = ref(null)
const messageList = ref(null)
const isAdmin = computed(() => normalizeRole(sessionState.user?.role) === 'admin')

function createMessage(role, content, sources = []) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    sources
  }
}

async function sendQuestion() {
  const value = question.value.trim()
  if (!value || asking.value) {
    return
  }

  messages.value.push(createMessage('user', value))
  question.value = ''
  asking.value = true
  await scrollToLatest()

  try {
    const res = await askKnowledge(value)
    const answer = res?.data?.answer || '暂未获得有效回答'
    const sources = Array.isArray(res?.data?.sourceDocuments) ? res.data.sourceDocuments : []
    messages.value.push(createMessage('assistant', answer, sources))
  } catch (error) {
    messages.value.push(createMessage('assistant', error.message || '知识问答失败，请稍后再试'))
  } finally {
    asking.value = false
    await scrollToLatest()
  }
}

async function loadDocuments() {
  if (!isAdmin.value) {
    return
  }

  documentsLoading.value = true
  try {
    const res = await listKnowledgeDocuments()
    documents.value = Array.isArray(res?.data?.items) ? res.data.items : []
  } catch (error) {
    documents.value = []
    ElMessage.error(error.message || '知识库文档加载失败')
  } finally {
    documentsLoading.value = false
  }
}

function openFilePicker() {
  fileInputRef.value?.click()
}

async function handleFileSelect(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) {
    return
  }

  uploading.value = true
  try {
    await uploadKnowledgeDocument(file)
    await loadDocuments()
    ElMessage.success('文档已加入知识库')
  } catch (error) {
    ElMessage.error(error.message || '知识库文档上传失败')
  } finally {
    uploading.value = false
  }
}

async function removeDocument(document) {
  try {
    await ElMessageBox.confirm(`确认删除“${document.title}”吗？删除后将不再参与知识检索。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch (error) {
    return
  }

  deletingId.value = document.id
  try {
    await deleteKnowledgeDocument(document.id)
    await loadDocuments()
    ElMessage.success('文档已删除')
  } catch (error) {
    ElMessage.error(error.message || '知识库文档删除失败')
  } finally {
    deletingId.value = ''
  }
}

function formatFileSize(size) {
  const value = Number(size || 0)
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

async function scrollToLatest() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}

onMounted(loadDocuments)
</script>

<style scoped>
.knowledge-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  min-height: calc(100vh - 150px);
}

.knowledge-chat,
.knowledge-admin {
  border: 1px solid #e7edf6;
  border-radius: 12px;
  background: #fff;
}

.knowledge-chat {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.knowledge-chat__header,
.knowledge-admin__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid #edf1f7;
}

.knowledge-page__eyebrow {
  margin: 0 0 4px;
  color: #6b7d98;
  font-size: 12px;
}

.knowledge-page__title,
.knowledge-admin__title {
  margin: 0;
  color: #17325f;
  font-size: 20px;
  font-weight: 600;
}

.knowledge-admin__title {
  font-size: 18px;
}

.knowledge-chat__messages {
  display: flex;
  flex: 1;
  min-height: 360px;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px;
  overflow-y: auto;
}

.knowledge-chat__empty,
.knowledge-admin__empty {
  color: #7f8ba0;
  font-size: 14px;
}

.knowledge-message {
  display: flex;
  gap: 12px;
}

.knowledge-message__role {
  display: flex;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #eaf2ff;
  color: #2d66ea;
  font-size: 12px;
  font-weight: 600;
}

.knowledge-message.is-assistant .knowledge-message__role {
  background: #e8faef;
  color: #17995c;
}

.knowledge-message__body {
  min-width: 0;
  max-width: min(760px, calc(100% - 44px));
}

.knowledge-message__content {
  white-space: pre-wrap;
  word-break: break-word;
  color: #33425c;
  line-height: 1.8;
}

.knowledge-message__sources {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.knowledge-message__source-label {
  color: #7f8ba0;
  font-size: 12px;
}

.knowledge-message__source {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  background: #f1f4f8;
  color: #50607c;
  font-size: 12px;
}

.knowledge-composer {
  padding: 18px 20px;
  border-top: 1px solid #edf1f7;
}

.knowledge-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.knowledge-composer__hint {
  color: #7f8ba0;
  font-size: 12px;
}

.knowledge-admin {
  min-width: 0;
}

.knowledge-admin__file-input {
  display: none;
}

.knowledge-admin__list {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 220px;
}

.knowledge-document {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #f0f3f8;
}

.knowledge-document:last-child {
  border-bottom: 0;
}

.knowledge-document__main {
  min-width: 0;
}

.knowledge-document__title {
  overflow: hidden;
  color: #17325f;
  font-size: 14px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-document__meta {
  margin-top: 4px;
  overflow: hidden;
  color: #7f8ba0;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .knowledge-page {
    grid-template-columns: 1fr;
  }
}
</style>
