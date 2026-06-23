export const REFUND_STATUS_LABELS = {
  NOT_STARTED: '待审核',
  SUBMITTING: '提交中',
  RETURN_PENDING: '等待退货',
  RETURN_RECEIVED: '已收货',
  REFUNDED: '已退款',
  FAILED: '执行失败'
}

export function formatRefundAmount(value) {
  const amount = Number(value)
  return Number.isFinite(amount) ? `¥${amount.toFixed(2)}` : '--'
}

export function refundStatusLabel(status) {
  return REFUND_STATUS_LABELS[status] || '未生成方案'
}

export function canApproveRefund(refund) {
  return refund?.reviewStatus === 'PENDING_REVIEW' && refund?.executionStatus === 'NOT_STARTED'
}

export function canConfirmReturn(refund) {
  return refund?.reviewStatus === 'APPROVED' && refund?.executionStatus === 'RETURN_PENDING'
}
