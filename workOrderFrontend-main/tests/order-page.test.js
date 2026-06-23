import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const routerSource = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const orderApiSource = readFileSync(new URL('../src/api/order.js', import.meta.url), 'utf8')
const orderPageSource = readFileSync(new URL('../src/views/OrderView.vue', import.meta.url), 'utf8')
const feedbackSource = readFileSync(new URL('../src/views/FeedbackView.vue', import.meta.url), 'utf8')

assert.match(routerSource, /path:\s*['"]\/orders['"]/)
assert.match(routerSource, /roles:\s*\[['"]user['"]\]/)
assert.match(appSource, /to="\/orders"/)
assert.match(orderApiSource, /\/orders\/mine/)
assert.match(orderPageSource, /申请退款/)
assert.match(orderPageSource, /buildRefundQuery/)
assert.match(orderPageSource, /formatOrderAmount\(order\.paidAmount\)/)
assert.match(feedbackSource, /buildRefundFeedbackDraft/)
assert.match(feedbackSource, /route\.query\.intent/)
assert.match(feedbackSource, /router\.replace/)

console.log('order page wiring tests passed')
