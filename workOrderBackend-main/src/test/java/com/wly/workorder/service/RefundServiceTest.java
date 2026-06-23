package com.wly.workorder.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.wly.workorder.model.RefundModels.ExecutionStatus;
import com.wly.workorder.model.RefundModels.RefundDraftCommand;
import com.wly.workorder.model.RefundModels.RefundEvaluation;
import com.wly.workorder.model.RefundModels.RefundRequestView;
import com.wly.workorder.model.RefundModels.RefundType;
import com.wly.workorder.model.RefundModels.ReviewRefundRequest;
import com.wly.workorder.model.RefundModels.ReviewStatus;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest(
  properties = {
    "spring.datasource.url=jdbc:h2:mem:refund_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password=",
    "spring.sql.init.mode=always"
  }
)
@Transactional
class RefundServiceTest {
  @Autowired
  private RefundService refundService;

  @Autowired
  private JdbcTemplate jdbcTemplate;

  @Test
  void shippedOrderCannotUseUnshippedRefund() {
    RefundEvaluation result = refundService.evaluate(
      "1004", "ORD-1004-SHIPPED", RefundType.UNSHIPPED_REFUND
    );

    assertThat(result.isEligible()).isFalse();
    assertThat(result.getCode()).isEqualTo("ORDER_ALREADY_SHIPPED");
  }

  @Test
  void deliveredOrderWithinSevenDaysCanReturn() {
    RefundEvaluation result = refundService.evaluate(
      "1004", "ORD-1004-DELIVERED", RefundType.RETURN_REFUND
    );

    assertThat(result.isEligible()).isTrue();
    assertThat(result.getRefundableAmount()).isEqualByComparingTo("1299.00");
    assertThat(result.getPolicySources()).extracting("code").contains("RETURN_7_DAYS");
  }

  @Test
  void rejectsCrossUserOrder() {
    assertThatThrownBy(() -> refundService.evaluate(
      "1004", "ORD-OTHER-USER", RefundType.UNSHIPPED_REFUND
    )).isInstanceOf(IllegalStateException.class)
      .hasMessageContaining("order access denied");
  }

  @Test
  void approvalExecutesUnshippedRefundExactlyOnce() {
    RefundRequestView draft = createDraft("ticket-unshipped", "ORD-1004-PAID", RefundType.UNSHIPPED_REFUND);

    RefundRequestView first = refundService.review(
      draft.getTicketId(), "admin", new ReviewRefundRequest("APPROVE", "同意退款", draft.getVersion())
    );
    RefundRequestView second = refundService.review(
      draft.getTicketId(), "admin", new ReviewRefundRequest("APPROVE", "重复点击", first.getVersion())
    );

    assertThat(first.getExecutionStatus()).isEqualTo(ExecutionStatus.REFUNDED);
    assertThat(second.getExecutionStatus()).isEqualTo(ExecutionStatus.REFUNDED);
    assertThat(countAudit(draft.getId(), "REFUND_EXECUTED")).isEqualTo(1);
  }

  @Test
  void returnRefundWaitsForWarehouseReceipt() {
    RefundRequestView draft = createDraft("ticket-return", "ORD-1004-DELIVERED", RefundType.RETURN_REFUND);
    RefundRequestView approved = refundService.review(
      draft.getTicketId(), "admin", new ReviewRefundRequest("APPROVE", "同意退货", draft.getVersion())
    );

    assertThat(approved.getReviewStatus()).isEqualTo(ReviewStatus.APPROVED);
    assertThat(approved.getExecutionStatus()).isEqualTo(ExecutionStatus.RETURN_PENDING);

    RefundRequestView received = refundService.confirmReturnReceived(
      approved.getTicketId(), "admin", approved.getVersion()
    );
    assertThat(received.getExecutionStatus()).isEqualTo(ExecutionStatus.REFUNDED);
  }

  @Test
  void changedOrderFailsApprovalAndRequiresReanalysis() {
    RefundRequestView draft = createDraft("ticket-changed", "ORD-1004-PAID", RefundType.UNSHIPPED_REFUND);
    jdbcTemplate.update(
      "update ec_shipment set status='SHIPPED' where order_id=(select id from ec_order where order_no=?)",
      draft.getOrderNo()
    );

    assertThatThrownBy(() -> refundService.review(
      draft.getTicketId(), "admin", new ReviewRefundRequest("APPROVE", "", draft.getVersion())
    )).hasMessageContaining("refund eligibility changed");
  }

  private RefundRequestView createDraft(String ticketId, String orderNo, RefundType refundType) {
    return refundService.saveAgentDraft(
      ticketId,
      "1004",
      RefundDraftCommand.builder()
        .orderNo(orderNo)
        .refundType(refundType)
        .reason("用户不再需要商品")
        .agentPlanJson("{\"action\":\"REVIEW\"}")
        .policySources(List.of())
        .build()
    );
  }

  private int countAudit(String refundId, String eventType) {
    Integer count = jdbcTemplate.queryForObject(
      "select count(*) from ec_refund_audit where refund_request_id=? and event_type=?",
      Integer.class,
      refundId,
      eventType
    );
    return count == null ? 0 : count;
  }
}
