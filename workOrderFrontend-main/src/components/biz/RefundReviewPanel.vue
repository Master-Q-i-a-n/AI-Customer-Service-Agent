<template>
  <section v-if="visible" class="refund-review" v-loading="loading">
    <header class="refund-review__header">
      <div>
        <div class="refund-review__eyebrow">退款审核</div>
        <h4>订单与退款方案</h4>
      </div>
      <div class="refund-review__actions">
        <el-tooltip content="重新分析退款诉求" placement="top">
          <el-button :icon="Refresh" :loading="analyzing" @click="runAnalysis">重新分析</el-button>
        </el-tooltip>
        <el-tooltip v-if="canApproveRefund(refund)" content="批准后由后端重新校验并执行" placement="top">
          <el-button type="success" :icon="Check" :loading="acting" @click="approve">批准</el-button>
        </el-tooltip>
        <el-tooltip v-if="canApproveRefund(refund)" content="拒绝当前退款方案" placement="top">
          <el-button type="danger" plain :icon="Close" :loading="acting" @click="reject">拒绝</el-button>
        </el-tooltip>
        <el-tooltip v-if="canConfirmReturn(refund)" content="仓库收到退货后确认" placement="top">
          <el-button type="primary" :icon="Box" :loading="acting" @click="confirmReceived">确认收货</el-button>
        </el-tooltip>
      </div>
    </header>

    <div v-if="refund" class="refund-review__body">
      <div class="refund-review__status" :data-status="refund.executionStatus">
        <span>{{ refundStatusLabel(refund.executionStatus) }}</span>
        <span>{{ refund.reviewStatus }}</span>
      </div>

      <dl class="refund-review__facts">
        <div><dt>订单号</dt><dd>{{ refund.orderNo }}</dd></div>
        <div><dt>退款类型</dt><dd>{{ refundTypeLabel }}</dd></div>
        <div><dt>资格结论</dt><dd>{{ refund.eligibilityReason || '--' }}</dd></div>
        <div class="refund-review__amount"><dt>可退金额</dt><dd>{{ formatRefundAmount(refund.calculatedAmount) }}</dd></div>
      </dl>

      <div v-if="refund.policySources?.length" class="refund-review__policies">
        <span class="refund-review__label">政策依据</span>
        <div v-for="policy in refund.policySources" :key="policy.code" class="refund-review__policy">
          <strong>{{ policy.title || policy.code }}</strong>
          <span>{{ policy.content }}</span>
        </div>
      </div>

      <div v-if="agentPlan" class="refund-review__plan">
        <span class="refund-review__label">Agent 方案</span>
        <p>{{ agentPlan.request_summary || refund.reason }}</p>
        <p v-for="risk in agentPlan.risks || []" :key="risk" class="refund-review__risk">{{ risk }}</p>
      </div>

      <div v-if="refund.reviewComment" class="refund-review__comment">
        审核意见：{{ refund.reviewComment }}
      </div>
    </div>

    <el-empty v-else description="尚未生成退款审核方案" :image-size="52" />
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Box, Check, Close, Refresh } from '@element-plus/icons-vue'
import {
  analyzeRefund,
  confirmReturnReceived,
  getRefundReview,
  reviewRefund
} from '../../api/workOrder'
import {
  canApproveRefund,
  canConfirmReturn,
  formatRefundAmount,
  refundStatusLabel
} from '../../utils/refund'

const props = defineProps({
  ticketId: { type: String, required: true },
  ticketCategory: { type: String, default: '' }
})
const emit = defineEmits(['reply-draft-ready', 'updated'])

const refund = ref(null)
const loading = ref(false)
const analyzing = ref(false)
const acting = ref(false)
const visible = computed(() => props.ticketCategory === '退款售后' || !!refund.value || analyzing.value)
const refundTypeLabel = computed(() => refund.value?.refundType === 'RETURN_REFUND' ? '退货退款' : '未发货退款')
const agentPlan = computed(() => {
  try {
    return refund.value?.agentPlanJson ? JSON.parse(refund.value.agentPlanJson) : null
  } catch {
    return null
  }
})

async function loadRefund() {
  if (!props.ticketId) return
  loading.value = true
  try {
    const response = await getRefundReview(props.ticketId)
    refund.value = response?.data || null
  } catch {
    refund.value = null
  } finally {
    loading.value = false
  }
}

async function runAnalysis() {
  analyzing.value = true
  try {
    const response = await analyzeRefund(props.ticketId)
    const result = response?.data || {}
    if (result.suggested_reply) emit('reply-draft-ready', result.suggested_reply)
    if (result.action === 'REVIEW') {
      await loadRefund()
      ElMessage.success('退款审核方案已生成')
    } else if (result.action === 'CLARIFY') {
      ElMessage.info('需要向用户补充确认')
    } else {
      ElMessage.warning('该退款诉求需要人工核实')
    }
    emit('updated')
  } catch (error) {
    ElMessage.error(error.message || '退款分析失败')
  } finally {
    analyzing.value = false
  }
}

async function approve() {
  try {
    await ElMessageBox.confirm(
      `确认批准订单 ${refund.value.orderNo} 的退款，金额 ${formatRefundAmount(refund.value.calculatedAmount)}？`,
      '批准退款',
      { confirmButtonText: '批准并执行', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  await submitReview('APPROVE', '管理员批准退款')
}

async function reject() {
  let comment = ''
  try {
    const result = await ElMessageBox.prompt('请填写拒绝原因', '拒绝退款', {
      confirmButtonText: '确认拒绝',
      cancelButtonText: '取消',
      inputValidator: value => !!String(value || '').trim() || '请输入拒绝原因'
    })
    comment = result.value
  } catch {
    return
  }
  await submitReview('REJECT', comment)
}

async function submitReview(action, comment) {
  acting.value = true
  try {
    const response = await reviewRefund(props.ticketId, {
      action,
      comment,
      version: refund.value.version
    })
    refund.value = response?.data || refund.value
    if (refund.value?.executionStatus === 'RETURN_PENDING') {
      emit('reply-draft-ready', '您好，您的退货申请已审核通过，请按客服提供的方式寄回商品。仓库确认收货后将执行退款。')
    } else if (refund.value?.executionStatus === 'REFUNDED') {
      emit('reply-draft-ready', `您好，订单 ${refund.value.orderNo} 已完成退款，退款金额为 ${formatRefundAmount(refund.value.calculatedAmount)}。`)
    }
    ElMessage.success(action === 'APPROVE' ? '退款审核已批准' : '退款申请已拒绝')
    emit('updated')
  } catch (error) {
    ElMessage.error(error.message || '退款审核失败')
  } finally {
    acting.value = false
  }
}

async function confirmReceived() {
  try {
    await ElMessageBox.confirm('确认仓库已经收到退货商品？确认后将执行退款。', '确认退货收货', {
      confirmButtonText: '已收到，执行退款',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  acting.value = true
  try {
    const response = await confirmReturnReceived(props.ticketId, { version: refund.value.version })
    refund.value = response?.data || refund.value
    emit('reply-draft-ready', `您好，退货商品已确认收货，订单 ${refund.value.orderNo} 已退款 ${formatRefundAmount(refund.value.calculatedAmount)}。`)
    emit('updated')
    ElMessage.success('退货退款已完成')
  } catch (error) {
    ElMessage.error(error.message || '确认收货失败')
  } finally {
    acting.value = false
  }
}

watch(() => props.ticketId, loadRefund)
onMounted(loadRefund)
</script>

<style scoped>
.refund-review {
  margin-bottom: 18px;
  padding: 16px 0;
  border-top: 1px solid #dfe6ef;
  border-bottom: 1px solid #dfe6ef;
  color: #24364b;
}

.refund-review__header,
.refund-review__actions,
.refund-review__status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.refund-review__header h4 {
  margin: 3px 0 0;
  font-size: 16px;
}

.refund-review__eyebrow,
.refund-review__label {
  color: #77859a;
  font-size: 12px;
}

.refund-review__body {
  margin-top: 14px;
}

.refund-review__status {
  justify-content: flex-start;
  padding: 8px 10px;
  border-left: 3px solid #409eff;
  background: #f3f7fc;
  font-size: 13px;
}

.refund-review__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 14px 0;
  background: #e4eaf1;
}

.refund-review__facts > div {
  min-width: 0;
  padding: 10px 12px;
  background: #fff;
}

.refund-review__facts dt {
  color: #7b8798;
  font-size: 12px;
}

.refund-review__facts dd {
  margin: 5px 0 0;
  overflow-wrap: anywhere;
}

.refund-review__amount dd {
  color: #c45656;
  font-size: 18px;
  font-weight: 700;
}

.refund-review__policies,
.refund-review__plan {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}

.refund-review__policy {
  display: grid;
  grid-template-columns: minmax(120px, 0.4fr) minmax(0, 1fr);
  gap: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.refund-review__plan p,
.refund-review__comment {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.refund-review__risk {
  color: #a36a00;
}

.refund-review__comment {
  margin-top: 12px;
  color: #65758a;
}

@media (max-width: 720px) {
  .refund-review__header,
  .refund-review__actions {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .refund-review__facts {
    grid-template-columns: 1fr;
  }

  .refund-review__policy {
    grid-template-columns: 1fr;
    gap: 3px;
  }
}
</style>
