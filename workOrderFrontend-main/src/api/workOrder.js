import request from './http'

export function pageWorkOrders(params) {
  return request({
    url: '/work-order/page',
    method: 'get',
    params
  })
}

export function getWorkOrderSummary(params) {
  return request({
    url: '/work-order/summary',
    method: 'get',
    params
  })
}

export function updateWorkOrderStatus(id, data) {
  return request({
    url: `/work-order/${id}/status`,
    method: 'post',
    data
  })
}

export function getWorkOrderDetail(id) {
  return request({
    url: `/work-order/${id}`,
    method: 'get'
  })
}

export function replyWorkOrder(id, data) {
  return request({
    url: `/work-order/${id}/reply`,
    method: 'post',
    data
  })
}

export function getSuggestion(id){
  return request({
    url: `/work-order/${id}/suggest`,
    method: 'get'
  })
}

export function refreshWorkOrderAnalysis(id) {
  return request({
    url: `/work-order/${id}/analysis/refresh`,
    method: 'post'
  })
}

export const getRefundReview = id => request({
  url: `/work-order/${id}/refund`,
  method: 'get'
})

export const analyzeRefund = id => request({
  url: `/work-order/${id}/refund/analyze`,
  method: 'post'
})

export const reviewRefund = (id, data) => request({
  url: `/work-order/${id}/refund/review`,
  method: 'post',
  data
})

export const confirmReturnReceived = (id, data) => request({
  url: `/work-order/${id}/refund/return-received`,
  method: 'post',
  data
})
