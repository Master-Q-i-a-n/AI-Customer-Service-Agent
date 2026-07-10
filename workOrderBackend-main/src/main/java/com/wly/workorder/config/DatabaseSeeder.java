package com.wly.workorder.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.wly.workorder.model.TicketModels.ServiceGroup;
import com.wly.workorder.model.TicketModels.TicketCategory;
import com.wly.workorder.model.TicketModels.TicketEmotion;
import com.wly.workorder.model.TicketModels.TicketPriority;
import com.wly.workorder.model.TicketModels.TicketStatus;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class DatabaseSeeder implements CommandLineRunner {
  private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.CHINA);

  private final JdbcTemplate jdbcTemplate;
  private final ObjectMapper objectMapper;

  public DatabaseSeeder(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
    this.jdbcTemplate = jdbcTemplate;
    this.objectMapper = objectMapper;
  }

  @Override
  public void run(String... args) throws Exception {
    ensureAssigneeColumn();
    ensureAvatarColumn();
    ensureUserServiceGroupColumn();
    ensureCategoryColumn();
    ensurePriorityColumn();
    ensureEmotionColumn();
    ensureServiceGroupColumn();
    ensureKnowledgeDocumentTable();
    ensureCaseMemoryTable();
    ensureTicketMemoryTable();
    ensureUserMemoryTable();
    ensureAssistantTables();
    ensureCommerceRefundTables();
    ensureCatalogTables();

    Integer userCount = jdbcTemplate.queryForObject("select count(*) from wo_user", Integer.class);
    if (userCount == null || userCount == 0) {
      seedUsers();
    }
    backfillUserServiceGroups();

    Integer feedbackCount = jdbcTemplate.queryForObject("select count(*) from wo_feedback", Integer.class);
    if (feedbackCount == null || feedbackCount == 0) {
      seedFeedbacks();
    }

    seedCommerceOrders();
    seedCatalog();

    backfillServiceGroups();
  }

  private void seedUsers() {
    String now = now();
    jdbcTemplate.update(
      "insert ignore into wo_user (id, username, password, display_name, avatar_url, role, service_group, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "user-1", "user", "user123", "普通用户", "", "USER", "", now, now
    );
    jdbcTemplate.update(
      "insert ignore into wo_user (id, username, password, display_name, avatar_url, role, service_group, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "admin-1", "admin", "admin123", "系统管理员", "", "ADMIN", ServiceGroup.PRODUCT_CONSULTING.name(), now, now
    );
  }

  private void seedFeedbacks() throws Exception {
    String now = now();

    jdbcTemplate.update(
      "insert into wo_feedback (id, code, title, description, category, priority, emotion, status, owner_username, account_name, assignee, images_json, attachments_json, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "fb-1", "FB-001", "导出任务在大数据量下失败",
      "每次导出超过 10 万条数据时都会超时失败，影响了月度报表生成，请尽快协助排查。",
      "技术故障", TicketPriority.高.name(), TicketEmotion.焦虑.name(), TicketStatus.PROCESSING.name(), "user", "西湖托育中心", "客服一组",
      json(List.of(textAsset("附件-导出日志.txt", "导出日志示例：导出任务在 60% 左右超时"))),
      json(List.of("data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='112' viewBox='0 0 160 112'%3E%3Crect width='160' height='112' rx='18' fill='%237aa7ff'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='white' font-size='16'%3E导出报错%3C/text%3E%3C/svg%3E")),
      now, now
    );
    jdbcTemplate.update(
      "insert into wo_feedback (id, code, title, description, category, priority, emotion, status, owner_username, account_name, assignee, images_json, attachments_json, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "fb-2", "FB-002", "移动端导航在小屏幕重叠",
      "手机横屏进入系统后，侧边导航和顶部导航会发生重叠，部分按钮无法点击。",
      "技术故障", TicketPriority.中.name(), TicketEmotion.困惑.name(), TicketStatus.CLOSED.name(), "user", "城南幼儿园", "前端组", "[]", "[]", now, now
    );
    jdbcTemplate.update(
      "insert into wo_feedback (id, code, title, description, category, priority, emotion, status, owner_username, account_name, assignee, images_json, attachments_json, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "fb-3", "FB-003", "账号权限配置后仍看不到模块",
      "账号已经分配了查看权限，但登录后依旧无法进入数据模块，请协助检查权限配置。",
      "产品咨询", TicketPriority.低.name(), TicketEmotion.平静.name(), TicketStatus.SOLVED.name(), "user", "余杭护理院", "权限组",
      "[]",
      json(List.of(textAsset("权限说明.docx", "权限说明：已补齐角色菜单授权和数据看板查看范围"))),
      now, now
    );
    jdbcTemplate.update(
      "insert into wo_feedback (id, code, title, description, category, priority, emotion, status, owner_username, account_name, assignee, images_json, attachments_json, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      "fb-4", "FB-004", "打印预览按钮点击无响应",
      "申请单详情页里的打印预览按钮点了没有任何反应，怀疑是浏览器兼容问题。",
      "功能需求", TicketPriority.紧急.name(), TicketEmotion.急迫.name(), TicketStatus.PENDING.name(), "user", "滨江园区", "", "[]", "[]", now, now
    );

    jdbcTemplate.update(
      "insert into wo_feedback_reply (id, feedback_id, role, author, content, created_at) values (?, ?, ?, ?, ?, ?)",
      "rep-1", "fb-1", "user", "西湖托育中心", "<p>导出到 60% 左右时会提示超时。</p>", now
    );
    jdbcTemplate.update(
      "insert into wo_feedback_reply (id, feedback_id, role, author, content, created_at) values (?, ?, ?, ?, ?, ?)",
      "rep-2", "fb-1", "service", "系统管理员", "<p>已收到反馈，正在定位导出任务的超时原因。</p>", now
    );
    jdbcTemplate.update(
      "insert into wo_feedback_reply (id, feedback_id, role, author, content, created_at) values (?, ?, ?, ?, ?, ?)",
      "rep-3", "fb-2", "service", "系统管理员", "<p>该问题已在新版本中修复，请刷新页面后再试。</p>", now
    );
    jdbcTemplate.update(
      "insert into wo_feedback_reply (id, feedback_id, role, author, content, created_at) values (?, ?, ?, ?, ?, ?)",
      "rep-4", "fb-3", "service", "系统管理员", "<p>已重新校准角色菜单权限，问题已处理完成。</p>", now
    );
    jdbcTemplate.update(
      "insert into wo_feedback_reply (id, feedback_id, role, author, content, created_at) values (?, ?, ?, ?, ?, ?)",
      "rep-5", "fb-3", "user", "余杭护理院", "<p>现在可以正常查看了，感谢处理。</p>", now
    );
  }

  private String json(Object value) throws Exception {
    return objectMapper.writeValueAsString(value);
  }

  private Map<String, Object> textAsset(String name, String text) {
    return Map.of(
      "uid", "att-" + name.hashCode(),
      "name", name,
      "url", "data:text/plain;charset=utf-8," + java.net.URLEncoder.encode(text, java.nio.charset.StandardCharsets.UTF_8),
      "fileUrl", "data:text/plain;charset=utf-8," + java.net.URLEncoder.encode(text, java.nio.charset.StandardCharsets.UTF_8),
      "serverPath", "data:text/plain;charset=utf-8," + java.net.URLEncoder.encode(text, java.nio.charset.StandardCharsets.UTF_8),
      "ext", "txt"
    );
  }

  private void ensureAssigneeColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_feedback", "assignee")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_feedback add column assignee varchar(128) not null default ''");
      }
      return null;
    });
  }

  private void ensureAvatarColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_user", "avatar_url")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_user add column avatar_url text");
      }
      return null;
    });
  }

  private void ensureCategoryColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_feedback", "category")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_feedback add column category varchar(64)");
      }
      return null;
    });
  }

  private void ensurePriorityColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_feedback", "priority")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_feedback add column priority varchar(32) not null default 'MEDIUM'");
      }
      return null;
    });
  }

  private void ensureEmotionColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_feedback", "emotion")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_feedback add column emotion varchar(32)");
      }
      return null;
    });
  }

  private void ensureKnowledgeDocumentTable() {
    jdbcTemplate.execute(
      """
      create table if not exists wo_knowledge_document (
        id varchar(36) primary key,
        title varchar(255) not null,
        file_name varchar(255) not null,
        file_ext varchar(32) not null,
        file_size bigint not null,
        content_md5 varchar(32) not null unique,
        storage_path varchar(500) not null,
        created_by varchar(64) not null,
        status varchar(32) not null,
        created_at varchar(19) not null,
        updated_at varchar(19) not null
      )
      """
    );
  }

  private void ensureUserServiceGroupColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_user", "service_group")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_user add column service_group varchar(32) not null default ''");
      }
      return null;
    });
  }

  private void backfillUserServiceGroups() {
    jdbcTemplate.update(
      "update wo_user set service_group = ? where role = 'ADMIN' and (service_group is null or service_group = '')",
      ServiceGroup.PRODUCT_CONSULTING.name()
    );
  }

  private void ensureServiceGroupColumn() {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, "wo_feedback", "service_group")) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table wo_feedback add column service_group varchar(32) not null default 'PRODUCT_CONSULTING'");
      }
      return null;
    });
  }

  private void backfillServiceGroups() {
    jdbcTemplate.update(
      """
      update wo_feedback
      set service_group = case
        when category = ? then ?
        when category = ? then ?
        when category = ? then ?
        else ?
      end
      """,
      TicketCategory.技术故障.name(), ServiceGroup.TECH_SUPPORT.name(),
      TicketCategory.账单问题.name(), ServiceGroup.BILLING_SERVICE.name(),
      TicketCategory.退款售后.name(), ServiceGroup.AFTER_SALES.name(),
      ServiceGroup.PRODUCT_CONSULTING.name()
    );
  }

  private void ensureCommerceRefundTables() {
    jdbcTemplate.execute(
      """
      create table if not exists ec_order (
        id varchar(36) primary key,
        order_no varchar(64) not null,
        owner_username varchar(64) not null,
        status varchar(32) not null,
        total_amount decimal(12,2) not null,
        discount_amount decimal(12,2) not null default 0,
        paid_amount decimal(12,2) not null,
        paid_at varchar(19) not null default '',
        created_at varchar(19) not null,
        updated_at varchar(19) not null,
        unique key uk_ec_order_no (order_no)
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_order_item (
        id varchar(36) primary key,
        order_id varchar(36) not null,
        product_name varchar(255) not null,
        sku_name varchar(255) not null default '',
        quantity int not null,
        unit_price decimal(12,2) not null,
        discount_share decimal(12,2) not null default 0,
        paid_amount decimal(12,2) not null,
        returnable tinyint not null default 1,
        key idx_order_item_order (order_id)
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_payment (
        id varchar(36) primary key,
        order_id varchar(36) not null unique,
        channel varchar(32) not null,
        transaction_no varchar(128) not null,
        paid_amount decimal(12,2) not null,
        refunded_amount decimal(12,2) not null default 0,
        status varchar(32) not null
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_shipment (
        id varchar(36) primary key,
        order_id varchar(36) not null unique,
        status varchar(32) not null,
        tracking_no varchar(128) not null default '',
        shipped_at varchar(19) not null default '',
        delivered_at varchar(19) not null default ''
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_refund_policy (
        id varchar(36) primary key,
        code varchar(64) not null unique,
        title varchar(255) not null,
        content text not null,
        refund_type varchar(32) not null,
        active tinyint not null default 1,
        updated_at varchar(19) not null
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_refund_request (
        id varchar(36) primary key,
        refund_no varchar(64) not null unique,
        ticket_id varchar(36) not null,
        order_id varchar(36) not null,
        owner_username varchar(64) not null,
        refund_type varchar(32) not null,
        reason text not null,
        requested_item_ids_json text not null,
        calculated_amount decimal(12,2) not null,
        eligibility_code varchar(64) not null,
        eligibility_reason text not null,
        agent_plan_json text not null,
        policy_sources_json text not null,
        review_status varchar(32) not null,
        execution_status varchar(32) not null,
        reviewed_by varchar(64) not null default '',
        review_comment text not null,
        idempotency_key varchar(128) not null,
        version int not null default 1,
        created_at varchar(19) not null,
        updated_at varchar(19) not null,
        unique key uk_refund_idempotency (idempotency_key),
        key idx_refund_ticket (ticket_id),
        key idx_refund_order (order_id)
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_refund_audit (
        id varchar(36) primary key,
        refund_request_id varchar(36) not null,
        event_type varchar(64) not null,
        operator_type varchar(32) not null,
        operator_id varchar(64) not null,
        summary varchar(500) not null,
        created_at varchar(19) not null,
        key idx_refund_audit_request (refund_request_id)
      )
      """
    );
  }

  private void ensureCatalogTables() {
    jdbcTemplate.execute(
      """
      create table if not exists ec_product (
        id varchar(36) primary key,
        name varchar(128) not null,
        category varchar(64) not null,
        summary varchar(500) not null,
        image_url varchar(500) not null,
        active tinyint not null default 1,
        created_at varchar(19) not null,
        updated_at varchar(19) not null
      )
      """
    );
    jdbcTemplate.execute(
      """
      create table if not exists ec_product_sku (
        id varchar(36) primary key,
        product_id varchar(36) not null,
        sku_name varchar(128) not null,
        price decimal(12,2) not null,
        stock int not null default 0,
        attributes_json text not null,
        active tinyint not null default 1,
        updated_at varchar(19) not null,
        key idx_product_sku_product (product_id)
      )
      """
    );
  }

  private void seedCatalog() throws Exception {
    seedCatalogProduct(
      "product-s1", "sku-s1-white", "净巡 S1 Lite", "云白标准版", "1299.00", 30,
      "适合小户型的轻量扫拖基础款，操作直接，日常维护简单。", "/products/jingxun-s1-lite.png",
      Map.ofEntries(
        Map.entry("home_size_max", 80),
        Map.entry("floor_types", List.of("木地板", "瓷砖")),
        Map.entry("pet_friendly", false),
        Map.entry("suction_pa", 3500),
        Map.entry("runtime_minutes", 90),
        Map.entry("navigation", "激光导航"),
        Map.entry("obstacle_avoidance", "红外避障"),
        Map.entry("mop_lift", false),
        Map.entry("anti_tangle", false),
        Map.entry("station_type", "无"),
        Map.entry("noise_db", 58)
      )
    );
    seedCatalogProduct(
      "product-p2", "sku-p2-gray", "净巡 P2 Pet", "雾灰宠物版", "2299.00", 20,
      "面向养宠家庭的防缠绕机型，兼顾木地板与短毛地毯清洁。", "/products/jingxun-p2-pet.png",
      Map.ofEntries(
        Map.entry("home_size_max", 120),
        Map.entry("floor_types", List.of("木地板", "瓷砖", "短毛地毯")),
        Map.entry("pet_friendly", true),
        Map.entry("suction_pa", 5500),
        Map.entry("runtime_minutes", 150),
        Map.entry("navigation", "激光导航"),
        Map.entry("obstacle_avoidance", "3D结构光"),
        Map.entry("mop_lift", true),
        Map.entry("anti_tangle", true),
        Map.entry("station_type", "自动集尘"),
        Map.entry("noise_db", 56)
      )
    );
    seedCatalogProduct(
      "product-m3", "sku-m3-white", "净巡 M3 Station", "曜白基站版", "3299.00", 12,
      "带自动集尘、洗拖布和热风烘干的进阶基站款。", "/products/jingxun-m3-station.png",
      Map.ofEntries(
        Map.entry("home_size_max", 150),
        Map.entry("floor_types", List.of("木地板", "瓷砖", "短毛地毯")),
        Map.entry("pet_friendly", true),
        Map.entry("suction_pa", 6500),
        Map.entry("runtime_minutes", 180),
        Map.entry("navigation", "激光导航"),
        Map.entry("obstacle_avoidance", "AI视觉避障"),
        Map.entry("mop_lift", true),
        Map.entry("anti_tangle", true),
        Map.entry("station_type", "集尘洗拖烘干基站"),
        Map.entry("noise_db", 54)
      )
    );
    seedCatalogProduct(
      "product-x4", "sku-x4-black", "净巡 X4 Max", "深空黑旗舰版", "4599.00", 8,
      "覆盖大户型和地毯场景的旗舰全能款，续航和避障能力更强。", "/products/jingxun-x4-max.png",
      Map.ofEntries(
        Map.entry("home_size_max", 220),
        Map.entry("floor_types", List.of("木地板", "瓷砖", "短毛地毯", "地毯")),
        Map.entry("pet_friendly", true),
        Map.entry("suction_pa", 8000),
        Map.entry("runtime_minutes", 220),
        Map.entry("navigation", "双线激光导航"),
        Map.entry("obstacle_avoidance", "3D结构光避障"),
        Map.entry("mop_lift", true),
        Map.entry("anti_tangle", true),
        Map.entry("station_type", "全能自清洁基站"),
        Map.entry("noise_db", 52)
      )
    );
  }

  private void seedCatalogProduct(
    String productId, String skuId, String name, String skuName, String price, int stock,
    String summary, String imageUrl, Map<String, Object> attributes
  ) throws Exception {
    String now = now();
    jdbcTemplate.update(
      "insert ignore into ec_product (id, name, category, summary, image_url, active, created_at, updated_at) values (?, ?, '扫拖机器人', ?, ?, 1, ?, ?)",
      productId, name, summary, imageUrl, now, now
    );
    jdbcTemplate.update(
      "insert ignore into ec_product_sku (id, product_id, sku_name, price, stock, attributes_json, active, updated_at) values (?, ?, ?, ?, ?, ?, 1, ?)",
      skuId, productId, skuName, price, stock, objectMapper.writeValueAsString(attributes), now
    );
  }

  private void seedCommerceOrders() {
    String now = now();
    String recentDelivery = LocalDateTime.now().minusDays(1).format(FMT);
    String oldDelivery = LocalDateTime.now().minusDays(10).format(FMT);

    seedCommerceOrder("order-1004-paid", "ORD-1004-PAID", "1004", "PAID", "399.00", "NOT_SHIPPED", "", true, "扫拖一体机器人", now);
    seedCommerceOrder("order-1004-shipped", "ORD-1004-SHIPPED", "1004", "PAID", "699.00", "SHIPPED", "", true, "无线吸尘器", now);
    seedCommerceOrder("order-1004-new", "ORD-1004-DELIVERED", "1004", "DELIVERED", "1299.00", "DELIVERED", recentDelivery, true, "智能洗地机", now);
    seedCommerceOrder("order-1004-old", "ORD-1004-EXPIRED", "1004", "DELIVERED", "199.00", "DELIVERED", oldDelivery, true, "清洁耗材套装", now);
    seedCommerceOrder("order-other", "ORD-OTHER-USER", "other", "PAID", "299.00", "NOT_SHIPPED", "", true, "除螨仪", now);
    // demo 账号使用同样的两条核心路径，方便直接从前端体验。
    seedCommerceOrder("order-user-paid", "ORD-USER-PAID", "user", "PAID", "399.00", "NOT_SHIPPED", "", true, "扫拖一体机器人", now);
    seedCommerceOrder("order-user-delivered", "ORD-USER-DELIVERED", "user", "DELIVERED", "1299.00", "DELIVERED", recentDelivery, true, "智能洗地机", now);

    jdbcTemplate.update(
      "insert ignore into ec_refund_policy (id, code, title, content, refund_type, active, updated_at) values (?, ?, ?, ?, ?, ?, ?)",
      "policy-unshipped", "UNSHIPPED_STANDARD", "未发货订单退款", "已支付且未发货的订单可申请整单退款。", "UNSHIPPED_REFUND", 1, now
    );
    jdbcTemplate.update(
      "insert ignore into ec_refund_policy (id, code, title, content, refund_type, active, updated_at) values (?, ?, ?, ?, ?, ?, ?)",
      "policy-return", "RETURN_7_DAYS", "七天退货退款", "已签收且不超过七天、商品支持退货时可申请整单退货退款。", "RETURN_REFUND", 1, now
    );
    jdbcTemplate.update(
      "insert ignore into ec_refund_policy (id, code, title, content, refund_type, active, updated_at) values (?, ?, ?, ?, ?, ?, ?)",
      "policy-non-return", "NON_RETURNABLE", "不可退商品说明", "标记为不可退的商品不支持退货退款。", "RETURN_REFUND", 1, now
    );
  }

  private void seedCommerceOrder(
    String id, String orderNo, String owner, String orderStatus, String amount,
    String shipmentStatus, String deliveredAt, boolean returnable, String productName, String now
  ) {
    jdbcTemplate.update(
      "insert ignore into ec_order (id, order_no, owner_username, status, total_amount, discount_amount, paid_amount, paid_at, created_at, updated_at) values (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
      id, orderNo, owner, orderStatus, amount, amount, now, now, now
    );
    jdbcTemplate.update(
      "insert ignore into ec_order_item (id, order_id, product_name, sku_name, quantity, unit_price, discount_share, paid_amount, returnable) values (?, ?, ?, ?, 1, ?, 0, ?, ?)",
      id + "-item", id, productName, "标准版", amount, amount, returnable ? 1 : 0
    );
    jdbcTemplate.update(
      "insert ignore into ec_payment (id, order_id, channel, transaction_no, paid_amount, refunded_amount, status) values (?, ?, 'MOCK', ?, ?, 0, 'PAID')",
      id + "-payment", id, "TX-" + orderNo, amount
    );
    jdbcTemplate.update(
      "insert ignore into ec_shipment (id, order_id, status, tracking_no, shipped_at, delivered_at) values (?, ?, ?, ?, ?, ?)",
      id + "-shipment", id, shipmentStatus, shipmentStatus.equals("NOT_SHIPPED") ? "" : "TRACK-" + orderNo,
      shipmentStatus.equals("NOT_SHIPPED") ? "" : now, deliveredAt
    );
  }

  private void ensureCaseMemoryTable() {
    jdbcTemplate.execute(
      """
      create table if not exists wo_case_memory (
        id varchar(36) primary key,
        ticket_id varchar(36) not null unique,
        ticket_code varchar(32) not null,
        title varchar(200) not null,
        problem_text text not null,
        final_reply text not null,
        status varchar(32) not null,
        vector_id varchar(36) not null unique,
        created_at varchar(19) not null,
        updated_at varchar(19) not null
      )
      """
    );
    ensureColumn("wo_case_memory", "problem_summary", "text");
    ensureColumn("wo_case_memory", "confirmed_facts_json", "text");
    ensureColumn("wo_case_memory", "resolution_steps_json", "text");
    ensureColumn("wo_case_memory", "resolution_result", "varchar(64) not null default ''");
    ensureColumn("wo_case_memory", "category", "varchar(64) not null default ''");
    ensureColumn("wo_case_memory", "quality_score", "double not null default 0.8");
    ensureColumn("wo_case_memory", "active", "tinyint not null default 1");
    ensureColumn("wo_case_memory", "memory_version", "int not null default 1");
    ensureColumn("wo_case_memory", "embedding_model", "varchar(128) not null default ''");
    ensureColumn("wo_case_memory", "vector_sync_status", "varchar(32) not null default 'PENDING'");
    ensureColumn("wo_case_memory", "solved_at", "varchar(19) not null default ''");
    jdbcTemplate.update("update wo_case_memory set problem_summary=problem_text where problem_summary is null or problem_summary='' ");
    jdbcTemplate.update("update wo_case_memory set confirmed_facts_json='[]' where confirmed_facts_json is null");
    jdbcTemplate.update("update wo_case_memory set resolution_steps_json='[]' where resolution_steps_json is null");
  }

  private void ensureTicketMemoryTable() {
    jdbcTemplate.execute(
      """
      create table if not exists wo_ticket_memory (
        ticket_id varchar(36) primary key,
        history_cursor varchar(128) not null default '',
        summary text not null,
        confirmed_facts_json text not null,
        attempted_steps_json text not null,
        unresolved_json text not null,
        version int not null default 1,
        created_at varchar(19) not null,
        updated_at varchar(19) not null
      )
      """
    );
  }

  private void ensureUserMemoryTable() {
    jdbcTemplate.execute(
      """
      create table if not exists wo_user_memory_item (
        id varchar(36) primary key,
        owner_username varchar(64) not null,
        memory_type varchar(32) not null,
        memory_key varchar(64) not null,
        memory_value text not null,
        source_type varchar(32) not null,
        source_id varchar(128) not null default '',
        source_reply_id varchar(36) not null default '',
        extraction_batch_id varchar(128) not null,
        confidence double not null,
        importance double not null,
        status varchar(32) not null,
        valid_from varchar(19) not null,
        expires_at varchar(19),
        last_confirmed_at varchar(19) not null,
        superseded_by varchar(36) not null default '',
        version int not null default 1,
        created_at varchar(19) not null,
        updated_at varchar(19) not null,
        unique key uk_user_memory_source (owner_username, memory_key, source_reply_id, extraction_batch_id),
        key idx_user_memory_active (owner_username, status, memory_key)
      )
      """
    );
  }

  private void ensureAssistantTables() {
    jdbcTemplate.execute(
      """
      create table if not exists wo_assistant_session (
        id varchar(36) primary key,
        owner_username varchar(64) not null,
        status varchar(32) not null,
        route varchar(64) not null default '',
        summary text not null,
        pending_ticket_draft_json text not null,
        presale_state_json text not null,
        ticket_id varchar(36) not null default '',
        deleted tinyint not null default 0,
        deleted_at varchar(19) not null default '',
        created_at varchar(19) not null,
        updated_at varchar(19) not null,
        key idx_assistant_session_owner (owner_username, updated_at)
      )
      """
    );
    // 兼容不允许 TEXT 默认值的 MySQL 版本：先加列，再为已有会话回填空状态。
    ensureColumn("wo_assistant_session", "presale_state_json", "text");
    ensureColumn("wo_assistant_session", "deleted", "tinyint not null default 0");
    ensureColumn("wo_assistant_session", "deleted_at", "varchar(19) not null default ''");
    jdbcTemplate.update(
      "update wo_assistant_session set presale_state_json='{}' where presale_state_json is null or presale_state_json=''"
    );
    jdbcTemplate.execute(
      """
      create table if not exists wo_assistant_message (
        id varchar(36) primary key,
        session_id varchar(36) not null,
        role varchar(32) not null,
        content text not null,
        action varchar(32) not null default '',
        metadata_json text not null,
        created_at varchar(19) not null,
        key idx_assistant_message_session (session_id, created_at)
      )
      """
    );
  }

  private void ensureColumn(String tableName, String columnName, String definition) {
    jdbcTemplate.execute((Connection connection) -> {
      DatabaseMetaData metaData = connection.getMetaData();
      try (ResultSet columns = metaData.getColumns(connection.getCatalog(), null, tableName, columnName)) {
        if (columns.next()) {
          return null;
        }
      }
      try (Statement statement = connection.createStatement()) {
        statement.execute("alter table " + tableName + " add column " + columnName + " " + definition);
      }
      return null;
    });
  }

  private static String now() {
    return LocalDateTime.now().format(FMT);
  }
}
