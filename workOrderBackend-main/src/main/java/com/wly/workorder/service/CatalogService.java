package com.wly.workorder.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.model.CatalogModels.CatalogProductView;
import com.wly.workorder.model.CatalogModels.CatalogSearchRequest;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
  private static final BigDecimal TARGET_BUDGET_MIN_FACTOR = new BigDecimal("0.80");
  private static final BigDecimal TARGET_BUDGET_MAX_FACTOR = new BigDecimal("1.20");

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;

  public CatalogService(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
  }

  public List<CatalogProductView> search(CatalogSearchRequest request) {
    CatalogSearchRequest criteria = request == null ? new CatalogSearchRequest() : request;
    return loadProducts(List.of()).stream()
      .filter(item -> matchesHardConstraints(item, criteria))
      .map(item -> score(item, criteria))
      .sorted(Comparator.comparingDouble(CatalogProductView::getMatchScore).reversed()
        .thenComparing(CatalogProductView::getPrice))
      .limit(3)
      .toList();
  }

  public List<CatalogProductView> details(List<String> skuIds) {
    List<String> normalized = (skuIds == null ? List.<String>of() : skuIds).stream()
      .map(value -> String.valueOf(value == null ? "" : value).trim())
      .filter(value -> !value.isEmpty())
      .distinct()
      .limit(3)
      .toList();
    if (normalized.isEmpty()) {
      throw new IllegalArgumentException("sku_ids is required");
    }
    Map<String, CatalogProductView> bySku = new LinkedHashMap<>();
    loadProducts(normalized).forEach(item -> bySku.put(item.getSkuId(), item));
    return normalized.stream().map(bySku::get).filter(item -> item != null).toList();
  }

  private List<CatalogProductView> loadProducts(List<String> skuIds) {
    StringBuilder sql = new StringBuilder(
      "select p.id product_id, p.name, p.category, p.summary, p.image_url, " +
        "s.id sku_id, s.sku_name, s.price, s.stock, s.attributes_json " +
        "from ec_product p join ec_product_sku s on s.product_id=p.id " +
        "where p.active=1 and s.active=1 and s.stock>0"
    );
    List<Object> args = new ArrayList<>();
    if (skuIds != null && !skuIds.isEmpty()) {
      sql.append(" and s.id in (");
      sql.append(String.join(",", skuIds.stream().map(value -> "?").toList()));
      sql.append(")");
      args.addAll(skuIds);
    }
    sql.append(" order by p.id, s.id");
    return jdbcTemplate.query(
      sql.toString(),
      (rs, rowNum) -> CatalogProductView.builder()
        .productId(rs.getString("product_id"))
        .skuId(rs.getString("sku_id"))
        .name(rs.getString("name"))
        .skuName(rs.getString("sku_name"))
        .category(rs.getString("category"))
        .summary(rs.getString("summary"))
        .imageUrl(rs.getString("image_url"))
        .price(rs.getBigDecimal("price"))
        .stock(rs.getInt("stock"))
        .attributes(readAttributes(rs.getString("attributes_json")))
        .highlights(new ArrayList<>())
        .matchReasons(new ArrayList<>())
        .warnings(new ArrayList<>())
        .matchScore(0)
        .build(),
      args.toArray()
    );
  }

  private boolean matchesHardConstraints(CatalogProductView item, CatalogSearchRequest criteria) {
    BigDecimal budgetMin = effectiveBudgetMin(criteria);
    BigDecimal budgetMax = effectiveBudgetMax(criteria);
    if (budgetMin != null && item.getPrice().compareTo(budgetMin) < 0) {
      return false;
    }
    if (budgetMax != null && item.getPrice().compareTo(budgetMax) > 0) {
      return false;
    }

    Integer requestedSize = effectiveHomeSize(criteria);
    if (requestedSize != null && intAttribute(item, "home_size_max") < requestedSize) {
      return false;
    }
    if (criteria.getFloorTypes() != null && !criteria.getFloorTypes().isEmpty()) {
      List<String> supported = stringListAttribute(item, "floor_types");
      if (!supported.containsAll(criteria.getFloorTypes())) {
        return false;
      }
    }
    if (Boolean.TRUE.equals(criteria.getHasPet()) && !booleanAttribute(item, "pet_friendly")) {
      return false;
    }
    String station = stringAttribute(item, "station_type");
    if (Boolean.TRUE.equals(criteria.getStationPreference()) && "无".equals(station)) {
      return false;
    }
    return !Boolean.FALSE.equals(criteria.getStationPreference()) || "无".equals(station);
  }

  private CatalogProductView score(CatalogProductView item, CatalogSearchRequest criteria) {
    List<String> highlights = new ArrayList<>();
    List<String> reasons = new ArrayList<>();
    List<String> warnings = new ArrayList<>();
    double score = 20;

    BigDecimal target = criteria.getBudgetTarget();
    if (target != null && target.compareTo(BigDecimal.ZERO) > 0) {
      BigDecimal delta = item.getPrice().subtract(target).abs();
      double ratio = delta.divide(target, 4, RoundingMode.HALF_UP).doubleValue();
      score += Math.max(0, 35 * (1 - ratio));
      if (item.getPrice().compareTo(target) > 0) {
        warnings.add("比目标预算高 ¥" + item.getPrice().subtract(target).stripTrailingZeros().toPlainString());
      } else {
        reasons.add("价格接近目标预算");
      }
    } else if (criteria.getBudgetMax() != null) {
      score += 30;
      reasons.add("符合预算范围");
    }

    Integer requestedSize = effectiveHomeSize(criteria);
    int maxSize = intAttribute(item, "home_size_max");
    if (requestedSize != null) {
      score += Math.max(5, 20 - Math.max(0, maxSize - requestedSize) / 10.0);
      reasons.add("覆盖 " + requestedSize + "㎡ 户型");
    }
    if (Boolean.TRUE.equals(criteria.getHasPet()) && booleanAttribute(item, "pet_friendly")) {
      score += 15;
      reasons.add("防毛发缠绕，适合宠物家庭");
    }
    if (criteria.getFloorTypes() != null && !criteria.getFloorTypes().isEmpty()) {
      score += 10;
      reasons.add("适配" + String.join("、", criteria.getFloorTypes()));
    }
    String station = stringAttribute(item, "station_type");
    if (criteria.getStationPreference() != null) {
      score += 10;
      reasons.add(Boolean.TRUE.equals(criteria.getStationPreference()) ? station : "无需基站");
    }
    if (Boolean.TRUE.equals(criteria.getNoiseSensitive())) {
      int noise = intAttribute(item, "noise_db");
      score += noise <= 55 ? 10 : Math.max(0, 10 - (noise - 55) * 2);
      reasons.add("工作噪音约 " + noise + "dB");
    }

    highlights.add(intAttribute(item, "suction_pa") + "Pa 吸力");
    highlights.add(intAttribute(item, "runtime_minutes") + " 分钟续航");
    highlights.add("无".equals(station) ? stringAttribute(item, "navigation") : station);
    item.setHighlights(highlights);
    item.setMatchReasons(reasons.stream().distinct().limit(3).toList());
    item.setWarnings(warnings);
    item.setMatchScore(Math.round(score * 100.0) / 100.0);
    return item;
  }

  private Integer effectiveHomeSize(CatalogSearchRequest criteria) {
    if (criteria.getHomeSizeSqm() != null && criteria.getHomeSizeSqm() > 0) {
      return criteria.getHomeSizeSqm();
    }
    String level = String.valueOf(criteria.getHomeSizeLevel() == null ? "" : criteria.getHomeSizeLevel())
      .trim().toUpperCase(Locale.ROOT);
    return switch (level) {
      case "SMALL" -> 80;
      case "MEDIUM" -> 120;
      case "LARGE" -> 160;
      default -> null;
    };
  }

  private BigDecimal effectiveBudgetMin(CatalogSearchRequest criteria) {
    if (criteria.getBudgetMin() != null || criteria.getBudgetMax() != null) {
      return criteria.getBudgetMin();
    }
    BigDecimal target = criteria.getBudgetTarget();
    if (target == null || target.compareTo(BigDecimal.ZERO) <= 0) {
      return null;
    }
    // 目标价表达使用固定 ±20% 的硬推荐窗口，防止排序后仍返回明显超预算商品。
    return target.multiply(TARGET_BUDGET_MIN_FACTOR);
  }

  private BigDecimal effectiveBudgetMax(CatalogSearchRequest criteria) {
    if (criteria.getBudgetMin() != null || criteria.getBudgetMax() != null) {
      return criteria.getBudgetMax();
    }
    BigDecimal target = criteria.getBudgetTarget();
    if (target == null || target.compareTo(BigDecimal.ZERO) <= 0) {
      return null;
    }
    return target.multiply(TARGET_BUDGET_MAX_FACTOR);
  }

  private Map<String, Object> readAttributes(String json) {
    try {
      return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() { });
    } catch (Exception ex) {
      return new LinkedHashMap<>();
    }
  }

  private int intAttribute(CatalogProductView item, String key) {
    Object value = item.getAttributes().get(key);
    return value instanceof Number number ? number.intValue() : 0;
  }

  private boolean booleanAttribute(CatalogProductView item, String key) {
    Object value = item.getAttributes().get(key);
    return value instanceof Boolean bool && bool;
  }

  private String stringAttribute(CatalogProductView item, String key) {
    return String.valueOf(item.getAttributes().getOrDefault(key, ""));
  }

  private List<String> stringListAttribute(CatalogProductView item, String key) {
    Object value = item.getAttributes().get(key);
    if (!(value instanceof List<?> values)) {
      return List.of();
    }
    return values.stream().map(String::valueOf).toList();
  }
}
