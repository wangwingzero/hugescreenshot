"""
设备管理器测试

Feature: subscription-system
Property 3: Device limit enforcement by plan
Validates: Requirements 3.1, 3.2, 3.4, 3.5
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from hypothesis import given, strategies as st, assume

from screenshot_tool.core.device_manager import DeviceManager, DeviceInfo


class TestMachineId:
    """设备指纹测试"""
    
    def test_machine_id_is_consistent(self):
        """测试设备指纹一致性"""
        with patch('screenshot_tool.core.device_manager.uuid.getnode', return_value=123456789):
            with patch('screenshot_tool.core.device_manager.platform.node', return_value='test-host'):
                with patch('screenshot_tool.core.device_manager.platform.processor', return_value='Intel'):
                    with patch('screenshot_tool.core.device_manager.platform.machine', return_value='AMD64'):
                        mock_client = MagicMock()
                        manager = DeviceManager(mock_client, "user-123")
                        
                        id1 = manager.get_machine_id()
                        id2 = manager.get_machine_id()
                        
                        assert id1 == id2
                        assert len(id1) == 64  # SHA256 hex
    
    def test_machine_id_is_hex(self):
        """测试设备指纹是十六进制字符串"""
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        machine_id = manager.get_machine_id()
        
        # 应该是有效的十六进制字符串
        int(machine_id, 16)  # 不抛异常说明是有效的十六进制


class TestDeviceLimitEnforcement:
    """设备限制测试
    
    Property 3: Device limit enforcement by plan
    """
    
    @given(
        active_count=st.integers(min_value=0, max_value=10),
        is_vip=st.booleans(),
    )
    def test_device_limit_by_plan_property(self, active_count: int, is_vip: bool):
        """Property 3: 设备限制按计划执行
        
        Feature: subscription-system, Property 3: Device limit enforcement by plan
        Validates: Requirements 3.2, 3.4
        
        - 免费用户限制 2 台设备
        - VIP 用户限制 3 台设备
        """
        limit = DeviceManager.VIP_DEVICE_LIMIT if is_vip else DeviceManager.FREE_DEVICE_LIMIT
        
        # 模拟已激活设备
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        # 模拟当前设备未激活
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        # 模拟已激活设备数量
        active_devices = [
            {"id": f"dev-{i}", "user_id": "user-123", "machine_id": f"machine-{i}",
             "device_name": f"Device {i}", "os_version": "Windows 10",
             "app_version": "1.0.0", "is_active": True}
            for i in range(active_count)
        ]
        
        # 设置 mock 返回值
        def mock_select(*args):
            mock_result = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()
            
            # 第一次调用检查当前设备
            mock_eq2.execute.return_value = MagicMock(data=[])
            mock_eq1.eq.return_value = mock_eq2
            mock_result.eq.return_value = mock_eq1
            
            return mock_result
        
        # 使用 patch 模拟 get_active_devices
        with patch.object(manager, 'get_active_devices') as mock_get_active:
            mock_get_active.return_value = [
                DeviceInfo(
                    id=f"dev-{i}", user_id="user-123", machine_id=f"machine-{i}",
                    device_name=f"Device {i}", os_version="Windows 10",
                    app_version="1.0.0", is_active=True
                )
                for i in range(active_count)
            ]
            
            can_activate, message = manager.can_activate(is_vip=is_vip)
            
            # 验证限制逻辑
            if active_count >= limit:
                assert can_activate is False
                assert "设备上限" in message
            else:
                assert can_activate is True
    
    def test_free_user_limit_is_2(self):
        """测试免费用户设备限制为 2"""
        assert DeviceManager.FREE_DEVICE_LIMIT == 2
    
    def test_vip_user_limit_is_3(self):
        """测试 VIP 用户设备限制为 3"""
        assert DeviceManager.VIP_DEVICE_LIMIT == 3


class TestDeviceActivation:
    """设备激活测试"""
    
    def test_activate_new_device(self):
        """测试激活新设备"""
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        # 模拟设备不存在
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        # 模拟插入成功
        mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock()
        
        with patch('screenshot_tool.core.device_manager.platform.node', return_value='test-host'):
            with patch('screenshot_tool.core.device_manager.platform.system', return_value='Windows'):
                with patch('screenshot_tool.core.device_manager.platform.release', return_value='10'):
                    success, message = manager.activate_device()
        
        assert success is True
        assert "激活" in message
    
    def test_reactivate_existing_device(self):
        """测试重新激活已存在的设备"""
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        # 模拟设备已存在
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "dev-123", "is_active": False}]
        )
        
        # 模拟更新成功
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        
        with patch('screenshot_tool.core.device_manager.platform.node', return_value='test-host'):
            with patch('screenshot_tool.core.device_manager.platform.system', return_value='Windows'):
                with patch('screenshot_tool.core.device_manager.platform.release', return_value='10'):
                    success, message = manager.activate_device()
        
        assert success is True
        assert "激活" in message


class TestDeviceDeactivation:
    """设备停用测试"""
    
    def test_deactivate_own_device(self):
        """测试停用自己的设备"""
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        # 模拟设备存在且属于当前用户
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "dev-123"}]
        )
        
        # 模拟更新成功
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        
        success, message = manager.deactivate_device("dev-123")
        
        assert success is True
        assert "停用" in message
    
    def test_deactivate_nonexistent_device(self):
        """测试停用不存在的设备"""
        mock_client = MagicMock()
        manager = DeviceManager(mock_client, "user-123")
        
        # 模拟设备不存在
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        success, message = manager.deactivate_device("dev-999")
        
        assert success is False
        assert "不存在" in message or "无权" in message


class TestDeviceInfo:
    """DeviceInfo 数据类测试"""
    
    def test_device_info_creation(self):
        """测试 DeviceInfo 创建"""
        device = DeviceInfo(
            id="dev-123",
            user_id="user-123",
            machine_id="abc123",
            device_name="My PC",
            os_version="Windows 10",
            app_version="1.0.0",
            is_active=True,
        )
        
        assert device.id == "dev-123"
        assert device.user_id == "user-123"
        assert device.machine_id == "abc123"
        assert device.device_name == "My PC"
        assert device.is_active is True
        assert device.last_seen is None
        assert device.created_at is None
