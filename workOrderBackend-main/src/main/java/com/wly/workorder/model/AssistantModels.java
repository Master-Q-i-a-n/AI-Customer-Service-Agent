package com.wly.workorder.model;

import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.Map;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public final class AssistantModels {
  private AssistantModels() {
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class SendAssistantMessageRequest {
    @NotBlank
    private String content;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class AssistantMessageView {
    private String id;
    private String role;
    private String content;
    private String action;
    private Map<String, Object> metadata;
    private String createdAt;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class AssistantSessionView {
    private String id;
    private String status;
    private String route;
    private String summary;
    private Map<String, Object> pendingTicketDraft;
    private Map<String, Object> presaleState;
    private String ticketId;
    private List<AssistantMessageView> messages;
    private String createdAt;
    private String updatedAt;
  }
}
