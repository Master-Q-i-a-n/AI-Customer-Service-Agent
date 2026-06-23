import assert from 'node:assert/strict'
import { canApproveRefund, formatRefundAmount, refundStatusLabel } from '../src/utils/refund.js'

assert.equal(formatRefundAmount('399.00'), '¥399.00')
assert.equal(refundStatusLabel('RETURN_PENDING'), '等待退货')
assert.equal(canApproveRefund({ reviewStatus: 'PENDING_REVIEW', executionStatus: 'NOT_STARTED' }), true)
assert.equal(canApproveRefund({ reviewStatus: 'APPROVED', executionStatus: 'REFUNDED' }), false)
console.log('refund tests passed')
