package com.wly.workorder.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public final class RefundModels {
  private RefundModels() {
  }

  public enum RefundType {
    UNSHIPPED_REFUND,
    RETURN_REFUND
  }

  public enum ReviewStatus {
    DRAFT,
    PENDING_REVIEW,
    APPROVED,
    REJECTED
  }

  public enum ExecutionStatus {
    NOT_STARTED,
    SUBMITTING,
    RETURN_PENDING,
    RETURN_RECEIVED,
    REFUNDED,
    FAILED
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class RefundPolicySource {
    private String code;
    private String title;
    private String content;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class RefundEvaluation {
    private boolean eligible;
    private String code;
    private String reason;
    private BigDecimal refundableAmount;
    private List<RefundPolicySource> policySources;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class RefundDraftCommand {
    @NotBlank
    private String orderNo;
    @NotNull
    private RefundType refundType;
    @NotBlank
    private String reason;
    @NotBlank
    private String agentPlanJson;
    private List<RefundPolicySource> policySources;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class RefundRequestView {
    private String id;
    private String refundNo;
    private String ticketId;
    private String orderNo;
    private RefundType refundType;
    private String reason;
    private BigDecimal calculatedAmount;
    private String eligibilityCode;
    private String eligibilityReason;
    private String agentPlanJson;
    private List<RefundPolicySource> policySources;
    private ReviewStatus reviewStatus;
    private ExecutionStatus executionStatus;
    private String reviewComment;
    private int version;
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class ReviewRefundRequest {
    @NotBlank
    private String action;
    private String comment;
    @NotNull
    private Integer version;
  }
}
