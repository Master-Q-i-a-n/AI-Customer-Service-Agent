package com.wly.workorder.controller;

import com.wly.workorder.common.ApiResponse;
import com.wly.workorder.model.OrderModels.UserOrderView;
import com.wly.workorder.service.OrderQueryService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
  private final OrderQueryService orderQueryService;

  public OrderController(OrderQueryService orderQueryService) {
    this.orderQueryService = orderQueryService;
  }

  @GetMapping("/mine")
  public ApiResponse<List<UserOrderView>> mine() {
    return ApiResponse.success(orderQueryService.listCurrentUserOrders());
  }
}

