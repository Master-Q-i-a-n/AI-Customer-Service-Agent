import request from './http'

export function askKnowledge(question) {
  return request({
    url: '/knowledge/qa',
    method: 'post',
    data: { question }
  })
}

export function listKnowledgeDocuments() {
  return request({
    url: '/knowledge/documents',
    method: 'get'
  })
}

export function uploadKnowledgeDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  return request({
    url: '/knowledge/documents/upload',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export function deleteKnowledgeDocument(id) {
  return request({
    url: `/knowledge/documents/${id}`,
    method: 'delete'
  })
}
