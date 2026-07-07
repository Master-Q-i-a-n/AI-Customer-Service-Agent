import request from './http'

export const createAssistantSession = () =>
  request({
    url: '/assistant/sessions',
    method: 'post'
  })

export const listAssistantSessions = () =>
  request({
    url: '/assistant/sessions',
    method: 'get'
  })

export const getAssistantSession = id =>
  request({
    url: `/assistant/sessions/${id}`,
    method: 'get'
  })

export const sendAssistantMessage = (id, content) =>
  request({
    url: `/assistant/sessions/${id}/messages`,
    method: 'post',
    data: { content }
  })

export const confirmAssistantTicket = id =>
  request({
    url: `/assistant/sessions/${id}/ticket`,
    method: 'post'
  })
