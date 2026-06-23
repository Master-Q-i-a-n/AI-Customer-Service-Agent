<template>
  <section class="order-page" v-loading="loading">
    <div class="order-page__header">
      <div>
        <p class="order-page__eyebrow">我的订单</p>
        <h2 class="order-page__title">订单与物流</h2>
      </div>
      <el-button class="order-page__refresh" :loading="loading" @click="loadOrders">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div class="order-tabs" role="tablist" aria-label="订单状态筛选">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        class="order-tabs__item"
        :class="{ 'is-active': activeState === tab.value }"
        @click="activeState = tab.value"
      >
        <span>{{ tab.label }}</span>
        <strong>{{ countByState(tab.value) }}</strong>
      </button>
    </div>

    <div v-if="errorMessage && !loading" class="order-empty">
      <p>{{ errorMessage }}</p>
      <el-button type="primary" @click="loadOrders">重新加载</el-button>
    </div>

    <div v-else-if="!filteredOrders.length && !loading" class="order-empty">
      <p>当前没有匹配的订单记录。</p>
    </div>

    <div v-else class="order-list">
      <article v-for="order in filteredOrders" :key="order.orderNo" class="order-row">
        <div class="order-row__main">
          <div class="order-row__summary">
            <div class="order-row__top">
              <span class="order-row__no">{{ order.orderNo }}</span>
              <span class="order-state" :class="toOrderState(order).className">{{ toOrderState(order).label }}</span>
            </div>
            <h3 class="order-row__title">{{ primaryItem(order).productName }}</h3>
            <p class="order-row__meta">
              {{ primaryItem(order).skuName || '默认规格' }} · x{{ primaryItem(order).quantity || 1 }}
              <template v-if="order.items && order.items.length > 1"> · 等 {{ order.items.length }} 件商品</template>
            </p>
          </div>

          <div class="order-row__facts">
            <div>
              <span>实付金额</span>
              <strong>{{ formatOrderAmount(order.paidAmount) }}</strong>
            </div>
            <div>
              <span>物流单号</span>
              <strong>{{ order.shipment?.trackingNo || '暂无' }}</strong>
            </div>
            <div>
              <span>物流状态</span>
              <strong>{{ shipmentLabel(order) }}</strong>
            </div>
          </div>

          <div class="order-row__actions">
            <el-button
              v-if="toOrderState(order).canRefund"
              type="primary"
              class="order-row__refund"
              @click="applyRefund(order)"
            >
              申请退款
            </el-button>
            <el-button v-else plain disabled>{{ toOrderState(order).label }}</el-button>
            <button type="button" class="order-row__toggle" @click="toggleOrder(order.orderNo)">
              {{ expandedOrderNo === order.orderNo ? '收起详情' : '查看详情' }}
            </button>
          </div>
        </div>

        <el-collapse-transition>
          <div v-show="expandedOrderNo === order.orderNo" class="order-detail">
            <div class="order-detail__block">
              <span>下单时间</span>
              <strong>{{ formatOrderTime(order.createdAt) }}</strong>
            </div>
            <div class="order-detail__block">
              <span>付款时间</span>
              <strong>{{ formatOrderTime(order.paidAt) }}</strong>
            </div>
            <div class="order-detail__block">
              <span>发货时间</span>
              <strong>{{ formatOrderTime(order.shipment?.shippedAt) }}</strong>
            </div>
            <div class="order-detail__block">
              <span>签收时间</span>
              <strong>{{ formatOrderTime(order.shipment?.deliveredAt) }}</strong>
            </div>
          </div>
        </el-collapse-transition>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getMyOrders } from '../api/order'
import {
  buildRefundQuery,
  filterOrders,
  formatOrderAmount,
  formatOrderTime,
  toOrderState
} from '../utils/order'

const router = useRouter()
const loading = ref(false)
const orders = ref([])
const errorMessage = ref('')
const activeState = ref('all')
const expandedOrderNo = ref('')

const tabs = [
  { label: '全部', value: 'all' },
  { label: '待发货', value: 'pending' },
  { label: '运输中', value: 'shipping' },
  { label: '已签收', value: 'delivered' },
  { label: '退款中', value: 'refunding' },
  { label: '已退款', value: 'refunded' }
]

const filteredOrders = computed(() => filterOrders(orders.value, activeState.value))

function primaryItem(order) {
  const first = Array.isArray(order.items) ? order.items[0] : null
  return first || { productName: order.productName || '订单商品', skuName: '', quantity: 1 }
}

function shipmentLabel(order) {
  const status = String(order.shipment?.status || '').toUpperCase()
  if (status === 'DELIVERED') return '已签收'
  if (status === 'SHIPPED') return '运输中'
  return '待发货'
}

function countByState(state) {
  return filterOrders(orders.value, state).length
}

function toggleOrder(orderNo) {
  expandedOrderNo.value = expandedOrderNo.value === orderNo ? '' : orderNo
}

async function applyRefund(order) {
  const query = buildRefundQuery(order.orderNo)
  if (!query.orderNo) {
    ElMessage.warning('订单编号缺失，暂不能申请退款')
    return
  }
  await router.push({ path: '/feedback', query })
}

async function loadOrders() {
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await getMyOrders()
    const list = Array.isArray(res?.data) ? res.data : []
    orders.value = list
    if (!expandedOrderNo.value && list.length) {
      expandedOrderNo.value = list[0].orderNo || ''
    }
  } catch (error) {
    orders.value = []
    expandedOrderNo.value = ''
    errorMessage.value = error.message || '订单加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadOrders)
</script>

<style scoped>
.order-page {
  min-height: 640px;
  padding-left: 40px;
  color: #17233f;
}

.order-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 0 24px;
}

.order-page__eyebrow {
  margin: 0 0 4px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: #6a7d9f;
}

.order-page__title {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
  color: #17233f;
}

.order-page__refresh {
  min-width: 96px;
  border-radius: 10px;
}

.order-tabs {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.order-tabs__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid #dce5f2;
  border-radius: 8px;
  background: #fff;
  color: #52627f;
  cursor: pointer;
}

.order-tabs__item.is-active {
  border-color: #2f6fe4;
  color: #1f56bd;
  background: #f2f7ff;
}

.order-list {
  display: grid;
  gap: 12px;
}

.order-row {
  border: 1px solid #e4ebf5;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(28, 52, 92, 0.06);
}

.order-row__main {
  display: grid;
  grid-template-columns: minmax(220px, 1.2fr) minmax(300px, 1.4fr) 150px;
  gap: 18px;
  align-items: center;
  padding: 18px;
}

.order-row__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.order-row__no {
  font-size: 13px;
  color: #6f7d94;
}

.order-row__title {
  margin: 10px 0 6px;
  font-size: 17px;
  font-weight: 650;
  color: #15254a;
}

.order-row__meta {
  margin: 0;
  color: #6a7690;
  line-height: 1.6;
}

.order-row__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.order-row__facts div,
.order-detail__block {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.order-row__facts span,
.order-detail__block span {
  font-size: 12px;
  color: #7b879c;
}

.order-row__facts strong,
.order-detail__block strong {
  overflow: hidden;
  color: #263958;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-row__actions {
  display: grid;
  gap: 10px;
  justify-items: stretch;
}

.order-row__refund.el-button--primary {
  background: #17325f;
  border-color: #17325f;
}

.order-row__toggle {
  height: 32px;
  border: 0;
  background: transparent;
  color: #2f6fe4;
  cursor: pointer;
}

.order-state {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.order-state.is-pending {
  color: #926100;
  background: #fff5d9;
}

.order-state.is-shipping {
  color: #1f56bd;
  background: #edf4ff;
}

.order-state.is-delivered {
  color: #237a57;
  background: #e8f7ef;
}

.order-state.is-refunding {
  color: #9a4d00;
  background: #fff0df;
}

.order-state.is-refunded {
  color: #657086;
  background: #f0f3f8;
}

.order-detail {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  padding: 14px 18px 18px;
  border-top: 1px solid #edf1f7;
  background: #f8fbff;
}

.order-empty {
  display: grid;
  justify-items: center;
  gap: 14px;
  min-height: 360px;
  place-content: center;
  border: 1px dashed #d9e3f2;
  border-radius: 8px;
  background: #fbfdff;
  color: #748098;
}

.order-empty p {
  margin: 0;
}

@media (max-width: 1080px) {
  .order-page {
    padding-left: 0;
  }

  .order-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .order-row__main {
    grid-template-columns: 1fr;
  }

  .order-row__actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .order-page__header,
  .order-row__facts,
  .order-detail {
    grid-template-columns: 1fr;
  }

  .order-page__header {
    display: grid;
  }

  .order-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .order-row__actions {
    grid-template-columns: 1fr;
  }
}
</style>
