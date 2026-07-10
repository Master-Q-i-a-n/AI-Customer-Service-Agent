import request from './http'

export const createAssistantSession = () =>
  request({
    url: '/assistant/sessions',
    method: 'post'
  })

// The first user message and its conversation are persisted together.
export const startAssistantConversation = content =>
  request({
    url: '/assistant/sessions/messages',
    method: 'post',
    data: { content }
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

export const deleteAssistantSession = id =>
  request({
    url: `/assistant/sessions/${id}`,
    method: 'delete'
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
