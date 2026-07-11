package com.wly.workorder.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.config.WorkOrderAIProperties;
import com.wly.workorder.model.AssistantModels.AssistantImageRequest;
import com.wly.workorder.model.KnowledgeModels.KnowledgeAnswer;
import com.wly.workorder.model.KnowledgeModels.KnowledgeDocument;
import com.wly.workorder.model.KnowledgeModels.KnowledgeDocumentList;
import com.wly.workorder.model.KnowledgeModels.SourceDocument;
import com.wly.workorder.model.TicketModels.WorkOrder;
import com.wly.workorder.model.TicketModels.FeedbackReply;
import com.wly.workorder.model.TicketModels.HistoricalCaseSource;
import com.wly.workorder.service.FileStorageService;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.multipart.MultipartFile;

@Component
public class QueryAIService {
  private static final Logger log = LoggerFactory.getLogger(QueryAIService.class);

  private final WorkOrderAIProperties properties;
  private final RestTemplate restTemplate;
  private final Executor asyncExecutor;
  private final ObjectMapper objectMapper;
  private final FileStorageService fileStorageService;

  public QueryAIService(
    WorkOrderAIProperties properties,
    ObjectMapper objectMapper,
    FileStorageService fileStorageService
  ) {
    this.properties = properties;
    this.restTemplate = new RestTemplate();
    this.asyncExecutor = Executors.newFixedThreadPool(5);
    this.objectMapper = objectMapper;
    this.fileStorageService = fileStorageService;
  }

  public CompletableFuture<JsonNode> classifyTicketAsync(
    String ticketId,
    String title,
    String description,
    List<Map<String, String>> replies,
    List<String> images,
    boolean updateCategory
  ) {
    if (!properties.getAiClassification().isEnabled() || (updateCategory && !properties.getAiClassification().isTriggerOnCreate())) {
      return CompletableFuture.completedFuture(null);
    }
    return CompletableFuture.supplyAsync(() -> {
      try {
        ResponseEntity<JsonNode> response = callAI(
          "/ai/classify",
          buildClassificationRequest(ticketId, title, description, replies, images, updateCategory)
        );
        log.info("AI分类成功, ticketId: {}", ticketId);
        return response.getBody();
      } catch (Exception e) {
        log.error("AI分类失败, ticketId: {}", ticketId, e);
        return null;
      }
    }, asyncExecutor);
  }

  public JsonNode classifyTicket(
    String ticketId,
    String title,
    String description,
    List<Map<String, String>> replies,
    List<String> images,
    boolean updateCategory
  ) {
    if (!properties.getAiClassification().isEnabled()) {
      return null;
    }
    try {
      ResponseEntity<JsonNode> response = callAI(
        "/ai/classify",
        buildClassificationRequest(ticketId, title, description, replies, images, updateCategory)
      );
      log.info("AI分类成功, ticketId: {}", ticketId);
      return response.getBody();
    } catch (Exception e) {
      log.error("AI分类失败, ticketId: {}", ticketId, e);
      return null;
    }
  }

  public JsonNode suggestReply(WorkOrder workorder) {
    if (!properties.getAiReplySuggestion().isEnabled()) {
      return null;
    }
    try {
      Map<String, Object> requestBody = Map.of(
        "id", workorder.getId(),
        "title", workorder.getTitle(),
        "description", workorder.getDescription(),
        "category", workorder.getCategory(),
        "emotion", workorder.getEmotion(),
        "owner_username", workorder.getOwnerUsername(),
        "history", toReplyMessages(workorder.getReplies()),
        "images", prepareStoredImages(workorder.getImages())
      );
      ResponseEntity<JsonNode> response = callAI("/ai/suggestion", requestBody);
      log.info("AI回复建议生成成功, ticketId: {}", workorder.getId());
      return response.getBody();
    } catch (Exception e) {
      log.error("AI回复建议生成失败, ticketId: {}", workorder.getId(), e);
      return null;
    }
  }

  public CompletableFuture<Void> rememberCaseAsync(WorkOrder workorder, FeedbackReply finalServiceReply) {
    if (workorder == null) {
      return CompletableFuture.completedFuture(null);
    }
    return CompletableFuture.runAsync(() -> {
      try {
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("ticket_id", workorder.getId());
        requestBody.put("ticket_code", workorder.getCode());
        requestBody.put("title", workorder.getTitle());
        requestBody.put("description", workorder.getDescription());
        requestBody.put("final_reply", finalServiceReply == null ? null : finalServiceReply.getContent());
        requestBody.put("status", workorder.getStatus().name());
        requestBody.put("category", workorder.getCategory() == null ? "" : workorder.getCategory().name());
        requestBody.put("owner_username", workorder.getOwnerUsername());
        requestBody.put("history", toReplyMessages(workorder.getReplies()));
        callAI(
          "/ai/case-memory",
          requestBody
        );
        log.info("历史案例沉淀成功, ticketId: {}", workorder.getId());
      } catch (Exception e) {
        log.error("历史案例沉淀失败, ticketId: {}", workorder.getId(), e);
      }
    }, asyncExecutor);
  }

  public KnowledgeAnswer askKnowledge(String question) {
    if (!properties.getKnowledgeBase().isEnabled()) {
      return null;
    }
    try {
      JsonNode body = callAI("/ai/knowledge/qa", Map.of("question", question)).getBody();
      return body == null ? null : KnowledgeAnswer.builder()
        .answer(body.path("answer").asText())
        .sourceDocuments(mapSourceDocuments(body.path("source_documents")))
        .build();
    } catch (Exception e) {
      log.error("知识库问答失败", e);
      return null;
    }
  }

  public KnowledgeDocumentList listKnowledgeDocuments() {
    if (!properties.getKnowledgeBase().isEnabled()) {
      return null;
    }
    try {
      JsonNode body = callAIGet("/ai/knowledge/documents").getBody();
      if (body == null) {
        return null;
      }
      List<KnowledgeDocument> items = new ArrayList<>();
      for (JsonNode item : body.path("items")) {
        items.add(mapKnowledgeDocument(item));
      }
      return KnowledgeDocumentList.builder()
        .total(body.path("total").asLong(items.size()))
        .items(items)
        .build();
    } catch (Exception e) {
      log.error("知识库文档列表查询失败", e);
      return null;
    }
  }

  public KnowledgeDocument uploadKnowledgeDocument(MultipartFile file, String createdBy) throws IOException {
    if (!properties.getKnowledgeBase().isEnabled()) {
      return null;
    }
    try {
      JsonNode body = callAI(
        "/ai/knowledge/documents/upload",
        Map.of(
          "file_name", file.getOriginalFilename() == null ? "knowledge.txt" : file.getOriginalFilename(),
          "content_type", file.getContentType() == null ? "" : file.getContentType(),
          "content_base64", Base64.getEncoder().encodeToString(file.getBytes()),
          "created_by", createdBy
        )
      ).getBody();
      return body == null ? null : mapKnowledgeDocument(body);
    } catch (HttpStatusCodeException e) {
      throw new IllegalArgumentException(extractAiErrorMessage(e));
    } catch (Exception e) {
      log.error("知识库文档上传失败", e);
      return null;
    }
  }

  public boolean deleteKnowledgeDocument(String documentId) {
    if (!properties.getKnowledgeBase().isEnabled()) {
      return false;
    }
    try {
      JsonNode body = callAIDelete("/ai/knowledge/documents/" + documentId).getBody();
      return body != null && body.path("deleted").asBoolean(false);
    } catch (HttpStatusCodeException e) {
      if (e.getStatusCode() == HttpStatus.NOT_FOUND) {
        return false;
      }
      throw new IllegalStateException("knowledge document delete failed");
    } catch (Exception e) {
      log.error("知识库文档删除失败, documentId: {}", documentId, e);
      throw new IllegalStateException("knowledge document delete failed");
    }
  }

  public ResponseEntity<JsonNode> callAI(String path, Object requestBody) {
    String url = properties.getAiService().getBaseUrl() + path;
    HttpHeaders headers = new HttpHeaders();
    headers.setContentType(MediaType.APPLICATION_JSON);
    HttpEntity<Object> entity = new HttpEntity<>(requestBody, headers);

    int retryCount = 0;
    int maxRetries = properties.getAiService().getRetryCount();
    Exception lastException = null;

    while (retryCount <= 0) {
      try {
        return restTemplate.postForEntity(url, entity, JsonNode.class);
      } catch (Exception e) {
        lastException = e;
        retryCount++;
        if (retryCount <= maxRetries) {
          log.warn("AI服务调用失败, 第{}次重试: {}", retryCount, e.getMessage());
          try {
            Thread.sleep(1000 * retryCount);
          } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
          }
        }
      }
    }
    throw new RuntimeException("AI服务调用失败，已重试" + maxRetries + "次", lastException);
  }

  private ResponseEntity<JsonNode> callAIGet(String path) {
    String url = properties.getAiService().getBaseUrl() + path;
    return restTemplate.getForEntity(url, JsonNode.class);
  }

  private ResponseEntity<JsonNode> callAIDelete(String path) {
    String url = properties.getAiService().getBaseUrl() + path;
    return restTemplate.exchange(url, HttpMethod.DELETE, HttpEntity.EMPTY, JsonNode.class);
  }

  private Map<String, Object> buildClassificationRequest(
    String ticketId,
    String title,
    String description,
    List<Map<String, String>> replies,
    List<String> images,
    boolean updateCategory
  ) {
    Map<String, Object> request = new LinkedHashMap<>();
    request.put("ticket_id", ticketId);
    request.put("title", title);
    request.put("description", description);
    request.put("replies", replies);
    request.put("images", prepareStoredImages(images));
    request.put("update_category", updateCategory);
    return request;
  }

  public JsonNode customerAssistantChat(
    String sessionId,
    String ownerUsername,
    String message,
    List<Map<String, String>> history,
    Map<String, Object> presaleState,
    List<AssistantImageRequest> images
  ) {
    try {
      Map<String, Object> requestBody = new LinkedHashMap<>();
      requestBody.put("session_id", sessionId);
      requestBody.put("owner_username", ownerUsername);
      requestBody.put("message", message);
      requestBody.put("history", history == null ? List.of() : history);
      requestBody.put("presale_state", presaleState == null ? Map.of() : presaleState);
      requestBody.put("images", prepareAssistantImages(images));
      ResponseEntity<JsonNode> response = callAI("/ai/customer-assistant/chat", requestBody);
      return response.getBody();
    } catch (Exception e) {
      log.error("用户侧AI客服调用失败, sessionId: {}", sessionId, e);
      return null;
    }
  }

  private List<Map<String, Object>> prepareAssistantImages(List<AssistantImageRequest> images) {
    if (images == null || images.isEmpty()) {
      return List.of();
    }
    List<Map<String, Object>> result = new ArrayList<>();
    for (AssistantImageRequest image : images.stream().limit(5).toList()) {
      try {
        String serverPath = String.valueOf(image.getServerPath()).replace('\\', '/').trim();
        if (!serverPath.startsWith("image/") || serverPath.contains("..")) {
          throw new IllegalArgumentException("invalid image path");
        }
        Path path = fileStorageService.resolve(serverPath);
        if (!Files.isRegularFile(path)) {
          throw new IOException("image not found");
        }
        byte[] content = Files.readAllBytes(path);
        if (content.length == 0 || content.length > 7L * 1024 * 1024) {
          throw new IllegalArgumentException("image size is invalid");
        }
        String contentType = normalizeImageContentType(image.getContentType(), serverPath);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", image.getName());
        payload.put("content_type", contentType);
        payload.put("content_base64", Base64.getEncoder().encodeToString(content));
        result.add(payload);
      } catch (Exception ex) {
        // 单张图片异常不阻断整轮文本客服，视觉服务会对剩余有效图片继续分析。
        log.warn("跳过无效的AI客服图片, name: {}, reason: {}", image.getName(), ex.getMessage());
      }
    }
    return result;
  }

  private List<Map<String, Object>> prepareStoredImages(List<String> imagePaths) {
    if (imagePaths == null || imagePaths.isEmpty()) {
      return List.of();
    }
    List<AssistantImageRequest> images = new ArrayList<>();
    for (String value : imagePaths.stream().limit(5).toList()) {
      String serverPath = String.valueOf(value == null ? "" : value).replace('\\', '/').trim();
      if (serverPath.startsWith("/api/files/")) {
        serverPath = serverPath.substring("/api/files/".length());
      }
      String name = serverPath.contains("/") ? serverPath.substring(serverPath.lastIndexOf('/') + 1) : serverPath;
      images.add(new AssistantImageRequest(name, serverPath, "", 0));
    }
    return prepareAssistantImages(images);
  }

  private String normalizeImageContentType(String contentType, String serverPath) {
    String normalized = String.valueOf(contentType == null ? "" : contentType).trim().toLowerCase();
    if (normalized.startsWith("image/")) {
      return normalized;
    }
    String lowerPath = serverPath.toLowerCase();
    if (lowerPath.endsWith(".png")) return "image/png";
    if (lowerPath.endsWith(".webp")) return "image/webp";
    if (lowerPath.endsWith(".gif")) return "image/gif";
    if (lowerPath.endsWith(".bmp")) return "image/bmp";
    return "image/jpeg";
  }

  public JsonNode generateRefundPlan(WorkOrder workorder) {
    if (workorder == null) {
      return null;
    }
    try {
      Map<String, Object> requestBody = Map.of(
        "ticket_id", workorder.getId(),
        "title", workorder.getTitle(),
        "description", workorder.getDescription(),
        "owner_username", workorder.getOwnerUsername(),
        "history", toReplyMessages(workorder.getReplies())
      );
      ResponseEntity<JsonNode> response = callAI("/ai/refund/plan", requestBody);
      log.info("退款方案生成成功, ticketId: {}", workorder.getId());
      return response.getBody();
    } catch (Exception e) {
      log.error("退款方案生成失败, ticketId: {}", workorder.getId(), e);
      return null;
    }
  }

  private List<Map<String, String>> toReplyMessages(List<FeedbackReply> replies) {
    if (replies == null || replies.isEmpty()) {
      return List.of();
    }
    List<Map<String, String>> messages = new ArrayList<>();
    for (FeedbackReply reply : replies) {
      Map<String, String> message = new HashMap<>();
      message.put("id", reply.getId() == null ? "" : reply.getId());
      message.put("role", reply.getRole() == null ? "user" : reply.getRole());
      message.put("content", reply.getContent() == null ? "" : reply.getContent());
      message.put("created_at", reply.getCreatedAt() == null ? "" : reply.getCreatedAt());
      messages.add(message);
    }
    return messages;
  }

  private List<SourceDocument> mapSourceDocuments(JsonNode sourceNodes) {
    List<SourceDocument> sources = new ArrayList<>();
    for (JsonNode item : sourceNodes) {
      sources.add(SourceDocument.builder()
        .id(item.path("id").asText())
        .title(item.path("title").asText())
        .relevanceScore(item.path("relevance_score").asDouble())
        .build());
    }
    return sources;
  }

  public List<HistoricalCaseSource> mapHistoricalCaseSources(JsonNode sourceNodes) {
    List<HistoricalCaseSource> sources = new ArrayList<>();
    for (JsonNode item : sourceNodes) {
      sources.add(HistoricalCaseSource.builder()
        .ticketId(item.path("ticket_id").asText())
        .ticketCode(item.path("ticket_code").asText())
        .title(item.path("title").asText())
        .finalReply(item.path("final_reply").asText())
        .similarityScore(item.path("similarity_score").asDouble())
        .build());
    }
    return sources;
  }

  private KnowledgeDocument mapKnowledgeDocument(JsonNode item) {
    return KnowledgeDocument.builder()
      .id(item.path("id").asText())
      .title(item.path("title").asText())
      .fileName(item.path("file_name").asText())
      .fileExt(item.path("file_ext").asText())
      .fileSize(item.path("file_size").asLong())
      .createdBy(item.path("created_by").asText())
      .status(item.path("status").asText())
      .createdAt(item.path("created_at").asText())
      .build();
  }

  private String extractAiErrorMessage(HttpStatusCodeException exception) {
    try {
      JsonNode body = objectMapper.readTree(exception.getResponseBodyAsString());
      String detail = body.path("detail").asText();
      return detail == null || detail.isBlank() ? "knowledge document upload failed" : detail;
    } catch (Exception ignored) {
      return "knowledge document upload failed";
    }
  }
}
