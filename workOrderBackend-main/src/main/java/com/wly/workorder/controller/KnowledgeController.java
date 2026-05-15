package com.wly.workorder.controller;

import com.wly.workorder.auth.AuthContext;
import com.wly.workorder.auth.AuthRole;
import com.wly.workorder.auth.AuthSession;
import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.KnowledgeModels.KnowledgeAnswer;
import com.wly.workorder.model.KnowledgeModels.KnowledgeDocument;
import com.wly.workorder.model.KnowledgeModels.KnowledgeDocumentList;
import com.wly.workorder.model.KnowledgeModels.KnowledgeQuestionRequest;
import com.wly.workorder.service.impl.QueryAIService;
import jakarta.validation.Valid;
import java.io.IOException;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeController {
  private final QueryAIService queryAIService;

  public KnowledgeController(QueryAIService queryAIService) {
    this.queryAIService = queryAIService;
  }

  @PostMapping("/qa")
  public ApiResponse<KnowledgeAnswer> ask(@RequestBody @Valid KnowledgeQuestionRequest request) {
    KnowledgeAnswer answer = queryAIService.askKnowledge(request.getQuestion());
    return answer == null ? ApiResponse.fail("knowledge qa failed") : ApiResponse.success(answer);
  }

  @GetMapping("/documents")
  public ApiResponse<KnowledgeDocumentList> listDocuments() {
    requireAdmin();
    KnowledgeDocumentList documents = queryAIService.listKnowledgeDocuments();
    return documents == null ? ApiResponse.fail("list knowledge documents failed") : ApiResponse.success(documents);
  }

  @PostMapping("/documents/upload")
  public ApiResponse<KnowledgeDocument> upload(@RequestParam("file") MultipartFile file) throws IOException {
    AuthSession session = requireAdmin();
    KnowledgeDocument document = queryAIService.uploadKnowledgeDocument(file, session.getUsername());
    return document == null ? ApiResponse.fail("upload knowledge document failed") : ApiResponse.success("uploaded", document);
  }

  @DeleteMapping("/documents/{id}")
  public ApiResponse<Boolean> delete(@PathVariable String id) {
    requireAdmin();
    boolean deleted = queryAIService.deleteKnowledgeDocument(id);
    return deleted ? ApiResponse.success("deleted", true) : ApiResponse.fail("knowledge document not found");
  }

  private AuthSession requireAdmin() {
    AuthSession session = AuthContext.require();
    if (session.getRole() != AuthRole.ADMIN) {
      throw new IllegalStateException("Only admin can manage knowledge documents");
    }
    return session;
  }
}
