package com.wly.workorder.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.auth.AuthContext;
import com.wly.workorder.auth.AuthException;
import com.wly.workorder.auth.AuthRole;
import com.wly.workorder.auth.AuthSession;
import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.config.WorkOrderAIProperties;
import com.wly.workorder.model.RefundModels.RefundEvaluation;
import com.wly.workorder.model.RefundModels.RefundDraftCommand;
import com.wly.workorder.model.RefundModels.RefundPolicySource;
import com.wly.workorder.model.RefundModels.RefundRequestView;
import com.wly.workorder.model.RefundModels.RefundType;
import com.wly.workorder.model.RefundModels.ReviewRefundRequest;
import com.wly.workorder.service.RefundService;
import com.wly.workorder.service.TicketService;
import com.wly.workorder.service.impl.QueryAIService;
import jakarta.validation.Valid;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RefundController {
  private final RefundService refundService;
  private final WorkOrderAIProperties properties;
  private final TicketService ticketService;
  private final QueryAIService queryAIService;
  private final ObjectMapper objectMapper;

  public RefundController(
    RefundService refundService,
    WorkOrderAIProperties properties,
    TicketService ticketService,
    QueryAIService queryAIService,
    ObjectMapper objectMapper
  ) {
    this.refundService = refundService;
    this.properties = properties;
    this.ticketService = ticketService;
    this.queryAIService = queryAIService;
    this.objectMapper = objectMapper;
  }

  @GetMapping("/work-order/{ticketId}/refund")
  public ApiResponse<RefundRequestView> getRefund(@PathVariable String ticketId) {
    requireAdmin();
    return ApiResponse.success(refundService.getByTicketId(ticketId));
  }

  @PostMapping("/work-order/{ticketId}/refund/analyze")
  public ApiResponse<Map<String, Object>> analyzeRefund(@PathVariable String ticketId) {
    requireAdmin();
    var workOrder = ticketService.queryWorkOrderById(ticketId);
    if (workOrder == null) {
      throw new IllegalArgumentException("work order not found");
    }
    JsonNode plan = queryAIService.generateRefundPlan(workOrder);
    if (plan == null) {
      throw new IllegalStateException("refund analysis unavailable");
    }
    String action = plan.path("action").asText("ESCALATE");
    if (!"REVIEW".equals(action)) {
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("action", action);
      result.put("suggested_reply", plan.path("suggested_reply").asText(""));
      return ApiResponse.success(result);
    }

    RefundDraftCommand command = RefundDraftCommand.builder()
      .orderNo(requiredText(plan, "order_no"))
      .refundType(RefundType.valueOf(requiredText(plan, "refund_type")))
      .reason(requiredText(plan, "reason"))
      .agentPlanJson(writeJson(plan.path("agent_plan")))
      .policySources(readPolicies(plan.path("policy_sources")))
      .build();
    RefundRequestView draft = refundService.saveAgentDraft(ticketId, workOrder.getOwnerUsername(), command);
    Map<String, Object> result = objectMapper.convertValue(
      draft,
      new TypeReference<Map<String, Object>>() { }
    );
    result.put("action", "REVIEW");
    result.put("suggested_reply", plan.path("suggested_reply").asText(""));
    return ApiResponse.success(result);
  }

  @PostMapping("/work-order/{ticketId}/refund/review")
  public ApiResponse<RefundRequestView> reviewRefund(
    @PathVariable String ticketId,
    @RequestBody @Valid ReviewRefundRequest request
  ) {
    AuthSession admin = requireAdmin();
    return ApiResponse.success(refundService.review(ticketId, admin.getUsername(), request));
  }

  @PostMapping("/work-order/{ticketId}/refund/return-received")
  public ApiResponse<RefundRequestView> confirmReturnReceived(
    @PathVariable String ticketId,
    @RequestBody Map<String, Integer> request
  ) {
    AuthSession admin = requireAdmin();
    Integer version = request.get("version");
    if (version == null) {
      throw new IllegalArgumentException("version is required");
    }
    return ApiResponse.success(refundService.confirmReturnReceived(ticketId, admin.getUsername(), version));
  }

  @PostMapping("/internal/refund/evaluate")
  public ApiResponse<Map<String, Object>> evaluateRefund(
    @RequestHeader(value = "X-Internal-Agent-Token", required = false) String internalToken,
    @RequestBody Map<String, String> request
  ) {
    if (!properties.getAiService().getInternalToken().equals(internalToken)) {
      throw new AuthException(ApiResponse.withCode(403, "forbidden", null));
    }
    String ownerUsername = required(request, "owner_username");
    String orderNo = required(request, "order_no");
    RefundType refundType = RefundType.valueOf(required(request, "refund_type"));
    RefundEvaluation evaluation = refundService.evaluate(ownerUsername, orderNo, refundType);

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("eligible", evaluation.isEligible());
    result.put("code", evaluation.getCode());
    result.put("reason", evaluation.getReason());
    result.put("refundable_amount", evaluation.getRefundableAmount());
    result.put("policy_sources", evaluation.getPolicySources().stream()
      .map(policy -> Map.of("code", policy.getCode(), "title", policy.getTitle()))
      .toList());
    return ApiResponse.success(result);
  }

  private AuthSession requireAdmin() {
    AuthSession session = AuthContext.require();
    if (session.getRole() != AuthRole.ADMIN) {
      throw new AuthException(ApiResponse.withCode(403, "admin access required", null));
    }
    return session;
  }

  private String required(Map<String, String> request, String key) {
    String value = request.get(key);
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(key + " is required");
    }
    return value.trim();
  }

  private String requiredText(JsonNode node, String key) {
    String value = node.path(key).asText("").trim();
    if (value.isEmpty()) {
      throw new IllegalArgumentException(key + " is required");
    }
    return value;
  }

  private List<RefundPolicySource> readPolicies(JsonNode nodes) {
    List<RefundPolicySource> policies = new ArrayList<>();
    for (JsonNode node : nodes) {
      policies.add(RefundPolicySource.builder()
        .code(node.path("code").asText(""))
        .title(node.path("title").asText(""))
        .content(node.path("content").asText(""))
        .build());
    }
    return policies;
  }

  private String writeJson(JsonNode node) {
    try {
      return objectMapper.writeValueAsString(node);
    } catch (Exception ex) {
      throw new IllegalArgumentException("invalid agent plan");
    }
  }
}
