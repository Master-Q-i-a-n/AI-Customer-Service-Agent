package com.wly.workorder.model;

import jakarta.validation.constraints.NotBlank;
import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public final class KnowledgeModels {
  private KnowledgeModels() {
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class KnowledgeQuestionRequest {
    @NotBlank
    private String question;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class SourceDocument {
    private String id;
    private String title;
    private double relevanceScore;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class KnowledgeAnswer {
    private String answer;
    private List<SourceDocument> sourceDocuments;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class KnowledgeDocument {
    private String id;
    private String title;
    private String fileName;
    private String fileExt;
    private long fileSize;
    private String createdBy;
    private String status;
    private String createdAt;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class KnowledgeDocumentList {
    private long total;
    private List<KnowledgeDocument> items;
  }
}
