package com.wly.workorder.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.model.RefundModels.RefundDraftCommand;
import com.wly.workorder.model.RefundModels.RefundRequestView;
import com.wly.workorder.model.RefundModels.RefundType;
import com.wly.workorder.service.RefundService;
import com.wly.workorder.service.impl.QueryAIService;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest(properties = {
  "spring.datasource.url=jdbc:h2:mem:refund_controller;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false",
  "spring.datasource.driver-class-name=org.h2.Driver",
  "spring.datasource.username=sa",
  "spring.datasource.password=",
  "spring.sql.init.mode=always",
  "workorder.ai-service.internal-token=test-refund-token"
})
@AutoConfigureMockMvc
@Transactional
class RefundControllerTest {
  @Autowired
  private MockMvc mockMvc;
  @Autowired
  private ObjectMapper objectMapper;
  @Autowired
  private RefundService refundService;
  @MockBean
  private QueryAIService queryAIService;

  @Test
  void analysisPersistsReviewUsingBackendAmount() throws Exception {
    org.mockito.Mockito.when(queryAIService.generateRefundPlan(org.mockito.ArgumentMatchers.any()))
      .thenReturn(objectMapper.readTree("""
        {
          "action":"REVIEW",
          "suggested_reply":"已生成退款审核方案",
          "order_no":"ORD-USER-PAID",
          "refund_type":"UNSHIPPED_REFUND",
          "reason":"不再需要",
          "calculated_amount":"1.00",
          "policy_sources":[{"code":"UNSHIPPED_STANDARD","title":"未发货退款","content":"可退款"}],
          "agent_plan":{"action":"REVIEW"}
        }
        """));
    String token = login("admin", "admin123");

    mockMvc.perform(post("/api/work-order/fb-1/refund/analyze")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.action").value("REVIEW"))
      .andExpect(jsonPath("$.data.calculatedAmount").value(399.00))
      .andExpect(jsonPath("$.data.reviewStatus").value("PENDING_REVIEW"));
  }

  @Test
  void clarificationDoesNotCreateRefundDraft() throws Exception {
    org.mockito.Mockito.when(queryAIService.generateRefundPlan(org.mockito.ArgumentMatchers.any()))
      .thenReturn(objectMapper.readTree("""
        {"action":"CLARIFY","suggested_reply":"请确认订单号"}
        """));
    String token = login("admin", "admin123");

    mockMvc.perform(post("/api/work-order/fb-2/refund/analyze")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.action").value("CLARIFY"))
      .andExpect(jsonPath("$.data.suggested_reply").value("请确认订单号"));

    org.assertj.core.api.Assertions.assertThat(refundService.getByTicketId("fb-2")).isNull();
  }

  @Test
  void adminCanReadAndApproveRefundDraft() throws Exception {
    RefundRequestView draft = createDraft("ticket-controller");
    String token = login("admin", "admin123");

    mockMvc.perform(get("/api/work-order/" + draft.getTicketId() + "/refund")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.reviewStatus").value("PENDING_REVIEW"));

    mockMvc.perform(post("/api/work-order/" + draft.getTicketId() + "/refund/review")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"action\":\"APPROVE\",\"comment\":\"同意\",\"version\":" + draft.getVersion() + "}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.reviewStatus").value("APPROVED"))
      .andExpect(jsonPath("$.data.executionStatus").value("REFUNDED"));
  }

  @Test
  void normalUserCannotReviewRefund() throws Exception {
    RefundRequestView draft = createDraft("ticket-user-denied");
    String token = login("user", "user123");

    mockMvc.perform(post("/api/work-order/" + draft.getTicketId() + "/refund/review")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"action\":\"APPROVE\",\"version\":" + draft.getVersion() + "}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(403));
  }

  @Test
  void internalEvaluationRequiresServiceTokenAndReturnsBackendAmount() throws Exception {
    String body = "{\"owner_username\":\"1004\",\"order_no\":\"ORD-1004-PAID\",\"refund_type\":\"UNSHIPPED_REFUND\"}";

    mockMvc.perform(post("/api/internal/refund/evaluate")
        .header("X-Internal-Agent-Token", "test-refund-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content(body))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.eligible").value(true))
      .andExpect(jsonPath("$.data.refundable_amount").value(399.00));

    mockMvc.perform(post("/api/internal/refund/evaluate")
        .header("X-Internal-Agent-Token", "wrong")
        .contentType(MediaType.APPLICATION_JSON)
        .content(body))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(403));
  }

  private RefundRequestView createDraft(String ticketId) {
    return refundService.saveAgentDraft(
      ticketId,
      "1004",
      RefundDraftCommand.builder()
        .orderNo("ORD-1004-PAID")
        .refundType(RefundType.UNSHIPPED_REFUND)
        .reason("不再需要")
        .agentPlanJson("{\"action\":\"REVIEW\"}")
        .policySources(List.of())
        .build()
    );
  }

  private String login(String username, String password) throws Exception {
    MvcResult result = mockMvc.perform(post("/api/auth/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andReturn();
    JsonNode root = objectMapper.readTree(result.getResponse().getContentAsString());
    return root.path("data").path("token").asText();
  }
}
