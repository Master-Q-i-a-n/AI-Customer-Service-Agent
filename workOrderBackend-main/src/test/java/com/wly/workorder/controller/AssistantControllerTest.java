package com.wly.workorder.controller;

import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.wly.workorder.service.impl.QueryAIService;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest(properties = {
  "spring.datasource.url=jdbc:h2:mem:assistant_controller;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false",
  "spring.datasource.driver-class-name=org.h2.Driver",
  "spring.datasource.username=sa",
  "spring.datasource.password=",
  "spring.sql.init.mode=always"
})
@AutoConfigureMockMvc
class AssistantControllerTest {
  @Autowired
  private MockMvc mockMvc;
  @Autowired
  private ObjectMapper objectMapper;
  @Autowired
  private JdbcTemplate jdbcTemplate;
  @MockBean
  private QueryAIService queryAIService;

  @Test
  void user_can_chat_and_confirm_ticket_from_ai_draft() throws Exception {
    String token = login("user", "user123");
    ObjectNode ai = assistantCreateTicketResponse();
    when(queryAIService.customerAssistantChat(anyString(), eq("user"), anyString(), anyList(), anyMap())).thenReturn(ai);

    String sessionId = createSession(token);

    MvcResult messageResult = mockMvc.perform(post("/api/assistant/sessions/" + sessionId + "/messages")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"content\":\"ORD-USER-PAID 我想退款\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.route").value("REFUND_AFTER_SALES"))
      .andExpect(jsonPath("$.data.pendingTicketDraft.title").value("退款售后：ORD-USER-PAID"))
      .andReturn();

    JsonNode messageRoot = objectMapper.readTree(messageResult.getResponse().getContentAsString());
    Assertions.assertEquals(2, messageRoot.path("data").path("messages").size());

    MvcResult ticketResult = mockMvc.perform(post("/api/assistant/sessions/" + sessionId + "/ticket")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.status").value("TICKET_CREATED"))
      .andReturn();

    JsonNode ticketRoot = objectMapper.readTree(ticketResult.getResponse().getContentAsString());
    String ticketId = ticketRoot.path("data").path("ticketId").asText();
    Assertions.assertFalse(ticketId.isBlank());
    Assertions.assertEquals(
      1,
      jdbcTemplate.queryForObject(
        "select count(*) from wo_feedback where id=? and category='退款售后' and service_group='AFTER_SALES'",
        Integer.class,
        ticketId
      )
    );
  }

  @Test
  void user_can_list_own_assistant_sessions() throws Exception {
    String token = registerAndLogin("assistant-list-owner");
    String otherToken = registerAndLogin("assistant-list-other");

    createSession(token);
    String firstId = createSession(token);
    sendText(token, firstId, "第一条咨询");
    String secondId = createSession(token);
    sendText(token, secondId, "第二条咨询");
    createSession(otherToken);

    mockMvc.perform(get("/api/assistant/sessions")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.length()").value(2))
      .andExpect(jsonPath("$.data[?(@.id == '" + firstId + "')]").exists());
  }

  @Test
  void first_message_creates_the_only_visible_session_and_delete_is_soft() throws Exception {
    String token = registerAndLogin("assistant-soft-delete");

    MvcResult started = mockMvc.perform(post("/api/assistant/sessions/messages")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"content\":\"想咨询扫地机器人\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.messages.length()").value(2))
      .andReturn();
    String sessionId = objectMapper.readTree(started.getResponse().getContentAsString()).path("data").path("id").asText();

    mockMvc.perform(get("/api/assistant/sessions").header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.length()").value(1));

    mockMvc.perform(delete("/api/assistant/sessions/" + sessionId).header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200));

    mockMvc.perform(get("/api/assistant/sessions").header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.length()").value(0));
    mockMvc.perform(get("/api/assistant/sessions/" + sessionId).header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(400));

    Assertions.assertEquals(1, jdbcTemplate.queryForObject(
      "select deleted from wo_assistant_session where id=?", Integer.class, sessionId
    ));
    Assertions.assertEquals(2, jdbcTemplate.queryForObject(
      "select count(*) from wo_assistant_message where session_id=?", Integer.class, sessionId
    ));
  }

  @Test
  void presale_state_is_persisted_with_the_current_session() throws Exception {
    String token = login("user", "user123");
    ObjectNode ai = objectMapper.createObjectNode();
    ai.put("action", "ANSWER");
    ai.put("route", "PRESALE");
    ai.put("reply", "已为您筛选商品。");
    ai.putArray("sources");
    ai.putArray("products");
    ObjectNode state = ai.putObject("presale_state");
    state.put("budget_target", 2500);
    state.put("budget_flexible", true);
    state.put("home_size_sqm", 90);
    state.putArray("candidate_sku_ids").add("sku-p2-gray");
    state.putArray("candidate_names").add("净巡 P2 Pet");
    when(queryAIService.customerAssistantChat(anyString(), eq("user"), anyString(), anyList(), anyMap())).thenReturn(ai);

    String sessionId = createSession(token);
    mockMvc.perform(post("/api/assistant/sessions/" + sessionId + "/messages")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"content\":\"90平，预算2500\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.presaleState.budget_target").value(2500))
      .andExpect(jsonPath("$.data.presaleState.candidate_sku_ids[0]").value("sku-p2-gray"));

    Assertions.assertEquals(
      1,
      jdbcTemplate.queryForObject(
        "select count(*) from wo_assistant_session where id=? and presale_state_json like '%sku-p2-gray%'",
        Integer.class,
        sessionId
      )
    );
  }

  @Test
  void admin_cannot_use_user_assistant_endpoint() throws Exception {
    String token = login("admin", "admin123");

    mockMvc.perform(post("/api/assistant/sessions").header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(403));
  }

  @Test
  void ai_failure_returns_ticket_draft_without_auto_creating_ticket() throws Exception {
    String token = login("user", "user123");
    when(queryAIService.customerAssistantChat(anyString(), eq("user"), anyString(), anyList(), anyMap())).thenReturn(null);

    String sessionId = createSession(token);

    mockMvc.perform(post("/api/assistant/sessions/" + sessionId + "/messages")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"content\":\"帮我处理一下这个问题\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.pendingTicketDraft.title").exists());

    Assertions.assertEquals(
      0,
      jdbcTemplate.queryForObject("select count(*) from wo_feedback where title like 'AI客服转人工:%'", Integer.class)
    );
  }

  @Test
  void user_cannot_read_another_users_session() throws Exception {
    String token = login("user", "user123");
    String otherToken = registerAndLogin("assistant-other");
    String sessionId = createSession(token);

    mockMvc.perform(get("/api/assistant/sessions/" + sessionId)
        .header("Authorization", otherToken))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(400));
  }

  private String createSession(String token) throws Exception {
    MvcResult result = mockMvc.perform(post("/api/assistant/sessions")
        .header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andReturn();

    JsonNode root = objectMapper.readTree(result.getResponse().getContentAsString());
    return root.path("data").path("id").asText();
  }

  private void sendText(String token, String sessionId, String content) throws Exception {
    mockMvc.perform(post("/api/assistant/sessions/" + sessionId + "/messages")
        .header("Authorization", token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"content\":\"" + content + "\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200));
  }

  private ObjectNode assistantCreateTicketResponse() {
    ObjectNode root = objectMapper.createObjectNode();
    root.put("action", "CREATE_TICKET");
    root.put("route", "REFUND_AFTER_SALES");
    root.put("reply", "可以为您生成售后工单。");
    root.putArray("sources");
    ObjectNode draft = root.putObject("ticket_draft");
    draft.put("title", "退款售后：ORD-USER-PAID");
    draft.put("description", "来源：用户侧 AI 客服对话\n用户诉求：ORD-USER-PAID 我想退款");
    draft.put("category", "退款售后");
    draft.put("service_group", "AFTER_SALES");
    return root;
  }

  private String registerAndLogin(String username) throws Exception {
    mockMvc.perform(post("/api/auth/register")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"username\":\"" + username + "\",\"password\":\"123456\",\"displayName\":\"Other User\",\"role\":\"USER\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200));
    return login(username, "123456");
  }

  private String login(String username, String password) throws Exception {
    MockHttpServletRequestBuilder request = post("/api/auth/login")
      .contentType(MediaType.APPLICATION_JSON)
      .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}");

    MvcResult result = mockMvc.perform(request)
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andReturn();

    JsonNode root = objectMapper.readTree(result.getResponse().getContentAsString());
    return root.path("data").path("token").asText();
  }
}
