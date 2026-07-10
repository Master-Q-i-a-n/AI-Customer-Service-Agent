import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const assistantSource = readFileSync(new URL('../src/views/AssistantView.vue', import.meta.url), 'utf8')
const assistantApiSource = readFileSync(new URL('../src/api/assistant.js', import.meta.url), 'utf8')

assert.match(assistantSource, /messageProducts\(message\)/)
assert.match(assistantSource, /查看详情/)
assert.match(assistantSource, /加入对比/)
assert.match(assistantSource, /currentCompareSelection\.length !== 2/)
assert.match(assistantSource, /messageComparison\(message\)/)
assert.match(assistantSource, /assistant-product-drawer/)
assert.match(assistantSource, /viewportWidth\.value <= 960 \? '100%' : '480px'/)
assert.match(assistantSource, /const requirementChips = computed/)
assert.match(assistantSource, /目标预算/)
assert.match(assistantSource, /推荐范围/)
assert.match(assistantSource, /v-model="historyQuery"/)
assert.match(assistantSource, /filteredSessionList/)
assert.match(assistantSource, /class="assistant-history__list"/)
assert.match(assistantSource, /class="assistant-history-backdrop"/)
assert.match(assistantSource, /'is-open': historyOpen/)
assert.match(assistantSource, /height: calc\(100dvh - 152px\)/)
assert.match(assistantSource, /\.assistant-products\.is-single \.assistant-product\s*\{[^}]*grid-template-columns:/s)
assert.match(assistantSource, /\.assistant-history__list\s*\{[^}]*overflow-y: auto;/s)
assert.match(assistantSource, /\.assistant-messages\s*\{[^}]*min-height: 0;[^}]*overflow-y: auto;/s)
assert.match(assistantSource, /@media \(max-width: 960px\)/)
assert.match(assistantSource, /startAssistantConversation\(content\)/)
assert.match(assistantSource, /deleteSession\(item\)/)
assert.match(assistantSource, /assistant-history__delete/)
assert.doesNotMatch(assistantSource, /createAssistantSession/)
assert.match(assistantApiSource, /url: '\/assistant\/sessions\/messages'/)
assert.match(assistantApiSource, /url: `\/assistant\/sessions\/\$\{id\}`[\s\S]*method: 'delete'/)

for (const file of [
  'jingxun-s1-lite.png',
  'jingxun-p2-pet.png',
  'jingxun-m3-station.png',
  'jingxun-x4-max.png'
]) {
  assert.equal(existsSync(new URL(`../public/products/${file}`, import.meta.url)), true, `${file} should exist`)
}

console.log('assistant presale UI wiring tests passed')
