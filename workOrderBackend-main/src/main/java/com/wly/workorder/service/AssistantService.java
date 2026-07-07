package com.wly.workorder.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.wly.workorder.auth.AuthContext;
import com.wly.workorder.auth.AuthException;
import com.wly.workorder.auth.AuthRole;
import com.wly.workorder.auth.AuthSession;
import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.AssistantModels.AssistantMessageView;
import com.wly.workorder.model.AssistantModels.AssistantSessionView;
import com.wly.workorder.model.TicketModels.Feedback;
import com.wly.workorder.model.TicketModels.ServiceGroup;
import com.wly.workorder.model.TicketModels.TicketCategory;
import com.wly.workorder.service.impl.QueryAIService;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AssistantService {
  private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.CHINA);
  private static final Set<String> VALID_ACTIONS = Set.of("ANSWER", "CLARIFY", "CREATE_TICKET", "TRANSFER_HUMAN");
  private static final Set<String> VALID_ROUTES = Set.of(
    "GENERAL_CHAT", "PRESALE", "KNOWLEDGE_QA", "ORDER_QUERY", "USER_RECORD",
    "AFTER_SALES_FAULT", "REFUND_AFTER_SALES", "CLARIFY", "OUT_OF_SCOPE"
  );

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;
  private final QueryAIService queryAIService;
  private final TicketService ticketService;

  public AssistantService(
    JdbcTemplate jdbcTemplate,
    ObjectMapper objectMapper,
    QueryAIService queryAIService,
    TicketService ticketService
  ) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
    this.queryAIService = queryAIService;
    this.ticketService = ticketService;
  }

  @Transactional
  public AssistantSessionView createSession() {
    AuthSession session = requireUser();
    String id = "as-" + UUID.randomUUID().toString().substring(0, 12);
    String now = now();
    jdbcTemplate.update(
      """
      insert into wo_assistant_session
      (id, owner_username, status, route, summary, pending_ticket_draft_json, ticket_id, created_at, updated_at)
      values (?, ?, ?, ?, ?, ?, ?, ?, ?)
      """,
      id, session.getUsername(), "ACTIVE", "", "", "{}", "", now, now
    );
    return getSession(id);
  }

  public AssistantSessionView getSession(String sessionId) {
    AuthSession session = requireUser();
    return loadOwnedSession(session.getUsername(), sessionId);
  }

  public List<AssistantSessionView> listSessions() {
    AuthSession session = requireUser();
    return jdbcTemplate.query(
      """
      select id, status, route, summary, pending_ticket_draft_json, ticket_id, created_at, updated_at
      from wo_assistant_session
      where owner_username=?
      order by updated_at desc, id desc
      limit 20
      """,
      (rs, rowNum) -> AssistantSessionView.builder()
        .id(rs.getString("id"))
        .status(rs.getString("status"))
        .route(rs.getString("route"))
        .summary(rs.getString("summary"))
        .pendingTicketDraft(readMap(rs.getString("pending_ticket_draft_json")))
        .ticketId(rs.getString("ticket_id"))
        .createdAt(rs.getString("created_at"))
        .updatedAt(rs.getString("updated_at"))
        .messages(List.of())
        .build(),
      session.getUsername()
    );
  }

  @Transactional
  public AssistantSessionView sendMessage(String sessionId, String content) {
    AuthSession session = requireUser();
    AssistantSessionView before = loadOwnedSession(session.getUsername(), sessionId);
    String cleanContent = String.valueOf(content == null ? "" : content).trim();
    if (cleanContent.isEmpty()) {
      throw new IllegalArgumentException("content is required");
    }

    insertMessage(sessionId, "user", cleanContent, "", Map.of());

    List<Map<String, String>> history = before.getMessages().stream()
      .map(item -> Map.of(
        "role", item.getRole(),
        "content", item.getContent()
      ))
      .toList();
    JsonNode aiResponse = queryAIService.customerAssistantChat(
      sessionId,
      session.getUsername(),
      cleanContent,
      history
    );
    if (aiResponse == null || aiResponse.isMissingNode()) {
      aiResponse = fallbackAiResponse(cleanContent);
    }

    String action = normalize(aiResponse.path("action").asText("ANSWER"), VALID_ACTIONS, "ANSWER");
    String route = normalize(aiResponse.path("route").asText("KNOWLEDGE_QA"), VALID_ROUTES, "KNOWLEDGE_QA");
    String reply = aiResponse.path("reply").asText("").trim();
    if (reply.isEmpty()) {
      reply = "您好，AI 客服暂时无法生成有效回复。您可以补充问题细节，或确认是否转人工处理。";
    }
    Map<String, Object> metadata = objectMapper.convertValue(aiResponse, new TypeReference<Map<String, Object>>() { });
    Map<String, Object> ticketDraft = readMap(writeJson(metadata.get("ticket_draft")));
    String pendingDraftJson = ticketDraft.isEmpty() ? "{}" : writeJson(ticketDraft);

    insertMessage(sessionId, "assistant", reply, action, metadata);
    jdbcTemplate.update(
      "update wo_assistant_session set route=?, summary=?, pending_ticket_draft_json=?, updated_at=? where id=? and owner_username=?",
      route,
      summarize(cleanContent),
      pendingDraftJson,
      now(),
      sessionId,
      session.getUsername()
    );
    return loadOwnedSession(session.getUsername(), sessionId);
  }

  @Transactional
  public AssistantSessionView confirmTicket(String sessionId) {
    AuthSession session = requireUser();
    AssistantSessionView current = loadOwnedSession(session.getUsername(), sessionId);
    if (current.getTicketId() != null && !current.getTicketId().isBlank()) {
      return current;
    }
    Map<String, Object> draft = current.getPendingTicketDraft();
    if (draft == null || draft.isEmpty()) {
      throw new IllegalArgumentException("no pending ticket draft");
    }

    // 工单分类和服务组来自 AI 草稿，但创建动作仍由后端按当前登录用户执行。
    Feedback feedback = ticketService.createFeedbackFromAssistant(
      requiredDraftText(draft, "title"),
      requiredDraftText(draft, "description"),
      parseCategory(String.valueOf(draft.get("category"))),
      parseServiceGroup(String.valueOf(draft.get("service_group")))
    );
    jdbcTemplate.update(
      "update wo_assistant_session set status=?, ticket_id=?, pending_ticket_draft_json=?, updated_at=? where id=? and owner_username=?",
      "TICKET_CREATED",
      feedback.getId(),
      "{}",
      now(),
      sessionId,
      session.getUsername()
    );
    insertMessage(
      sessionId,
      "assistant",
      "已为您生成工单 " + feedback.getCode() + "，人工客服会继续跟进。",
      "ANSWER",
      Map.of("ticket_id", feedback.getId(), "ticket_code", feedback.getCode())
    );
    return loadOwnedSession(session.getUsername(), sessionId);
  }

  private AssistantSessionView loadOwnedSession(String username, String sessionId) {
    List<AssistantSessionView> sessions = jdbcTemplate.query(
      """
      select id, status, route, summary, pending_ticket_draft_json, ticket_id, created_at, updated_at
      from wo_assistant_session where id=? and owner_username=?
      """,
      (rs, rowNum) -> AssistantSessionView.builder()
        .id(rs.getString("id"))
        .status(rs.getString("status"))
        .route(rs.getString("route"))
        .summary(rs.getString("summary"))
        .pendingTicketDraft(readMap(rs.getString("pending_ticket_draft_json")))
        .ticketId(rs.getString("ticket_id"))
        .createdAt(rs.getString("created_at"))
        .updatedAt(rs.getString("updated_at"))
        .messages(new ArrayList<>())
        .build(),
      sessionId,
      username
    );
    if (sessions.isEmpty()) {
      throw new IllegalArgumentException("assistant session not found");
    }
    AssistantSessionView view = sessions.get(0);
    view.setMessages(loadMessages(sessionId));
    return view;
  }

  private List<AssistantMessageView> loadMessages(String sessionId) {
    return jdbcTemplate.query(
      """
      select id, role, content, action, metadata_json, created_at
      from wo_assistant_message where session_id=? order by created_at asc, id asc
      """,
      (rs, rowNum) -> AssistantMessageView.builder()
        .id(rs.getString("id"))
        .role(rs.getString("role"))
        .content(rs.getString("content"))
        .action(rs.getString("action"))
        .metadata(readMap(rs.getString("metadata_json")))
        .createdAt(rs.getString("created_at"))
        .build(),
      sessionId
    );
  }

  private void insertMessage(String sessionId, String role, String content, String action, Map<String, Object> metadata) {
    jdbcTemplate.update(
      """
      insert into wo_assistant_message (id, session_id, role, content, action, metadata_json, created_at)
      values (?, ?, ?, ?, ?, ?, ?)
      """,
      nextMessageId(),
      sessionId,
      role,
      content,
      action == null ? "" : action,
      writeJson(metadata == null ? Map.of() : metadata),
      now()
    );
  }

  private AuthSession requireUser() {
    AuthSession session = AuthContext.require();
    if (session.getRole() != AuthRole.USER) {
      throw new AuthException(ApiResponse.withCode(403, "user access required", null));
    }
    return session;
  }

  private String nextMessageId() {
    return "am-" + System.currentTimeMillis() + "-" + UUID.randomUUID().toString().substring(0, 6);
  }

  private ObjectNode fallbackAiResponse(String userMessage) {
    ObjectNode root = objectMapper.createObjectNode();
    root.put("action", "CREATE_TICKET");
    root.put("route", "CLARIFY");
    root.put("reply", "您好，AI 客服暂时不可用。我可以先帮您生成工单，由人工客服继续处理。");
    root.putArray("sources");
    ObjectNode draft = root.putObject("ticket_draft");
    draft.put("title", "AI客服转人工：" + truncate(userMessage, 32));
    draft.put("description", "来源：用户侧 AI 客服对话\n用户诉求：" + userMessage + "\n处理建议：AI 服务暂时不可用，请人工客服继续核实。");
    draft.put("category", TicketCategory.其他.name());
    draft.put("service_group", ServiceGroup.PRODUCT_CONSULTING.name());
    return root;
  }

  private Map<String, Object> readMap(String json) {
    if (json == null || json.isBlank() || "{}".equals(json)) {
      return new LinkedHashMap<>();
    }
    try {
      return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() { });
    } catch (Exception ex) {
      return new LinkedHashMap<>();
    }
  }

  private String writeJson(Object value) {
    try {
      return objectMapper.writeValueAsString(value == null ? Map.of() : value);
    } catch (Exception ex) {
      return "{}";
    }
  }

  private String requiredDraftText(Map<String, Object> draft, String key) {
    String value = String.valueOf(draft.getOrDefault(key, "")).trim();
    if (value.isEmpty() || "null".equals(value)) {
      throw new IllegalArgumentException("ticket draft " + key + " is required");
    }
    return value;
  }

  private TicketCategory parseCategory(String value) {
    try {
      return TicketCategory.valueOf(value);
    } catch (Exception ex) {
      return TicketCategory.其他;
    }
  }

  private ServiceGroup parseServiceGroup(String value) {
    try {
      return ServiceGroup.valueOf(value);
    } catch (Exception ex) {
      return ServiceGroup.PRODUCT_CONSULTING;
    }
  }

  private String normalize(String value, Set<String> allowed, String fallback) {
    String normalized = String.valueOf(value == null ? "" : value).trim();
    return allowed.contains(normalized) ? normalized : fallback;
  }

  private String summarize(String content) {
    return truncate(content, 120);
  }

  private String truncate(String text, int limit) {
    String normalized = String.valueOf(text == null ? "" : text).replaceAll("\\s+", " ").trim();
    return normalized.length() <= limit ? normalized : normalized.substring(0, limit) + "...";
  }

  private static String now() {
    return LocalDateTime.now().format(FMT);
  }
}
