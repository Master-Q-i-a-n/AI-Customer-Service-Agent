package com.wly.workorder.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest(properties = {
  "spring.datasource.url=jdbc:h2:mem:order_controller;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_UPPER=false",
  "spring.datasource.driver-class-name=org.h2.Driver",
  "spring.datasource.username=sa",
  "spring.datasource.password=",
  "spring.sql.init.mode=always"
})
@AutoConfigureMockMvc
@Transactional
class OrderControllerTest {
  @Autowired
  private MockMvc mockMvc;
  @Autowired
  private ObjectMapper objectMapper;

  @Test
  void userCanReadOnlyOwnOrdersWithItemsAndShipment() throws Exception {
    String token = login("user", "user123");

    mockMvc.perform(get("/api/orders/mine").header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andExpect(jsonPath("$.data[0].orderNo").exists())
      .andExpect(jsonPath("$.data[0].items[0].productName").exists())
      .andExpect(jsonPath("$.data[0].shipment.status").exists())
      .andExpect(jsonPath("$.data[0].transactionNo").doesNotExist())
      .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("ORD-1004-PAID"))))
      .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("transactionNo"))));
  }

  @Test
  void adminCannotReadUserOrderPage() throws Exception {
    String token = login("admin", "admin123");

    mockMvc.perform(get("/api/orders/mine").header("Authorization", token))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(403));
  }

  private String login(String username, String password) throws Exception {
    MvcResult result = mockMvc.perform(post("/api/auth/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"))
      .andExpect(status().isOk())
      .andExpect(jsonPath("$.code").value(200))
      .andReturn();
    JsonNode root = objectMapper.readTree(result.getResponse().getContentAsString());
    return root.path("data").path("token").asText();
  }
}

