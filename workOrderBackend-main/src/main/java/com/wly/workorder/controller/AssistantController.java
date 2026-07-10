package com.wly.workorder.controller;

import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.AssistantModels.AssistantSessionView;
import com.wly.workorder.model.AssistantModels.SendAssistantMessageRequest;
import com.wly.workorder.service.AssistantService;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/assistant")
public class AssistantController {
  private final AssistantService assistantService;

  public AssistantController(AssistantService assistantService) {
    this.assistantService = assistantService;
  }

  @PostMapping("/sessions")
  public ApiResponse<AssistantSessionView> createSession() {
    return ApiResponse.success(assistantService.createSession());
  }

  @PostMapping("/sessions/messages")
  public ApiResponse<AssistantSessionView> startSessionWithMessage(
    @RequestBody @Valid SendAssistantMessageRequest request
  ) {
    return ApiResponse.success(assistantService.startSessionWithMessage(request.getContent()));
  }

  @GetMapping("/sessions")
  public ApiResponse<List<AssistantSessionView>> listSessions() {
    return ApiResponse.success(assistantService.listSessions());
  }

  @GetMapping("/sessions/{id}")
  public ApiResponse<AssistantSessionView> getSession(@PathVariable String id) {
    return ApiResponse.success(assistantService.getSession(id));
  }

  @DeleteMapping("/sessions/{id}")
  public ApiResponse<Map<String, String>> deleteSession(@PathVariable String id) {
    assistantService.softDeleteSession(id);
    return ApiResponse.success("会话已删除", Map.of("id", id));
  }

  @PostMapping("/sessions/{id}/messages")
  public ApiResponse<AssistantSessionView> sendMessage(
    @PathVariable String id,
    @RequestBody @Valid SendAssistantMessageRequest request
  ) {
    return ApiResponse.success(assistantService.sendMessage(id, request.getContent()));
  }

  @PostMapping("/sessions/{id}/ticket")
  public ApiResponse<AssistantSessionView> confirmTicket(@PathVariable String id) {
    return ApiResponse.success(assistantService.confirmTicket(id));
  }
}
