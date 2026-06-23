package com.wly.workorder.service;

import com.wly.workorder.auth.AuthContext;
import com.wly.workorder.auth.AuthException;
import com.wly.workorder.auth.AuthRole;
import com.wly.workorder.auth.AuthSession;
import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.OrderModels.OrderItemView;
import com.wly.workorder.model.OrderModels.RefundSummaryView;
import com.wly.workorder.model.OrderModels.ShipmentView;
import com.wly.workorder.model.OrderModels.UserOrderView;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
  private final JdbcTemplate jdbcTemplate;

  public OrderQueryService(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public List<UserOrderView> listCurrentUserOrders() {
    AuthSession session = AuthContext.require();
    if (session.getRole() != AuthRole.USER) {
      throw new AuthException(ApiResponse.withCode(403, "user access required", null));
    }

    Map<String, UserOrderView> orders = new LinkedHashMap<>();
    jdbcTemplate.query(
      """
      select o.id, o.order_no, o.status, o.total_amount, o.paid_amount, o.paid_at, o.created_at,
             s.status shipment_status, s.tracking_no, s.shipped_at, s.delivered_at
      from ec_order o
      left join ec_shipment s on s.order_id=o.id
      where o.owner_username=?
      order by o.created_at desc, o.order_no desc
      """,
      rs -> {
        UserOrderView order = UserOrderView.builder()
          .orderNo(rs.getString("order_no"))
          .status(rs.getString("status"))
          .totalAmount(rs.getBigDecimal("total_amount"))
          .paidAmount(rs.getBigDecimal("paid_amount"))
          .paidAt(rs.getString("paid_at"))
          .createdAt(rs.getString("created_at"))
          .items(new ArrayList<>())
          .shipment(ShipmentView.builder()
            .status(rs.getString("shipment_status"))
            .trackingNo(rs.getString("tracking_no"))
            .shippedAt(rs.getString("shipped_at"))
            .deliveredAt(rs.getString("delivered_at"))
            .build())
          .build();
        orders.put(rs.getString("id"), order);
      },
      session.getUsername()
    );

    if (orders.isEmpty()) {
      return List.of();
    }

    jdbcTemplate.query(
      """
      select i.order_id, i.product_name, i.sku_name, i.quantity, i.paid_amount, i.returnable
      from ec_order_item i
      join ec_order o on o.id=i.order_id
      where o.owner_username=?
      order by i.order_id, i.id
      """,
      rs -> {
        UserOrderView order = orders.get(rs.getString("order_id"));
        if (order != null) {
          order.getItems().add(OrderItemView.builder()
            .productName(rs.getString("product_name"))
            .skuName(rs.getString("sku_name"))
            .quantity(rs.getInt("quantity"))
            .paidAmount(rs.getBigDecimal("paid_amount"))
            .returnable(rs.getInt("returnable") == 1)
            .build());
        }
      },
      session.getUsername()
    );

    // 退款记录按更新时间倒序，首次写入即为每个订单的最新状态。
    Map<String, RefundSummaryView> latestRefunds = new LinkedHashMap<>();
    jdbcTemplate.query(
      """
      select r.order_id, r.review_status, r.execution_status, r.ticket_id
      from ec_refund_request r
      join ec_order o on o.id=r.order_id
      where o.owner_username=?
      order by r.updated_at desc, r.id desc
      """,
      rs -> {
        latestRefunds.putIfAbsent(
          rs.getString("order_id"),
          RefundSummaryView.builder()
            .reviewStatus(rs.getString("review_status"))
            .executionStatus(rs.getString("execution_status"))
            .ticketId(rs.getString("ticket_id"))
            .build()
        );
      },
      session.getUsername()
    );
    latestRefunds.forEach((orderId, refund) -> {
      UserOrderView order = orders.get(orderId);
      if (order != null) {
        order.setRefund(refund);
      }
    });

    return new ArrayList<>(orders.values());
  }
}
