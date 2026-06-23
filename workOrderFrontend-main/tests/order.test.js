import assert from 'node:assert/strict'
import {
  buildRefundFeedbackDraft,
  buildRefundQuery,
  filterOrders,
  formatOrderAmount,
  toOrderState
} from '../src/utils/order.js'

const pending = { status: 'PAID', shipment: { status: 'NOT_SHIPPED' } }
const shipping = { status: 'PAID', shipment: { status: 'SHIPPED' } }
const delivered = { status: 'DELIVERED', shipment: { status: 'DELIVERED' } }
const reviewing = { ...pending, refund: { reviewStatus: 'PENDING_REVIEW', executionStatus: 'PENDING' } }
const refunded = { ...delivered, refund: { reviewStatus: 'APPROVED', executionStatus: 'REFUNDED' } }

assert.equal(toOrderState(pending).key, 'pending')
assert.equal(toOrderState(shipping).key, 'shipping')
assert.equal(toOrderState(delivered).key, 'delivered')
assert.equal(toOrderState(reviewing).key, 'refunding')
assert.equal(toOrderState(refunded).key, 'refunded')
assert.equal(filterOrders([pending, shipping, delivered], 'shipping').length, 1)
assert.equal(filterOrders([pending], 'all').length, 1)
assert.equal(formatOrderAmount('399'), '¥399.00')
assert.deepEqual(buildRefundQuery(' ORD-1 '), { orderNo: 'ORD-1', intent: 'refund' })
assert.deepEqual(buildRefundFeedbackDraft('ORD-1'), {
  title: '订单 ORD-1 申请退款',
  description: '我想申请订单 ORD-1 的退款，请协助处理。'
})
assert.equal(buildRefundFeedbackDraft(''), null)

console.log('order tests passed')
