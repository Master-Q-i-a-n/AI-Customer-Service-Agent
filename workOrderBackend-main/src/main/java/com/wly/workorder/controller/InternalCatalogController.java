package com.wly.workorder.controller;

import com.wly.workorder.auth.AuthException;
import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.config.WorkOrderAIProperties;
import com.wly.workorder.model.CatalogModels.CatalogDetailsRequest;
import com.wly.workorder.model.CatalogModels.CatalogProductView;
import com.wly.workorder.model.CatalogModels.CatalogSearchRequest;
import com.wly.workorder.service.CatalogService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/internal/catalog")
public class InternalCatalogController {
  private final CatalogService catalogService;
  private final WorkOrderAIProperties properties;

  public InternalCatalogController(CatalogService catalogService, WorkOrderAIProperties properties) {
    this.catalogService = catalogService;
    this.properties = properties;
  }

  @PostMapping("/search")
  public ApiResponse<List<CatalogProductView>> search(
    @RequestHeader(value = "X-Internal-Agent-Token", required = false) String token,
    @RequestBody(required = false) CatalogSearchRequest request
  ) {
    requireInternalToken(token);
    return ApiResponse.success(catalogService.search(request));
  }

  @PostMapping("/details")
  public ApiResponse<List<CatalogProductView>> details(
    @RequestHeader(value = "X-Internal-Agent-Token", required = false) String token,
    @RequestBody @Valid CatalogDetailsRequest request
  ) {
    requireInternalToken(token);
    return ApiResponse.success(catalogService.details(request.getSkuIds()));
  }

  private void requireInternalToken(String token) {
    if (!properties.getAiService().getInternalToken().equals(token)) {
      throw new AuthException(ApiResponse.withCode(403, "forbidden", null));
    }
  }
}
