package com.wly.workorder.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

public final class CatalogModels {
  private CatalogModels() {
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class CatalogSearchRequest {
    private BigDecimal budgetMin;
    private BigDecimal budgetMax;
    private BigDecimal budgetTarget;
    private boolean budgetFlexible = true;
    private Integer homeSizeSqm;
    private String homeSizeLevel;
    private List<String> floorTypes;
    private Boolean hasPet;
    private Boolean stationPreference;
    private Boolean noiseSensitive;
  }

  @Data
  @NoArgsConstructor
  @AllArgsConstructor
  public static class CatalogDetailsRequest {
    @Size(min = 1, max = 3)
    private List<@NotBlank String> skuIds;
  }

  @Data
  @Builder
  @NoArgsConstructor
  @AllArgsConstructor
  public static class CatalogProductView {
    private String productId;
    private String skuId;
    private String name;
    private String skuName;
    private String category;
    private String summary;
    private String imageUrl;
    private BigDecimal price;
    private int stock;
    private Map<String, Object> attributes;
    private List<String> highlights;
    private List<String> matchReasons;
    private List<String> warnings;
    private double matchScore;
  }
}
