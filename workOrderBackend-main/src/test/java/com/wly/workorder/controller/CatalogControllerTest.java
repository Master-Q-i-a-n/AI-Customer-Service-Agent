package com.wly.workorder.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest(properties = {
  "spring.datasource.url=jdbc:h2:mem:catalog_controller;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false",
  "spring.datasource.driver-class-name=org.h2.Driver",
  "spring.datasource.username=sa",
  "spring.datasource.password=",
  "spring.sql.init.mode=always",
  "workorder.ai-service.internal-token=test-catalog-token"
})
@AutoConfigureMockMvc
class CatalogControllerTest {
  @Autowired
  private MockMvc mockMvc;

  @Autowired
  private JdbcTemplate jdbcTemplate;

  @Test
  void searchAppliesHardRequirementsAndReturnsGroundedProducts() throws Exception {
    mockMvc.perform(post("/api/internal/catalog/search")
        .header("X-Internal-Agent-Token", "test-catalog-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
          {
            "budgetMax": 2500,
            "budgetFlexible": false,
            "homeSizeSqm": 90,
            "floorTypes": ["木地板"],
            "hasPet": true
          }
          """))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data.length()").value(1))
      .andExpect(jsonPath("$.data[0].skuId").value("sku-p2-gray"))
      .andExpect(jsonPath("$.data[0].price").value(2299.00))
      .andExpect(jsonPath("$.data[0].attributes.pet_friendly").value(true));
  }

  @Test
  void targetBudgetUsesHardTwentyPercentWindowAndReportsOverspend() throws Exception {
    mockMvc.perform(post("/api/internal/catalog/search")
        .header("X-Internal-Agent-Token", "test-catalog-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"budgetTarget\":2000,\"budgetFlexible\":true,\"homeSizeSqm\":90}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.length()").value(1))
      .andExpect(jsonPath("$.data[0].skuId").value("sku-p2-gray"))
      .andExpect(jsonPath("$.data[0].price").value(2299.00))
      .andExpect(jsonPath("$.data[0].warnings[0]").value("比目标预算高 ¥299"));
  }

  @Test
  void explicitBudgetRangeTakesPriorityOverTargetWindow() throws Exception {
    mockMvc.perform(post("/api/internal/catalog/search")
        .header("X-Internal-Agent-Token", "test-catalog-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"budgetMin\":3200,\"budgetMax\":3400,\"budgetTarget\":2000,\"budgetFlexible\":true,\"homeSizeSqm\":90}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.length()").value(1))
      .andExpect(jsonPath("$.data[0].skuId").value("sku-m3-white"));
  }

  @Test
  @Transactional
  void targetBudgetStillExcludesOutOfStockSku() throws Exception {
    jdbcTemplate.update("update ec_product_sku set stock=0 where id=?", "sku-p2-gray");

    mockMvc.perform(post("/api/internal/catalog/search")
        .header("X-Internal-Agent-Token", "test-catalog-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"budgetTarget\":2000,\"homeSizeSqm\":90}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data.length()").value(0));
  }

  @Test
  void detailsPreserveRequestedOrderAndRejectWrongToken() throws Exception {
    mockMvc.perform(post("/api/internal/catalog/details")
        .header("X-Internal-Agent-Token", "test-catalog-token")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"skuIds\":[\"sku-x4-black\",\"sku-s1-white\"]}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.data[0].skuId").value("sku-x4-black"))
      .andExpect(jsonPath("$.data[1].skuId").value("sku-s1-white"));

    mockMvc.perform(post("/api/internal/catalog/search")
        .header("X-Internal-Agent-Token", "wrong")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(403));
  }
}
