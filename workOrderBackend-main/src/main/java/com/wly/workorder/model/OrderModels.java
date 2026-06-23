package com.wly.workorder.model;

import java.math.BigDecimal;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public final class OrderModels {
  private OrderModels() {
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class UserOrderView {
    private String orderNo;
    private String status;
    private BigDecimal totalAmount;
    private BigDecimal paidAmount;
    private String paidAt;
    private String createdAt;
    private List<OrderItemView> items;
    private ShipmentView shipment;
    private RefundSummaryView refund;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class OrderItemView {
    private String productName;
    private String skuName;
    private int quantity;
    private BigDecimal paidAmount;
    private boolean returnable;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class ShipmentView {
    private String status;
    private String trackingNo;
    private String shippedAt;
    private String deliveredAt;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class RefundSummaryView {
    private String reviewStatus;
    private String executionStatus;
    private String ticketId;
  }
}

