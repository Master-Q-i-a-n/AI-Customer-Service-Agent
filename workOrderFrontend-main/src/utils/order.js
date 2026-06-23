const REFUNDING_REVIEW_STATES = new Set(['PENDING_REVIEW', 'APPROVED'])

export function toOrderState(order = {}) {
  const executionStatus = String(order.refund?.executionStatus || '').toUpperCase()
  const reviewStatus = String(order.refund?.reviewStatus || '').toUpperCase()
  const shipmentStatus = String(order.shipment?.status || '').toUpperCase()

  if (executionStatus === 'REFUNDED') {
    return { key: 'refunded', label: '已退款', className: 'is-refunded', canRefund: false }
  }
  if (REFUNDING_REVIEW_STATES.has(reviewStatus) || (executionStatus && executionStatus !== 'FAILED')) {
    return { key: 'refunding', label: '退款处理中', className: 'is-refunding', canRefund: false }
  }
  if (shipmentStatus === 'DELIVERED' || String(order.status || '').toUpperCase() === 'DELIVERED') {
    return { key: 'delivered', label: '已签收', className: 'is-delivered', canRefund: true }
  }
  if (shipmentStatus === 'SHIPPED') {
    return { key: 'shipping', label: '运输中', className: 'is-shipping', canRefund: true }
  }
  return { key: 'pending', label: '待发货', className: 'is-pending', canRefund: true }
}

export function filterOrders(orders = [], state = 'all') {
  const list = Array.isArray(orders) ? orders : []
  return state === 'all' ? list : list.filter(order => toOrderState(order).key === state)
}

export function formatOrderAmount(value) {
  const amount = Number(value)
  return Number.isFinite(amount) ? `¥${amount.toFixed(2)}` : '¥0.00'
}

export function formatOrderTime(value) {
  if (!value) return '尚未更新'
  return String(value).replace('T', ' ')
}

export function buildRefundQuery(orderNo) {
  const normalized = String(orderNo || '').trim()
  return normalized ? { orderNo: normalized, intent: 'refund' } : {}
}

export function buildRefundFeedbackDraft(orderNo) {
  const normalized = String(orderNo || '').trim()
  if (!normalized) return null
  return {
    title: `订单 ${normalized} 申请退款`,
    description: `我想申请订单 ${normalized} 的退款，请协助处理。`
  }
}
