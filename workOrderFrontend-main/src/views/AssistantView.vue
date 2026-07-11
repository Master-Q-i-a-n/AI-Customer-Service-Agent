<template>
  <section class="assistant-page" v-loading="initializing">
    <button
      v-if="historyOpen"
      type="button"
      class="assistant-history-backdrop"
      aria-label="关闭历史会话"
      @click="historyOpen = false"
    />

    <aside
      class="assistant-history"
      :class="{ 'is-open': historyOpen }"
      :aria-hidden="isMobileViewport && !historyOpen"
    >
      <div class="assistant-history__header">
        <span>历史会话</span>
        <div class="assistant-history__header-actions">
          <el-tooltip content="开始新对话" placement="bottom">
            <el-button circle text aria-label="开始新对话" @click="startNewSession">
              <el-icon><Plus /></el-icon>
            </el-button>
          </el-tooltip>
          <el-button
            class="assistant-history__close"
            circle
            text
            aria-label="关闭历史会话"
            @click="historyOpen = false"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>

      <div class="assistant-history__search">
        <el-input v-model="historyQuery" clearable placeholder="搜索会话" aria-label="搜索历史会话">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <div class="assistant-history__list">
        <div v-if="historyFallback" class="assistant-history__empty">历史列表接口暂不可用，已显示本机缓存会话</div>
        <div v-else-if="historyUnavailable" class="assistant-history__empty">历史会话接口暂不可用，当前会话仍可使用</div>
        <div v-else-if="!sessionList.length" class="assistant-history__empty">暂无历史会话</div>
        <div v-else-if="!filteredSessionList.length" class="assistant-history__empty">没有匹配的会话</div>
        <article
          v-for="item in filteredSessionList"
          :key="item.id"
          class="assistant-history__item"
          :class="{ 'is-active': session?.id === item.id }"
        >
          <button type="button" class="assistant-history__select" @click="selectSession(item.id)">
            <span class="assistant-history__title">{{ sessionTitle(item) }}</span>
            <span class="assistant-history__meta">
              {{ routeLabel(item.route) }} · {{ formatMessageTime(item.updatedAt) }}
            </span>
          </button>
          <el-tooltip content="删除会话" placement="right">
            <el-button
              class="assistant-history__delete"
              circle
              text
              :loading="deletingSessionId === item.id"
              :aria-label="`删除 ${sessionTitle(item)}`"
              @click="deleteSession(item)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </article>
      </div>
    </aside>

    <div class="assistant-panel">
      <div class="assistant-panel__header">
        <div>
          <p class="assistant-page__eyebrow">AI 客服</p>
          <h2 class="assistant-page__title">客服与选购助手</h2>
        </div>
        <div class="assistant-panel__actions">
          <el-tooltip content="历史会话" placement="bottom">
            <el-button class="assistant-panel__history" circle plain aria-label="打开历史会话" @click="historyOpen = true">
              <el-icon><ChatDotRound /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="开始新对话" placement="bottom">
            <el-button class="assistant-panel__reset" circle plain aria-label="开始新对话" @click="startNewSession">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <div v-if="requirementChips.length" class="assistant-requirements" aria-label="当前选购需求">
        <span v-for="item in requirementChips" :key="item" class="assistant-requirement-chip">{{ item }}</span>
      </div>

      <div ref="messageList" class="assistant-messages" aria-live="polite">
        <div v-if="!messages.length" class="assistant-empty">
          <div class="assistant-empty__mark">AI</div>
          <p>可以直接描述选购需求、订单物流、使用记录、故障或退款诉求。</p>
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
            <div v-if="messageImages(message).length" class="assistant-message-images">
              <button
                v-for="(image, index) in messageImages(message)"
                :key="image.serverPath || image.url || index"
                type="button"
                class="assistant-message-image"
                :aria-label="`查看图片 ${image.name || index + 1}`"
                @click="previewImage(image)"
              >
                <img :src="image.previewUrl" :alt="image.name || '售后图片'" />
              </button>
            </div>
            <div
              v-if="message.role === 'assistant' && message.metadata?.vision_evidence?.summary"
              class="assistant-vision-evidence"
            >
              <span>视觉识别</span>
              <p>{{ message.metadata.vision_evidence.summary }}</p>
            </div>
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

            <div
              v-if="messageProducts(message).length"
              class="assistant-products"
              :class="{
                'is-single': messageProducts(message).length === 1,
                'is-pair': messageProducts(message).length === 2
              }"
            >
              <article
                v-for="product in messageProducts(message)"
                :key="product.sku_id"
                class="assistant-product"
              >
                <button
                  type="button"
                  class="assistant-product__image-button"
                  :aria-label="`查看 ${product.name} 详情`"
                  @click="openProductDetail(product)"
                >
                  <img :src="product.image_url" :alt="product.name" class="assistant-product__image" />
                </button>
                <div class="assistant-product__content">
                  <div class="assistant-product__topline">
                    <span class="assistant-product__sku">{{ product.sku_name }}</span>
                    <span class="assistant-product__stock">现货 {{ product.stock }}</span>
                  </div>
                  <h3 class="assistant-product__name">{{ product.name }}</h3>
                  <p class="assistant-product__price">{{ formatProductPrice(product.price) }}</p>
                  <div class="assistant-product__highlights">
                    <span v-for="item in product.highlights" :key="item">{{ item }}</span>
                  </div>
                  <ul v-if="product.match_reasons?.length" class="assistant-product__reasons">
                    <li v-for="reason in product.match_reasons" :key="reason">{{ reason }}</li>
                  </ul>
                  <p v-for="warning in product.warnings" :key="warning" class="assistant-product__warning">
                    {{ warning }}
                  </p>
                  <div class="assistant-product__actions">
                    <el-button plain size="small" @click="openProductDetail(product)">
                      <el-icon><View /></el-icon>
                      查看详情
                    </el-button>
                    <el-button
                      size="small"
                      :type="isCompareSelected(product) ? 'success' : 'primary'"
                      plain
                      @click="toggleCompare(product)"
                    >
                      <el-icon><Check v-if="isCompareSelected(product)" /><Plus v-else /></el-icon>
                      {{ isCompareSelected(product) ? '已加入' : '加入对比' }}
                    </el-button>
                  </div>
                </div>
              </article>
            </div>

            <div v-if="messageComparison(message)" class="assistant-comparison">
              <div class="assistant-comparison__header">
                <span>参数对比</span>
                <strong>{{ messageComparison(message).product_names.join(' / ') }}</strong>
              </div>
              <div class="assistant-comparison__table">
                <div class="assistant-comparison__row is-head">
                  <span>对比项</span>
                  <strong v-for="name in messageComparison(message).product_names" :key="name">{{ name }}</strong>
                </div>
                <div
                  v-for="row in messageComparison(message).rows"
                  :key="row.label"
                  class="assistant-comparison__row"
                >
                  <span>{{ row.label }}</span>
                  <strong v-for="(value, index) in row.values" :key="`${row.label}-${index}`">{{ value }}</strong>
                </div>
              </div>
              <p class="assistant-comparison__recommendation">
                {{ messageComparison(message).recommendation }}
              </p>
            </div>
          </div>
        </article>
      </div>

      <div v-if="currentCompareSelection.length" class="assistant-compare-tray">
        <div class="assistant-compare-tray__selection">
          <span class="assistant-compare-tray__label">已选 {{ currentCompareSelection.length }}/2</span>
          <span v-for="product in currentCompareSelection" :key="product.sku_id" class="assistant-compare-chip">
            {{ product.name }}
            <button type="button" :aria-label="`移除 ${product.name}`" @click="removeCompare(product.sku_id)">
              <el-icon><Close /></el-icon>
            </button>
          </span>
        </div>
        <el-button type="primary" :disabled="currentCompareSelection.length !== 2" :loading="sending" @click="compareSelected">
          <el-icon><DataAnalysis /></el-icon>
          开始对比
        </el-button>
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
        <div v-if="draftImages.length" class="assistant-composer-images">
          <div v-for="(image, index) in draftImages" :key="image.uid" class="assistant-composer-image">
            <button type="button" @click="previewImage(image)">
              <img :src="image.url" :alt="image.name" />
            </button>
            <button
              type="button"
              class="assistant-composer-image__remove"
              :aria-label="`移除图片 ${image.name}`"
              @click="removeDraftImage(index)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </div>
        <el-input
          v-model.trim="draftMessage"
          type="textarea"
          :rows="2"
          resize="none"
          maxlength="500"
          show-word-limit
          placeholder="继续补充需求或选择商品进行对比..."
          @keydown.ctrl.enter.prevent="sendMessage"
        />
        <div class="assistant-composer__actions">
          <div class="assistant-composer__tools">
            <el-button plain :loading="uploadingImages" :disabled="draftImages.length >= 5" @click="openImagePicker">
              <el-icon><UploadFilled /></el-icon>
              添加售后图片
            </el-button>
            <span class="assistant-composer__hint">最多 5 张，单张不超过 7MB</span>
          </div>
          <el-button type="primary" :loading="sending" :disabled="uploadingImages" @click="sendMessage">
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>
        <input
          ref="imageInputRef"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
          multiple
          class="assistant-hidden-input"
          @change="handleImageSelect"
        />
      </div>
    </div>

    <el-drawer
      v-model="detailVisible"
      :size="drawerSize"
      :with-header="false"
      class="assistant-product-drawer"
    >
      <template v-if="selectedProduct">
        <div class="assistant-detail__toolbar">
          <span>商品详情</span>
          <el-button circle text aria-label="关闭商品详情" @click="detailVisible = false">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <img :src="selectedProduct.image_url" :alt="selectedProduct.name" class="assistant-detail__image" />
        <div class="assistant-detail__identity">
          <span>{{ selectedProduct.sku_name }}</span>
          <h2>{{ selectedProduct.name }}</h2>
          <div class="assistant-detail__commerce">
            <strong>{{ formatProductPrice(selectedProduct.price) }}</strong>
            <span>现货 {{ selectedProduct.stock }} 件</span>
          </div>
          <p>{{ selectedProduct.summary }}</p>
        </div>
        <div class="assistant-detail__section">
          <h3>核心规格</h3>
          <dl class="assistant-detail__specs">
            <div v-for="row in productAttributeRows(selectedProduct)" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
        </div>
        <div v-if="selectedProduct.match_reasons?.length" class="assistant-detail__section">
          <h3>适合你的原因</h3>
          <ul class="assistant-detail__reasons">
            <li v-for="reason in selectedProduct.match_reasons" :key="reason">{{ reason }}</li>
          </ul>
        </div>
        <div class="assistant-detail__footer">
          <el-button
            type="primary"
            :plain="!isCompareSelected(selectedProduct)"
            @click="toggleCompare(selectedProduct)"
          >
            <el-icon><Check v-if="isCompareSelected(selectedProduct)" /><Plus v-else /></el-icon>
            {{ isCompareSelected(selectedProduct) ? '已加入对比' : '加入对比' }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  ChatDotRound,
  Close,
  DataAnalysis,
  Delete,
  DocumentChecked,
  Plus,
  Promotion,
  Refresh,
  Search,
  UploadFilled,
  View
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import {
  confirmAssistantTicket,
  deleteAssistantSession,
  getAssistantSession,
  listAssistantSessions,
  sendAssistantMessage,
  startAssistantConversation
} from '../api/assistant'
import { uploadFile } from '../api/file'
import { sessionState } from '../store/session'
import { normalizeImageList, resolveAssetUrl } from '../utils/ticket'

const router = useRouter()
const LOCAL_HISTORY_LIMIT = 20
const initializing = ref(false)
const sending = ref(false)
const uploadingImages = ref(false)
const creatingTicket = ref(false)
const deletingSessionId = ref('')
const draftMessage = ref('')
const draftImages = ref([])
const imageInputRef = ref(null)
const historyQuery = ref('')
const historyOpen = ref(false)
const session = ref(null)
const sessionList = ref([])
const historyUnavailable = ref(false)
const historyFallback = ref(false)
const messageList = ref(null)
const compareSelections = ref({})
const detailVisible = ref(false)
const selectedProduct = ref(null)
const viewportWidth = ref(typeof window === 'undefined' ? 1280 : window.innerWidth)

const messages = computed(() => Array.isArray(session.value?.messages) ? session.value.messages : [])
const pendingDraft = computed(() => {
  const draft = session.value?.pendingTicketDraft
  return draft && Object.keys(draft).length ? draft : null
})
const createdTicketId = computed(() => session.value?.ticketId || '')
const currentCompareSelection = computed(() => {
  const id = session.value?.id
  return id && Array.isArray(compareSelections.value[id]) ? compareSelections.value[id] : []
})
const drawerSize = computed(() => viewportWidth.value <= 960 ? '100%' : '480px')
const isMobileViewport = computed(() => viewportWidth.value <= 960)
const filteredSessionList = computed(() => {
  const keyword = historyQuery.value.trim().toLowerCase()
  if (!keyword) {
    return sessionList.value
  }
  return sessionList.value.filter(item => {
    const searchable = `${sessionTitle(item)} ${routeLabel(item.route)}`.toLowerCase()
    return searchable.includes(keyword)
  })
})
const presaleState = computed(() => session.value?.presaleState || session.value?.presale_state || {})
const requirementChips = computed(() => {
  const state = presaleState.value
  const items = []
  if (state.budget_unlimited) {
    items.push('预算不限')
  } else {
    if (state.budget_target != null) {
      items.push(`目标预算 ${formatBudget(state.budget_target)}`)
    }
    if (state.budget_min != null && state.budget_max != null) {
      const label = state.budget_target != null ? '推荐范围' : '预算范围'
      items.push(`${label} ${formatBudget(state.budget_min)}–${formatBudget(state.budget_max)}`)
    } else if (state.budget_max != null) {
      items.push(`预算上限 ${formatBudget(state.budget_max)}`)
    }
  }
  if (state.home_size_sqm != null) {
    items.push(`${state.home_size_sqm}㎡`)
  } else if (state.home_size_level) {
    items.push({ SMALL: '小户型', MEDIUM: '中等户型', LARGE: '大户型' }[state.home_size_level] || state.home_size_level)
  }
  if (Array.isArray(state.floor_types) && state.floor_types.length) {
    items.push(state.floor_types.join('、'))
  }
  if (state.has_pet === true) {
    items.push('宠物家庭')
  } else if (state.has_pet === false) {
    items.push('无宠物')
  }
  if (state.station_preference === true) {
    items.push('需要基站')
  } else if (state.station_preference === false) {
    items.push('无需基站')
  }
  if (state.noise_sensitive === true) {
    items.push('低噪偏好')
  }
  return items
})

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
  // 新会话仅是本地草稿，首条消息发送成功后才会写入后端历史。
  session.value = {
    id: '',
    status: 'ACTIVE',
    route: '',
    summary: '',
    pendingTicketDraft: {},
    presaleState: {},
    ticketId: '',
    messages: [],
    createdAt: '',
    updatedAt: ''
  }
  detailVisible.value = false
  selectedProduct.value = null
  draftImages.value = []
  historyOpen.value = false
  historyQuery.value = ''
  await scrollToLatest()
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
  if (!id) {
    return
  }
  if (session.value?.id === id) {
    historyOpen.value = false
    return
  }
  initializing.value = true
  try {
    const res = await getAssistantSession(id)
    session.value = res?.data || null
    detailVisible.value = false
    historyOpen.value = false
    await scrollToLatest()
  } catch (error) {
    ElMessage.error(error.message || '会话加载失败')
  } finally {
    initializing.value = false
  }
}

async function sendMessage() {
  const content = draftMessage.value.trim()
  if ((!content && !draftImages.value.length) || sending.value || uploadingImages.value) {
    return
  }
  const sent = await submitMessage(
    content || '请分析这些售后图片。',
    draftImages.value.map(image => ({
      name: image.name,
      serverPath: image.serverPath,
      contentType: image.contentType,
      size: image.size
    }))
  )
  if (sent) {
    draftMessage.value = ''
    draftImages.value = []
  }
}

async function submitMessage(content, images = []) {
  sending.value = true
  try {
    const res = session.value?.id
      ? await sendAssistantMessage(session.value.id, content, images)
      : await startAssistantConversation(content, images)
    session.value = res?.data || session.value
    rememberLocalSession(session.value?.id)
    await loadSessionList()
    return true
  } catch (error) {
    ElMessage.error(error.message || '消息发送失败')
    return false
  } finally {
    sending.value = false
    await scrollToLatest()
  }
}

function openImagePicker() {
  imageInputRef.value?.click()
}

async function handleImageSelect(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return

  const remaining = 5 - draftImages.value.length
  const selected = files.slice(0, remaining)
  uploadingImages.value = true
  try {
    for (const file of selected) {
      if (!file.type.startsWith('image/')) {
        ElMessage.warning(`${file.name} 不是支持的图片格式`)
        continue
      }
      if (file.size > 7 * 1024 * 1024) {
        ElMessage.warning(`${file.name} 超过 7MB，未上传`)
        continue
      }
      const response = await uploadFile(file, 'image')
      const uploaded = normalizeImageList([{
        ...(response?.data || {}),
        contentType: response?.data?.contentType || file.type,
        size: response?.data?.size || file.size
      }])[0]
      if (uploaded?.serverPath) {
        draftImages.value.push(uploaded)
      }
    }
    if (files.length > remaining) {
      ElMessage.warning('每条消息最多添加 5 张图片')
    }
  } catch (error) {
    ElMessage.error(error.message || '图片上传失败')
  } finally {
    uploadingImages.value = false
  }
}

function removeDraftImage(index) {
  draftImages.value.splice(index, 1)
}

function messageImages(message) {
  const images = Array.isArray(message?.metadata?.images) ? message.metadata.images : []
  return images.map(image => ({
    ...image,
    previewUrl: resolveAssetUrl(image.url || image.serverPath || '')
  })).filter(image => image.previewUrl)
}

function previewImage(image) {
  const url = image?.previewUrl || resolveAssetUrl(image?.url || image?.serverPath || '')
  if (url) {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

async function deleteSession(item) {
  if (!item?.id || deletingSessionId.value) {
    return
  }
  try {
    await ElMessageBox.confirm(
      '删除后会话将不再出现在历史列表中，但系统会保留原始记录。',
      '删除会话',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (error) {
    return
  }

  deletingSessionId.value = item.id
  try {
    await deleteAssistantSession(item.id)
    forgetLocalSession(item.id)
    const remainingSelections = { ...compareSelections.value }
    delete remainingSelections[item.id]
    compareSelections.value = remainingSelections
    const deletedCurrentSession = session.value?.id === item.id

    await loadSessionList()
    if (deletedCurrentSession) {
      if (sessionList.value.length) {
        await selectSession(sessionList.value[0].id)
      } else {
        await startNewSession()
      }
    }
    ElMessage.success('会话已删除')
  } catch (error) {
    ElMessage.error(error.message || '会话删除失败')
  } finally {
    deletingSessionId.value = ''
  }
}

function messageProducts(message) {
  return Array.isArray(message?.metadata?.products) ? message.metadata.products : []
}

function messageComparison(message) {
  const comparison = message?.metadata?.comparison
  return comparison && Array.isArray(comparison.rows) && Array.isArray(comparison.product_names)
    ? comparison
    : null
}

function openProductDetail(product) {
  selectedProduct.value = product
  detailVisible.value = true
}

function isCompareSelected(product) {
  return currentCompareSelection.value.some(item => item.sku_id === product?.sku_id)
}

function toggleCompare(product) {
  if (!product?.sku_id || !session.value?.id) {
    return
  }
  if (isCompareSelected(product)) {
    removeCompare(product.sku_id)
    return
  }
  if (currentCompareSelection.value.length >= 2) {
    ElMessage.warning('最多选择两款商品进行对比')
    return
  }
  compareSelections.value = {
    ...compareSelections.value,
    [session.value.id]: [...currentCompareSelection.value, product]
  }
}

function removeCompare(skuId) {
  if (!session.value?.id) {
    return
  }
  compareSelections.value = {
    ...compareSelections.value,
    [session.value.id]: currentCompareSelection.value.filter(item => item.sku_id !== skuId)
  }
}

async function compareSelected() {
  if (currentCompareSelection.value.length !== 2 || sending.value) {
    return
  }
  const [first, second] = currentCompareSelection.value
  await submitMessage(`请对比 ${first.name} 和 ${second.name}`)
}

function formatProductPrice(value) {
  const amount = Number(value)
  return Number.isFinite(amount) ? `¥${amount.toFixed(0)}` : '价格待确认'
}

function formatBudget(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) {
    return '¥--'
  }
  return `¥${Number.isInteger(amount) ? amount : amount.toFixed(2).replace(/\.?0+$/, '')}`
}

function productAttributeRows(product) {
  const attributes = product?.attributes || {}
  const booleanLabel = value => value ? '支持' : '不支持'
  return [
    { label: '适用面积', value: attributes.home_size_max ? `最高 ${attributes.home_size_max}㎡` : '--' },
    { label: '适用地面', value: Array.isArray(attributes.floor_types) ? attributes.floor_types.join('、') : '--' },
    { label: '吸力', value: attributes.suction_pa ? `${attributes.suction_pa}Pa` : '--' },
    { label: '续航', value: attributes.runtime_minutes ? `${attributes.runtime_minutes} 分钟` : '--' },
    { label: '导航方式', value: attributes.navigation || '--' },
    { label: '避障方式', value: attributes.obstacle_avoidance || '--' },
    { label: '基站', value: attributes.station_type || '无' },
    { label: '拖布抬升', value: booleanLabel(attributes.mop_lift) },
    { label: '防毛发缠绕', value: booleanLabel(attributes.anti_tangle) },
    { label: '工作噪音', value: attributes.noise_db ? `约 ${attributes.noise_db}dB` : '--' }
  ]
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
      if (res?.data?.id && Array.isArray(res.data.messages) && res.data.messages.length) {
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

function handleViewportResize() {
  viewportWidth.value = window.innerWidth
  if (viewportWidth.value > 960) {
    historyOpen.value = false
  }
}

function handleWindowKeydown(event) {
  if (event.key === 'Escape') {
    historyOpen.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('keydown', handleWindowKeydown)
  loadInitialSession()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('keydown', handleWindowKeydown)
})
</script>

<style scoped>
.assistant-page {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  height: calc(100dvh - 152px);
  min-height: 0;
  overflow: hidden;
  color: #16233f;
}

.assistant-history-backdrop {
  display: none;
}

.assistant-history {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e3eaf4;
  border-radius: 8px;
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

.assistant-history__header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.assistant-history__close {
  display: none;
}

.assistant-history__search {
  padding: 12px 14px;
  border-bottom: 1px solid #edf1f6;
}

.assistant-history__search :deep(.el-input__wrapper) {
  border-radius: 6px;
  box-shadow: 0 0 0 1px #dfe6ef inset;
}

.assistant-history__list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.assistant-history__empty {
  padding: 18px 16px;
  color: #8390a7;
  font-size: 13px;
}

.assistant-history__item {
  display: flex;
  align-items: stretch;
  width: 100%;
  min-height: 66px;
  margin: 0;
  border-bottom: 1px solid #f0f4fa;
  background: #fff;
  color: inherit;
  position: relative;
}

.assistant-history__item:hover {
  background: #f7f9fc;
}

.assistant-history__item.is-active {
  background: #f1f6ff;
}

.assistant-history__item.is-active::before {
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 0;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: #2f6fe4;
  content: "";
}

.assistant-history__select {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 6px;
  padding: 13px 4px 13px 18px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.assistant-history__delete {
  align-self: center;
  flex: 0 0 auto;
  margin: 0 8px;
  color: #7a879d;
  opacity: 0;
  transition: color 0.16s ease, background-color 0.16s ease, opacity 0.16s ease;
}

.assistant-history__item:hover .assistant-history__delete,
.assistant-history__item:focus-within .assistant-history__delete {
  opacity: 1;
}

.assistant-history__delete:hover {
  color: #c2410c;
  background: #fff1ec;
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
  height: 100%;
  min-height: 0;
  flex-direction: column;
  border: 1px solid #e3eaf4;
  border-radius: 8px;
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

.assistant-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
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
  flex: 0 0 auto;
}

.assistant-panel__history {
  display: none;
}

.assistant-requirements {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  gap: 8px;
  padding: 11px 20px;
  border-bottom: 1px solid #e8eef7;
  background: #f8fafc;
}

.assistant-requirement-chip {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  padding: 4px 9px;
  border: 1px solid #dce5ef;
  border-radius: 6px;
  background: #fff;
  color: #42536b;
  font-size: 12px;
  font-weight: 600;
}

.assistant-messages {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 20px;
  scrollbar-gutter: stable;
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
  max-width: min(980px, calc(100% - 48px));
  padding: 13px 15px;
  border: 1px solid #dce7f6;
  border-radius: 8px;
  background: #fff;
}

.assistant-message.is-assistant .assistant-message__body {
  border: 0;
  background: transparent;
  padding: 2px 0 0;
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

.assistant-message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.assistant-message-image {
  width: 96px;
  height: 96px;
  padding: 0;
  overflow: hidden;
  border: 1px solid #d8e3f2;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.assistant-message-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.assistant-vision-evidence {
  margin-top: 10px;
  padding: 10px 12px;
  border-left: 3px solid #4c8be8;
  border-radius: 4px;
  background: #f2f7ff;
}

.assistant-vision-evidence span {
  color: #356eaf;
  font-size: 12px;
  font-weight: 650;
}

.assistant-vision-evidence p {
  margin: 4px 0 0;
  color: #425675;
  font-size: 13px;
  line-height: 1.6;
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

.assistant-products {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.assistant-products.is-single {
  grid-template-columns: minmax(0, 780px);
}

.assistant-products.is-pair {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.assistant-product {
  min-width: 0;
  padding: 14px;
  border: 1px solid #e0e7ef;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(31, 52, 82, 0.05);
}

.assistant-products.is-single .assistant-product {
  display: grid;
  grid-template-columns: minmax(240px, 42%) minmax(0, 1fr);
  align-items: stretch;
}

.assistant-products.is-single .assistant-product__image-button {
  min-height: 270px;
  aspect-ratio: auto;
}

.assistant-products.is-single .assistant-product__content {
  padding: 4px 2px 4px 16px;
}

.assistant-product__image-button {
  display: block;
  width: 100%;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 6px;
  aspect-ratio: 4 / 3;
  background: #eef1f4;
  cursor: pointer;
}

.assistant-product__image-button:focus-visible {
  outline: 2px solid #2f6fe4;
  outline-offset: 2px;
}

.assistant-product__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 180ms ease;
}

.assistant-product__image-button:hover .assistant-product__image {
  transform: scale(1.025);
}

.assistant-product__content {
  padding-top: 12px;
}

.assistant-product__topline,
.assistant-detail__commerce {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.assistant-product__sku {
  overflow: hidden;
  color: #6f7d91;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant-product__stock {
  flex: 0 0 auto;
  color: #16865a;
  font-size: 11px;
  font-weight: 650;
}

.assistant-product__name {
  margin: 7px 0 0;
  color: #17294f;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
}

.assistant-product__price {
  margin: 6px 0 0;
  color: #b45309;
  font-size: 21px;
  font-weight: 750;
}

.assistant-product__highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 9px;
}

.assistant-product__highlights span {
  padding: 3px 6px;
  border-radius: 4px;
  background: #edf3f8;
  color: #53647d;
  font-size: 11px;
  line-height: 1.3;
}

.assistant-product__reasons,
.assistant-detail__reasons {
  display: grid;
  gap: 5px;
  margin: 10px 0 0;
  padding-left: 17px;
  color: #40536f;
  font-size: 12px;
  line-height: 1.5;
}

.assistant-product__reasons li::marker,
.assistant-detail__reasons li::marker {
  color: #16865a;
}

.assistant-product__warning {
  margin: 8px 0 0;
  color: #9a5a16;
  font-size: 12px;
}

.assistant-product__actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.assistant-product__actions .el-button {
  min-width: 0;
  flex: 1;
  margin: 0;
}

.assistant-comparison {
  margin-top: 16px;
  overflow-x: auto;
  border-top: 1px solid #dce5ef;
  overscroll-behavior-x: contain;
}

.assistant-comparison__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 0;
  color: #6f7d91;
  font-size: 12px;
}

.assistant-comparison__header strong {
  color: #233654;
  font-size: 13px;
}

.assistant-comparison__table {
  min-width: 570px;
  border-top: 1px solid #e4eaf1;
}

.assistant-comparison__row {
  display: grid;
  grid-template-columns: 130px repeat(2, minmax(180px, 1fr));
  border-bottom: 1px solid #e4eaf1;
}

.assistant-comparison__row > * {
  min-width: 0;
  padding: 9px 10px;
  border-left: 1px solid #e4eaf1;
  color: #334861;
  font-size: 12px;
  font-weight: 500;
  word-break: break-word;
}

.assistant-comparison__row > *:first-child {
  border-left: 0;
  color: #77849a;
}

.assistant-comparison__row.is-head {
  background: #f2f6fa;
}

.assistant-comparison__row.is-head > * {
  color: #233654;
  font-weight: 700;
}

.assistant-comparison__recommendation {
  margin: 12px 0 0;
  padding: 11px 12px;
  border-left: 3px solid #16865a;
  background: #f0f8f4;
  color: #2f4d41;
  line-height: 1.65;
}

.assistant-compare-tray {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 20px;
  border-top: 1px solid #dbe5ef;
  background: #f4f7fa;
}

.assistant-compare-tray__selection {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.assistant-compare-tray__label {
  color: #68778e;
  font-size: 12px;
  font-weight: 650;
}

.assistant-compare-chip {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  padding: 5px 7px 5px 9px;
  border: 1px solid #ccd8e8;
  border-radius: 5px;
  background: #fff;
  color: #334861;
  font-size: 12px;
}

.assistant-compare-chip button {
  display: grid;
  width: 18px;
  height: 18px;
  padding: 0;
  place-items: center;
  border: 0;
  background: transparent;
  color: #7b8799;
  cursor: pointer;
}

:deep(.assistant-product-drawer .el-drawer__body) {
  padding: 0;
  background: #fbfcfe;
}

.assistant-detail__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #e1e7ef;
  background: #fff;
  color: #233654;
  font-size: 14px;
  font-weight: 700;
}

.assistant-detail__image {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: #eef1f4;
}

.assistant-detail__identity,
.assistant-detail__section {
  padding: 20px;
  border-bottom: 1px solid #e1e7ef;
}

.assistant-detail__identity > span {
  color: #78869b;
  font-size: 12px;
}

.assistant-detail__identity h2 {
  margin: 6px 0 12px;
  color: #17294f;
  font-size: 24px;
  font-weight: 720;
}

.assistant-detail__commerce strong {
  color: #b45309;
  font-size: 26px;
}

.assistant-detail__commerce span {
  color: #16865a;
  font-size: 13px;
  font-weight: 650;
}

.assistant-detail__identity p {
  margin: 12px 0 0;
  color: #53647d;
  line-height: 1.7;
}

.assistant-detail__section h3 {
  margin: 0 0 12px;
  color: #233654;
  font-size: 15px;
}

.assistant-detail__specs {
  margin: 0;
}

.assistant-detail__specs div {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 16px;
  padding: 9px 0;
  border-bottom: 1px solid #e9edf2;
}

.assistant-detail__specs div:last-child {
  border-bottom: 0;
}

.assistant-detail__specs dt {
  color: #7a8799;
}

.assistant-detail__specs dd {
  margin: 0;
  color: #2f405f;
  font-weight: 600;
  text-align: right;
  word-break: break-word;
}

.assistant-detail__reasons {
  margin-top: 0;
  font-size: 13px;
}

.assistant-detail__footer {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px 24px;
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
  flex: 0 0 auto;
  padding: 14px 20px;
  border-top: 1px solid #e8eef7;
  background: #fff;
}

.assistant-composer-images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.assistant-composer-image {
  position: relative;
  width: 72px;
  height: 72px;
}

.assistant-composer-image > button:first-child {
  width: 100%;
  height: 100%;
  padding: 0;
  overflow: hidden;
  border: 1px solid #d8e3f2;
  border-radius: 8px;
  background: #f7f9fc;
  cursor: pointer;
}

.assistant-composer-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.assistant-composer-image__remove {
  position: absolute;
  top: -7px;
  right: -7px;
  display: grid;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #52647d;
  color: #fff;
  cursor: pointer;
  place-items: center;
}

.assistant-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.assistant-composer__tools {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.assistant-composer__hint {
  color: #7a879d;
  font-size: 12px;
}

.assistant-hidden-input {
  display: none;
}

:deep(.el-button--primary) {
  background: #17325f;
  border-color: #17325f;
}

:deep(.el-textarea__inner) {
  border-radius: 8px;
}

@media (max-width: 1200px) and (min-width: 961px) {
  .assistant-products:not(.is-single) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .assistant-page {
    display: block;
    height: auto;
    min-height: calc(100dvh - 32px);
    overflow: visible;
  }

  .assistant-history {
    position: fixed;
    z-index: 2101;
    top: 0;
    bottom: 0;
    left: 0;
    width: min(360px, 88vw);
    height: 100dvh;
    border-width: 0 1px 0 0;
    border-radius: 0;
    visibility: hidden;
    transform: translateX(-100%);
    transition: transform 180ms ease, visibility 180ms ease;
  }

  .assistant-history.is-open {
    visibility: visible;
    transform: translateX(0);
    box-shadow: 18px 0 48px rgba(15, 31, 55, 0.18);
  }

  .assistant-history-backdrop {
    position: fixed;
    z-index: 2100;
    inset: 0;
    display: block;
    padding: 0;
    border: 0;
    background: rgba(13, 27, 49, 0.42);
  }

  .assistant-history__close,
  .assistant-panel__history {
    display: inline-flex;
  }

  .assistant-history__delete {
    opacity: 1;
  }

  .assistant-panel {
    min-height: min(780px, calc(100dvh - 32px));
  }

  .assistant-ticket,
  .assistant-composer__actions,
  .assistant-compare-tray {
    align-items: stretch;
    flex-direction: column;
  }

  .assistant-message__body {
    max-width: calc(100% - 46px);
  }

  .assistant-products {
    grid-template-columns: 1fr;
  }

  .assistant-product {
    display: block;
    width: 100%;
  }

  .assistant-products.is-single .assistant-product {
    display: block;
  }

  .assistant-products.is-single .assistant-product__image-button {
    min-height: 0;
    aspect-ratio: 4 / 3;
  }

  .assistant-products.is-single .assistant-product__content {
    padding: 12px 0 0;
  }

  .assistant-compare-tray {
    align-items: stretch;
  }

  .assistant-requirements,
  .assistant-messages,
  .assistant-composer {
    padding-right: 14px;
    padding-left: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .assistant-history,
  .assistant-product__image {
    transition: none;
  }
}
</style>
