package com.wly.workorder.service.impl;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.model.RefundModels.ExecutionStatus;
import com.wly.workorder.model.RefundModels.RefundDraftCommand;
import com.wly.workorder.model.RefundModels.RefundEvaluation;
import com.wly.workorder.model.RefundModels.RefundPolicySource;
import com.wly.workorder.model.RefundModels.RefundRequestView;
import com.wly.workorder.model.RefundModels.RefundType;
import com.wly.workorder.model.RefundModels.ReviewRefundRequest;
import com.wly.workorder.model.RefundModels.ReviewStatus;
import com.wly.workorder.service.RefundService;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcRefundService implements RefundService {
  private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.CHINA);

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;

  public JdbcRefundService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
  }

  @Override
  public List<Map<String, Object>> findCurrentUserOrders(String ownerUsername, String orderHint, String productHint) {
    String orderLike = "%" + defaultString(orderHint).trim() + "%";
    String productLike = "%" + defaultString(productHint).trim() + "%";
    return jdbcTemplate.query(
      """
      select distinct o.order_no, o.status, o.paid_amount, o.created_at, i.product_name
      from ec_order o
      join ec_order_item i on i.order_id=o.id
      where o.owner_username=? and o.order_no like ? and i.product_name like ?
      order by o.created_at desc
      limit 5
      """,
      (rs, rowNum) -> {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("order_no", rs.getString("order_no"));
        result.put("status", rs.getString("status"));
        result.put("paid_amount", rs.getBigDecimal("paid_amount"));
        result.put("created_at", rs.getString("created_at"));
        result.put("product_name", rs.getString("product_name"));
        return result;
      },
      ownerUsername,
      orderLike,
      productLike
    );
  }

  @Override
  public Map<String, Object> getOrderDetail(String ownerUsername, String orderNo) {
    OrderRow order = requireOwnedOrder(ownerUsername, orderNo);
    List<Map<String, Object>> items = jdbcTemplate.query(
      "select id, product_name, sku_name, quantity, paid_amount, returnable from ec_order_item where order_id=? order by id",
      (rs, rowNum) -> {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("item_id", rs.getString("id"));
        item.put("product_name", rs.getString("product_name"));
        item.put("sku_name", rs.getString("sku_name"));
        item.put("quantity", rs.getInt("quantity"));
        item.put("paid_amount", rs.getBigDecimal("paid_amount"));
        item.put("returnable", rs.getInt("returnable") == 1);
        return item;
      },
      order.id()
    );
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("order_no", order.orderNo());
    result.put("status", order.orderStatus());
    result.put("paid_amount", order.paidAmount());
    result.put("items", items);
    return result;
  }

  @Override
  public Map<String, Object> getLogistics(String ownerUsername, String orderNo) {
    OrderRow order = requireOwnedOrder(ownerUsername, orderNo);
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("order_no", order.orderNo());
    result.put("status", order.shipmentStatus());
    result.put("delivered_at", order.deliveredAt());
    return result;
  }

  @Override
  public List<RefundPolicySource> findPolicies(RefundType refundType) {
    return jdbcTemplate.query(
      "select code, title, content from ec_refund_policy where active=1 and refund_type=? order by code",
      (rs, rowNum) -> RefundPolicySource.builder()
        .code(rs.getString("code"))
        .title(rs.getString("title"))
        .content(rs.getString("content"))
        .build(),
      refundType.name()
    );
  }

  @Override
  public RefundEvaluation evaluate(String ownerUsername, String orderNo, RefundType refundType) {
    OrderRow order = requireOwnedOrder(ownerUsername, orderNo);
    List<RefundPolicySource> policies = findPolicies(refundType);
    BigDecimal refundable = order.paidAmount().subtract(order.refundedAmount()).max(BigDecimal.ZERO);

    if (refundable.compareTo(BigDecimal.ZERO) <= 0) {
      return evaluation(false, "ALREADY_REFUNDED", "订单已完成退款。", BigDecimal.ZERO, policies);
    }
    if (refundType == RefundType.UNSHIPPED_REFUND) {
      if (!"PAID".equals(order.orderStatus())) {
        return evaluation(false, "ORDER_STATUS_NOT_ELIGIBLE", "订单当前状态不支持未发货退款。", BigDecimal.ZERO, policies);
      }
      if (!"NOT_SHIPPED".equals(order.shipmentStatus())) {
        return evaluation(false, "ORDER_ALREADY_SHIPPED", "订单已经发货，不能按未发货退款处理。", BigDecimal.ZERO, policies);
      }
      return evaluation(true, "ELIGIBLE", "订单已支付且尚未发货。", refundable, policies);
    }

    if (!"DELIVERED".equals(order.orderStatus()) || !"DELIVERED".equals(order.shipmentStatus())) {
      return evaluation(false, "ORDER_NOT_DELIVERED", "订单尚未签收，不能申请退货退款。", BigDecimal.ZERO, policies);
    }
    if (!order.allReturnable()) {
      return evaluation(false, "ITEM_NOT_RETURNABLE", "订单中包含不可退商品。", BigDecimal.ZERO, policies);
    }
    if (daysSince(order.deliveredAt()) > 7) {
      return evaluation(false, "RETURN_WINDOW_EXPIRED", "订单已超过七天退货期限。", BigDecimal.ZERO, policies);
    }
    return evaluation(true, "ELIGIBLE", "订单在七天退货期限内且商品支持退货。", refundable, policies);
  }

  @Override
  @Transactional
  public RefundRequestView saveAgentDraft(String ticketId, String ownerUsername, RefundDraftCommand command) {
    OrderRow order = requireOwnedOrder(ownerUsername, command.getOrderNo());
    RefundEvaluation evaluation = evaluate(ownerUsername, command.getOrderNo(), command.getRefundType());
    if (!evaluation.isEligible()) {
      throw new IllegalStateException("refund is not eligible: " + evaluation.getCode());
    }
    String idempotencyKey = ticketId + ":" + order.id() + ":" + command.getRefundType().name();
    List<RefundRequestView> existing = findByIdempotencyKey(idempotencyKey);
    List<RefundPolicySource> policies = command.getPolicySources() == null || command.getPolicySources().isEmpty()
      ? evaluation.getPolicySources() : command.getPolicySources();
    String now = now();

    if (!existing.isEmpty()) {
      RefundRequestView current = existing.get(0);
      if (current.getReviewStatus() != ReviewStatus.PENDING_REVIEW && current.getReviewStatus() != ReviewStatus.DRAFT) {
        return current;
      }
      int updated = jdbcTemplate.update(
        """
        update ec_refund_request set reason=?, calculated_amount=?, eligibility_code=?, eligibility_reason=?,
          agent_plan_json=?, policy_sources_json=?, review_status=?, version=version+1, updated_at=?
        where id=? and version=?
        """,
        command.getReason(), evaluation.getRefundableAmount(), evaluation.getCode(), evaluation.getReason(),
        command.getAgentPlanJson(), writeJson(policies), ReviewStatus.PENDING_REVIEW.name(), now,
        current.getId(), current.getVersion()
      );
      requireUpdated(updated);
      audit(current.getId(), "AGENT_PLAN_CREATED", "AGENT", "refund-agent",
        "AGENT_PLAN_CREATED eligibility=" + evaluation.getCode() + " policy_count=" + policies.size());
      return getByTicketId(ticketId);
    }

    String id = UUID.randomUUID().toString();
    String refundNo = "RF-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase(Locale.ROOT);
    jdbcTemplate.update(
      """
      insert into ec_refund_request (
        id, refund_no, ticket_id, order_id, owner_username, refund_type, reason,
        requested_item_ids_json, calculated_amount, eligibility_code, eligibility_reason,
        agent_plan_json, policy_sources_json, review_status, execution_status, reviewed_by,
        review_comment, idempotency_key, version, created_at, updated_at
      ) values (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, '', '', ?, 1, ?, ?)
      """,
      id, refundNo, ticketId, order.id(), ownerUsername, command.getRefundType().name(), command.getReason(),
      evaluation.getRefundableAmount(), evaluation.getCode(), evaluation.getReason(), command.getAgentPlanJson(),
      writeJson(policies), ReviewStatus.PENDING_REVIEW.name(), ExecutionStatus.NOT_STARTED.name(),
      idempotencyKey, now, now
    );
    audit(id, "AGENT_PLAN_CREATED", "AGENT", "refund-agent",
      "AGENT_PLAN_CREATED eligibility=" + evaluation.getCode() + " policy_count=" + policies.size());
    return getByTicketId(ticketId);
  }

  @Override
  public RefundRequestView getByTicketId(String ticketId) {
    List<RefundRequestView> rows = jdbcTemplate.query(
      refundViewSql() + " where r.ticket_id=? order by r.updated_at desc limit 1",
      this::mapRefund,
      ticketId
    );
    return rows.isEmpty() ? null : rows.get(0);
  }

  @Override
  @Transactional
  public RefundRequestView review(String ticketId, String adminUsername, ReviewRefundRequest request) {
    RefundRequestView current = requireRefund(ticketId);
    if (current.getExecutionStatus() == ExecutionStatus.REFUNDED) {
      return current;
    }
    if (current.getVersion() != request.getVersion()) {
      throw new IllegalStateException("refund version conflict");
    }
    if (current.getReviewStatus() != ReviewStatus.PENDING_REVIEW) {
      throw new IllegalStateException("refund is not pending review");
    }
    String action = defaultString(request.getAction()).trim().toUpperCase(Locale.ROOT);
    if ("REJECT".equals(action)) {
      updateReview(current, ReviewStatus.REJECTED, ExecutionStatus.NOT_STARTED, adminUsername, request.getComment());
      audit(current.getId(), "ADMIN_REJECTED", "ADMIN", adminUsername, "ADMIN_REJECTED version=" + current.getVersion());
      return getByTicketId(ticketId);
    }
    if (!"APPROVE".equals(action)) {
      throw new IllegalArgumentException("unsupported review action");
    }

    RefundEvaluation evaluation = evaluate(currentOwner(current.getId()), current.getOrderNo(), current.getRefundType());
    if (!evaluation.isEligible() || evaluation.getRefundableAmount().compareTo(current.getCalculatedAmount()) != 0) {
      throw new IllegalStateException("refund eligibility changed; reanalysis required");
    }

    if (current.getRefundType() == RefundType.UNSHIPPED_REFUND) {
      jdbcTemplate.update("update ec_order set status='CANCELLED', updated_at=? where order_no=?", now(), current.getOrderNo());
      refundPayment(current.getOrderNo(), current.getCalculatedAmount());
      updateReview(current, ReviewStatus.APPROVED, ExecutionStatus.REFUNDED, adminUsername, request.getComment());
      audit(current.getId(), "REFUND_EXECUTED", "SYSTEM", "refund-service", "REFUND_EXECUTED status=REFUNDED");
    } else {
      updateReview(current, ReviewStatus.APPROVED, ExecutionStatus.RETURN_PENDING, adminUsername, request.getComment());
    }
    audit(current.getId(), "ADMIN_APPROVED", "ADMIN", adminUsername, "ADMIN_APPROVED version=" + current.getVersion());
    return getByTicketId(ticketId);
  }

  @Override
  @Transactional
  public RefundRequestView confirmReturnReceived(String ticketId, String adminUsername, int version) {
    RefundRequestView current = requireRefund(ticketId);
    if (current.getExecutionStatus() == ExecutionStatus.REFUNDED) {
      return current;
    }
    if (current.getVersion() != version) {
      throw new IllegalStateException("refund version conflict");
    }
    if (current.getReviewStatus() != ReviewStatus.APPROVED
      || current.getExecutionStatus() != ExecutionStatus.RETURN_PENDING) {
      throw new IllegalStateException("refund is not waiting for returned goods");
    }
    RefundEvaluation evaluation = evaluate(currentOwner(current.getId()), current.getOrderNo(), current.getRefundType());
    if (!evaluation.isEligible() || evaluation.getRefundableAmount().compareTo(current.getCalculatedAmount()) != 0) {
      throw new IllegalStateException("refund eligibility changed; reanalysis required");
    }
    refundPayment(current.getOrderNo(), current.getCalculatedAmount());
    jdbcTemplate.update("update ec_order set status='RETURNED', updated_at=? where order_no=?", now(), current.getOrderNo());
    int updated = jdbcTemplate.update(
      "update ec_refund_request set execution_status=?, version=version+1, updated_at=? where id=? and version=?",
      ExecutionStatus.REFUNDED.name(), now(), current.getId(), current.getVersion()
    );
    requireUpdated(updated);
    audit(current.getId(), "RETURN_RECEIVED", "ADMIN", adminUsername, "RETURN_RECEIVED status=REFUNDED");
    audit(current.getId(), "REFUND_EXECUTED", "SYSTEM", "refund-service", "REFUND_EXECUTED status=REFUNDED");
    return getByTicketId(ticketId);
  }

  private OrderRow requireOwnedOrder(String ownerUsername, String orderNo) {
    List<OrderRow> rows = jdbcTemplate.query(
      """
      select o.id, o.order_no, o.status order_status, p.paid_amount, p.refunded_amount,
        s.status shipment_status, s.delivered_at,
        case when min(i.returnable)=1 then 1 else 0 end all_returnable
      from ec_order o
      join ec_payment p on p.order_id=o.id
      join ec_shipment s on s.order_id=o.id
      join ec_order_item i on i.order_id=o.id
      where o.owner_username=? and o.order_no=?
      group by o.id, o.order_no, o.status, p.paid_amount, p.refunded_amount, s.status, s.delivered_at
      """,
      (rs, rowNum) -> new OrderRow(
        rs.getString("id"), rs.getString("order_no"), rs.getString("order_status"),
        rs.getBigDecimal("paid_amount"), rs.getBigDecimal("refunded_amount"),
        rs.getString("shipment_status"), rs.getString("delivered_at"), rs.getInt("all_returnable") == 1
      ),
      ownerUsername,
      orderNo
    );
    if (!rows.isEmpty()) {
      return rows.get(0);
    }
    Integer exists = jdbcTemplate.queryForObject("select count(*) from ec_order where order_no=?", Integer.class, orderNo);
    if (exists != null && exists > 0) {
      throw new IllegalStateException("order access denied");
    }
    throw new IllegalArgumentException("order not found");
  }

  private List<RefundRequestView> findByIdempotencyKey(String key) {
    return jdbcTemplate.query(refundViewSql() + " where r.idempotency_key=?", this::mapRefund, key);
  }

  private String currentOwner(String refundId) {
    return jdbcTemplate.queryForObject(
      "select owner_username from ec_refund_request where id=?",
      String.class,
      refundId
    );
  }

  private void updateReview(
    RefundRequestView current, ReviewStatus reviewStatus, ExecutionStatus executionStatus,
    String adminUsername, String comment
  ) {
    int updated = jdbcTemplate.update(
      """
      update ec_refund_request set review_status=?, execution_status=?, reviewed_by=?, review_comment=?,
        version=version+1, updated_at=? where id=? and version=?
      """,
      reviewStatus.name(), executionStatus.name(), adminUsername, defaultString(comment), now(),
      current.getId(), current.getVersion()
    );
    requireUpdated(updated);
  }

  private void refundPayment(String orderNo, BigDecimal amount) {
    int updated = jdbcTemplate.update(
      """
      update ec_payment set refunded_amount=refunded_amount+?, status='REFUNDED'
      where order_id=(select id from ec_order where order_no=?) and refunded_amount=0
      """,
      amount,
      orderNo
    );
    if (updated != 1) {
      throw new IllegalStateException("payment refund state changed");
    }
  }

  private void audit(String refundId, String eventType, String operatorType, String operatorId, String summary) {
    jdbcTemplate.update(
      "insert into ec_refund_audit (id, refund_request_id, event_type, operator_type, operator_id, summary, created_at) values (?, ?, ?, ?, ?, ?, ?)",
      UUID.randomUUID().toString(), refundId, eventType, operatorType, operatorId, summary, now()
    );
  }

  private RefundRequestView requireRefund(String ticketId) {
    RefundRequestView current = getByTicketId(ticketId);
    if (current == null) {
      throw new IllegalArgumentException("refund request not found");
    }
    return current;
  }

  private RefundRequestView mapRefund(java.sql.ResultSet rs, int rowNum) throws java.sql.SQLException {
    return RefundRequestView.builder()
      .id(rs.getString("id"))
      .refundNo(rs.getString("refund_no"))
      .ticketId(rs.getString("ticket_id"))
      .orderNo(rs.getString("order_no"))
      .refundType(RefundType.valueOf(rs.getString("refund_type")))
      .reason(rs.getString("reason"))
      .calculatedAmount(rs.getBigDecimal("calculated_amount"))
      .eligibilityCode(rs.getString("eligibility_code"))
      .eligibilityReason(rs.getString("eligibility_reason"))
      .agentPlanJson(rs.getString("agent_plan_json"))
      .policySources(readPolicies(rs.getString("policy_sources_json")))
      .reviewStatus(ReviewStatus.valueOf(rs.getString("review_status")))
      .executionStatus(ExecutionStatus.valueOf(rs.getString("execution_status")))
      .reviewComment(rs.getString("review_comment"))
      .version(rs.getInt("version"))
      .build();
  }

  private String refundViewSql() {
    return """
      select r.id, r.refund_no, r.ticket_id, o.order_no, r.refund_type, r.reason,
        r.calculated_amount, r.eligibility_code, r.eligibility_reason, r.agent_plan_json,
        r.policy_sources_json, r.review_status, r.execution_status, r.review_comment, r.version
      from ec_refund_request r join ec_order o on o.id=r.order_id
      """;
  }

  private RefundEvaluation evaluation(
    boolean eligible, String code, String reason, BigDecimal amount, List<RefundPolicySource> policies
  ) {
    return RefundEvaluation.builder()
      .eligible(eligible)
      .code(code)
      .reason(reason)
      .refundableAmount(amount)
      .policySources(policies)
      .build();
  }

  private long daysSince(String deliveredAt) {
    if (deliveredAt == null || deliveredAt.isBlank()) {
      return Long.MAX_VALUE;
    }
    try {
      return ChronoUnit.DAYS.between(LocalDateTime.parse(deliveredAt, FMT), LocalDateTime.now());
    } catch (DateTimeParseException ex) {
      return Long.MAX_VALUE;
    }
  }

  private String writeJson(Object value) {
    try {
      return objectMapper.writeValueAsString(value == null ? List.of() : value);
    } catch (Exception ex) {
      throw new IllegalStateException("failed to serialize refund data", ex);
    }
  }

  private List<RefundPolicySource> readPolicies(String json) {
    if (json == null || json.isBlank()) {
      return List.of();
    }
    try {
      return objectMapper.readValue(json, new TypeReference<List<RefundPolicySource>>() { });
    } catch (Exception ex) {
      return new ArrayList<>();
    }
  }

  private void requireUpdated(int updated) {
    if (updated != 1) {
      throw new IllegalStateException("refund version conflict");
    }
  }

  private static String defaultString(String value) {
    return value == null ? "" : value;
  }

  private static String now() {
    return LocalDateTime.now().format(FMT);
  }

  private record OrderRow(
    String id,
    String orderNo,
    String orderStatus,
    BigDecimal paidAmount,
    BigDecimal refundedAmount,
    String shipmentStatus,
    String deliveredAt,
    boolean allReturnable
  ) {
  }
}
