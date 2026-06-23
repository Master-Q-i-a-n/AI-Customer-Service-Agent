import request from './http'

export const getMyOrders = () =>
  request({
    url: '/orders/mine',
    method: 'get'
  })
