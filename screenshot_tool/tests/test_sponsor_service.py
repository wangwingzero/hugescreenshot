"""
赞助服务属性测试

测试 SponsorService 的核心功能：
- custom_order_id round-trip
- 赞助链接包含用户 ID
- API 签名生成
"""

import hashlib
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck

from screenshot_tool.services.subscription.sponsor_service import (
    SponsorService,
    Order,
    OrderStatus,
    OrderVerifyResult,
)

# 属性测试通用设置：允许使用 function-scoped fixture
PROPERTY_SETTINGS = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)


# ============================================================================
# Strategies
# ============================================================================

# UUID 格式的用户 ID
uuid_strategy = st.uuids().map(str)

# 合理的时间戳范围（2020-2030）
timestamp_strategy = st.integers(min_value=1577836800, max_value=1893456000)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_auth_service():
    """创建模拟的 AuthService"""
    auth = MagicMock()
    auth.get_current_user.return_value = None
    return auth


@pytest.fixture
def sponsor_service(mock_auth_service):
    """创建 SponsorService 实例"""
    return SponsorService(mock_auth_service)


@pytest.fixture
def sponsor_service_with_token(mock_auth_service):
    """创建带 token 的 SponsorService 实例"""
    return SponsorService(mock_auth_service, afdian_token="test_token_12345")


# ============================================================================
# Property Tests: Task 4.2 - custom_order_id round-trip
# ============================================================================

class TestCustomOrderIdRoundTrip:
    """测试 custom_order_id 的创建和解析"""
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_roundtrip_preserves_user_id(self, mock_auth_service, user_id: str):
        """Property 1: create -> parse 应该保留 user_id"""
        service = SponsorService(mock_auth_service)
        
        custom_order_id = service.create_custom_order_id(user_id)
        parsed_user_id, parsed_ts = service.parse_custom_order_id(custom_order_id)
        
        assert parsed_user_id == user_id
        assert parsed_ts is not None
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_timestamp_is_recent(self, mock_auth_service, user_id: str):
        """Property 2: 生成的时间戳应该是当前时间附近"""
        service = SponsorService(mock_auth_service)
        
        before = int(time.time())
        custom_order_id = service.create_custom_order_id(user_id)
        after = int(time.time())
        
        _, parsed_ts = service.parse_custom_order_id(custom_order_id)
        
        assert before <= parsed_ts <= after
    
    @given(user_id=uuid_strategy, ts=timestamp_strategy)
    @PROPERTY_SETTINGS
    def test_format_is_correct(self, mock_auth_service, user_id: str, ts: int):
        """Property 3: custom_order_id 格式应该是 user_id:timestamp"""
        service = SponsorService(mock_auth_service)
        
        # 手动构造 custom_order_id
        custom_order_id = f"{user_id}:{ts}"
        parsed_user_id, parsed_ts = service.parse_custom_order_id(custom_order_id)
        
        assert parsed_user_id == user_id
        assert parsed_ts == ts
    
    def test_parse_invalid_format_returns_none(self, sponsor_service):
        """解析无效格式应返回 (None, None)"""
        # 空字符串
        assert sponsor_service.parse_custom_order_id("") == (None, None)
        
        # 没有冒号
        assert sponsor_service.parse_custom_order_id("abc123") == (None, None)
        
        # 多个冒号
        assert sponsor_service.parse_custom_order_id("a:b:c") == (None, None)
        
        # 时间戳不是数字
        assert sponsor_service.parse_custom_order_id("user:abc") == (None, None)
    
    def test_parse_none_returns_none(self, sponsor_service):
        """解析 None 应返回 (None, None)"""
        assert sponsor_service.parse_custom_order_id(None) == (None, None)


# ============================================================================
# Property Tests: Task 4.3 - 赞助链接包含用户 ID
# ============================================================================

class TestSponsorUrlGeneration:
    """测试赞助链接生成"""
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_url_contains_user_id(self, mock_auth_service, user_id: str):
        """Property 1: 生成的 URL 应该包含 user_id"""
        service = SponsorService(mock_auth_service)
        
        url = service.generate_sponsor_url(user_id)
        
        # URL 应该包含 user_id（在 custom_order_id 参数中）
        assert user_id in url
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_url_contains_plan_id(self, mock_auth_service, user_id: str):
        """Property 2: 生成的 URL 应该包含 plan_id"""
        service = SponsorService(mock_auth_service)
        
        url = service.generate_sponsor_url(user_id)
        
        assert SponsorService.PLAN_ID in url
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_url_contains_sku_id(self, mock_auth_service, user_id: str):
        """Property 3: 生成的 URL 应该包含 sku_id"""
        service = SponsorService(mock_auth_service)
        
        url = service.generate_sponsor_url(user_id)
        
        assert SponsorService.SKU_ID in url
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_url_is_valid_afdian_url(self, mock_auth_service, user_id: str):
        """Property 4: 生成的 URL 应该是有效的爱发电订单 URL"""
        service = SponsorService(mock_auth_service)
        
        url = service.generate_sponsor_url(user_id)
        
        assert url.startswith(SponsorService.AFDIAN_ORDER_URL)
        assert "product_type=1" in url
        assert "custom_order_id=" in url
    
    @given(user_id=uuid_strategy)
    @PROPERTY_SETTINGS
    def test_custom_order_id_in_url_is_parseable(self, mock_auth_service, user_id: str):
        """Property 5: URL 中的 custom_order_id 应该可以被解析"""
        import urllib.parse
        
        service = SponsorService(mock_auth_service)
        url = service.generate_sponsor_url(user_id)
        
        # 解析 URL 参数
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        
        custom_order_id = params.get("custom_order_id", [None])[0]
        assert custom_order_id is not None
        
        parsed_user_id, parsed_ts = service.parse_custom_order_id(custom_order_id)
        assert parsed_user_id == user_id
        assert parsed_ts is not None


# ============================================================================
# Property Tests: Task 4.4 - API 签名生成
# ============================================================================

class TestApiSignatureGeneration:
    """测试 API 签名生成"""
    
    @given(
        page=st.integers(min_value=1, max_value=100),
        ts=timestamp_strategy
    )
    @PROPERTY_SETTINGS
    def test_sign_is_32_char_hex(self, mock_auth_service, page: int, ts: int):
        """Property 1: 签名应该是 32 字符的十六进制字符串"""
        service = SponsorService(mock_auth_service, afdian_token="test_token")
        
        params = {"page": page}
        sign = service.generate_sign(params, ts)
        
        assert len(sign) == 32
        assert all(c in "0123456789abcdef" for c in sign)
    
    @given(
        page=st.integers(min_value=1, max_value=100),
        ts=timestamp_strategy
    )
    @PROPERTY_SETTINGS
    def test_same_input_same_sign(self, mock_auth_service, page: int, ts: int):
        """Property 2: 相同输入应该产生相同签名"""
        service = SponsorService(mock_auth_service, afdian_token="test_token")
        
        params = {"page": page}
        sign1 = service.generate_sign(params, ts)
        sign2 = service.generate_sign(params, ts)
        
        assert sign1 == sign2
    
    @given(
        page1=st.integers(min_value=1, max_value=100),
        page2=st.integers(min_value=1, max_value=100),
        ts=timestamp_strategy
    )
    @PROPERTY_SETTINGS
    def test_different_params_different_sign(self, mock_auth_service, page1: int, page2: int, ts: int):
        """Property 3: 不同参数应该产生不同签名"""
        assume(page1 != page2)
        
        service = SponsorService(mock_auth_service, afdian_token="test_token")
        
        sign1 = service.generate_sign({"page": page1}, ts)
        sign2 = service.generate_sign({"page": page2}, ts)
        
        assert sign1 != sign2
    
    @given(
        page=st.integers(min_value=1, max_value=100),
        ts1=timestamp_strategy,
        ts2=timestamp_strategy
    )
    @PROPERTY_SETTINGS
    def test_different_ts_different_sign(self, mock_auth_service, page: int, ts1: int, ts2: int):
        """Property 4: 不同时间戳应该产生不同签名"""
        assume(ts1 != ts2)
        
        service = SponsorService(mock_auth_service, afdian_token="test_token")
        
        params = {"page": page}
        sign1 = service.generate_sign(params, ts1)
        sign2 = service.generate_sign(params, ts2)
        
        assert sign1 != sign2
    
    def test_sign_matches_expected_format(self, mock_auth_service):
        """测试签名计算是否符合爱发电文档规范"""
        token = "test_token_12345"
        service = SponsorService(mock_auth_service, afdian_token=token)
        
        params = {"page": 1}
        ts = 1700000000
        
        # 手动计算预期签名
        params_json = json.dumps(params, separators=(',', ':'))
        sign_str = f"{token}params{params_json}ts{ts}user_id{SponsorService.AFDIAN_USER_ID}"
        expected_sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        actual_sign = service.generate_sign(params, ts)
        
        assert actual_sign == expected_sign
    
    def test_sign_without_token_raises_error(self, sponsor_service):
        """没有 token 时生成签名应该抛出异常"""
        with pytest.raises(ValueError, match="Token not configured"):
            sponsor_service.generate_sign({"page": 1}, 1700000000)


# ============================================================================
# Unit Tests: 其他功能
# ============================================================================

class TestSponsorServiceMisc:
    """其他功能测试"""
    
    def test_get_current_user_id_when_logged_in(self, mock_auth_service):
        """登录时应返回用户 ID"""
        mock_user = MagicMock()
        mock_user.id = "test-user-id-123"
        mock_auth_service.get_current_user.return_value = mock_user
        
        service = SponsorService(mock_auth_service)
        
        assert service.get_current_user_id() == "test-user-id-123"
    
    def test_get_current_user_id_when_not_logged_in(self, sponsor_service):
        """未登录时应返回 None"""
        assert sponsor_service.get_current_user_id() is None
    
    def test_is_logged_in_true(self, mock_auth_service):
        """登录时 is_logged_in 应返回 True"""
        mock_auth_service.get_current_user.return_value = MagicMock()
        
        service = SponsorService(mock_auth_service)
        
        assert service.is_logged_in() is True
    
    def test_is_logged_in_false(self, sponsor_service):
        """未登录时 is_logged_in 应返回 False"""
        assert sponsor_service.is_logged_in() is False
    
    def test_order_dataclass(self):
        """测试 Order 数据类"""
        order = Order(
            id="order-1",
            user_id="user-1",
            afdian_order_id="afd-123",
            amount=9.9,
            status=OrderStatus.PAID,
        )
        
        assert order.id == "order-1"
        assert order.user_id == "user-1"
        assert order.afdian_order_id == "afd-123"
        assert order.amount == 9.9
        assert order.status == OrderStatus.PAID
    
    def test_order_verify_result_success(self):
        """测试成功的验证结果"""
        order = Order(
            id="1",
            user_id="user-1",
            afdian_order_id="afd-123",
            amount=9.9,
            status=OrderStatus.PAID,
        )
        result = OrderVerifyResult(success=True, message="OK", order=order)
        
        assert result.success is True
        assert result.order is not None
    
    def test_order_verify_result_failure(self):
        """测试失败的验证结果"""
        result = OrderVerifyResult(success=False, message="订单不存在")
        
        assert result.success is False
        assert result.order is None


class TestVerifyOrder:
    """测试订单验证"""
    
    def test_verify_without_token(self, sponsor_service):
        """没有 token 时验证应返回失败"""
        result = sponsor_service.verify_order("test-order-id")
        
        assert result.success is False
        assert "Token" in result.message
    
    @patch('screenshot_tool.services.subscription.sponsor_service.requests.post')
    def test_verify_order_success(self, mock_post, sponsor_service_with_token):
        """成功验证订单"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ec": 200,
            "data": {
                "list": [{
                    "out_trade_no": "afd-123",
                    "status": 2,
                    "total_amount": "9.90",
                    "user_id": "afdian-user-1",
                    "custom_order_id": "supabase-user-1:1700000000",
                }]
            }
        }
        mock_post.return_value = mock_response
        
        result = sponsor_service_with_token.verify_order("afd-123")
        
        assert result.success is True
        assert result.order is not None
        assert result.order.afdian_order_id == "afd-123"
        assert result.order.user_id == "supabase-user-1"
    
    @patch('screenshot_tool.services.subscription.sponsor_service.requests.post')
    def test_verify_order_not_found(self, mock_post, sponsor_service_with_token):
        """订单不存在"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ec": 200,
            "data": {"list": []}
        }
        mock_post.return_value = mock_response
        
        result = sponsor_service_with_token.verify_order("nonexistent")
        
        assert result.success is False
        assert "不存在" in result.message
    
    @patch('screenshot_tool.services.subscription.sponsor_service.requests.post')
    def test_verify_order_not_paid(self, mock_post, sponsor_service_with_token):
        """订单未支付"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ec": 200,
            "data": {
                "list": [{
                    "out_trade_no": "afd-123",
                    "status": 1,  # 未支付
                }]
            }
        }
        mock_post.return_value = mock_response
        
        result = sponsor_service_with_token.verify_order("afd-123")
        
        assert result.success is False
        assert "未支付" in result.message


class TestQueryOrders:
    """测试订单查询"""
    
    def test_query_without_token(self, sponsor_service):
        """没有 token 时查询应抛出异常"""
        with pytest.raises(ValueError, match="Token not configured"):
            sponsor_service.query_orders()
    
    @patch('screenshot_tool.services.subscription.sponsor_service.requests.post')
    def test_query_orders_success(self, mock_post, sponsor_service_with_token):
        """成功查询订单"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ec": 200,
            "data": {
                "list": [
                    {"out_trade_no": "order-1"},
                    {"out_trade_no": "order-2"},
                ]
            }
        }
        mock_post.return_value = mock_response
        
        orders = sponsor_service_with_token.query_orders(page=1)
        
        assert len(orders) == 2
        assert orders[0]["out_trade_no"] == "order-1"
    
    @patch('screenshot_tool.services.subscription.sponsor_service.requests.post')
    def test_query_orders_api_error(self, mock_post, sponsor_service_with_token):
        """API 错误时返回空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ec": 400, "em": "error"}
        mock_post.return_value = mock_response
        
        orders = sponsor_service_with_token.query_orders()
        
        assert orders == []
