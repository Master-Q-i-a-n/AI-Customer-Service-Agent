package com.wly.workorder.service;

import com.wly.workorder.model.RefundModels.RefundDraftCommand;
import com.wly.workorder.model.RefundModels.RefundEvaluation;
import com.wly.workorder.model.RefundModels.RefundPolicySource;
import com.wly.workorder.model.RefundModels.RefundRequestView;
import com.wly.workorder.model.RefundModels.RefundType;
import com.wly.workorder.model.RefundModels.ReviewRefundRequest;
import java.util.List;
import java.util.Map;

public interface RefundService {
  List<Map<String, Object>> findCurrentUserOrders(String ownerUsername, String orderHint, String productHint);

  Map<String, Object> getOrderDetail(String ownerUsername, String orderNo);

  Map<String, Object> getLogistics(String ownerUsername, String orderNo);

  List<RefundPolicySource> findPolicies(RefundType refundType);

  RefundEvaluation evaluate(String ownerUsername, String orderNo, RefundType refundType);

  RefundRequestView saveAgentDraft(String ticketId, String ownerUsername, RefundDraftCommand command);

  RefundRequestView getByTicketId(String ticketId);

  RefundRequestView review(String ticketId, String adminUsername, ReviewRefundRequest request);

  RefundRequestView confirmReturnReceived(String ticketId, String adminUsername, int version);
}
