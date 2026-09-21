"""
services/common/fallback_manager.py - 降级状态管理器

提供服务降级（degraded mode）的统一管理：
- 连接状态跟踪
- 重连策略（指数退避）
- 降级模式下返回本地数据
- 状态变更通知
"""

import json
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ConnectionState(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"       # 降级模式（重连中）
    DEGRADED_PERMANENT = "degraded_permanent"  # 永久降级（不再重试）


class FallbackManager:
    """降级状态管理器

    使用方法:
    1. 初始化时加载配置
    2. 连接失败时调用 on_connection_failed()
    3. 连接成功时调用 on_connection_success()
    4. 使用 get_fallback_data() 获取降级数据
    5. 使用 start_reconnect_timer() 开始重连
    """

    def __init__(
        self,
        service_name: str,
        config_path: Optional[Path] = None,
        fallback_data_path: Optional[str] = None,
        max_retry_attempts: int = 5,
        base_retry_delay: float = 2.0,
        max_retry_delay: float = 30.0,
    ):
        self.service_name = service_name
        self._state = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()

        # 重连配置
        self._retry_count = 0
        self._max_retry_attempts = max_retry_attempts
        self._base_retry_delay = base_retry_delay
        self._max_retry_delay = max_retry_delay
        self._retry_timer: Optional[threading.Timer] = None
        self._retry_timer_lock = threading.Lock()

        # 降级数据路径
        if fallback_data_path:
            self._fallback_data_path = Path(fallback_data_path)
        else:
            # 默认路径：config 同级目录下的 data/fallback/{service_name}
            if config_path:
                self._fallback_data_path = config_path.parent / "data" / "fallback" / service_name
            else:
                self._fallback_data_path = Path("data/fallback") / service_name

        # 状态变更回调列表 [(callback, description)]
        self._state_callbacks: List[tuple] = []

        # 最后错误信息
        self._last_error: Optional[str] = None

    @property
    def state(self) -> ConnectionState:
        """获取当前状态"""
        with self._state_lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self.state == ConnectionState.CONNECTED

    @property
    def is_degraded(self) -> bool:
        """是否处于降级模式"""
        return self.state in (ConnectionState.DEGRADED, ConnectionState.DEGRADED_PERMANENT)

    @property
    def is_permanently_degraded(self) -> bool:
        """是否永久降级"""
        return self.state == ConnectionState.DEGRADED_PERMANENT

    @property
    def retry_count(self) -> int:
        """当前重试次数"""
        return self._retry_count

    @property
    def last_error(self) -> Optional[str]:
        """最后错误信息"""
        return self._last_error

    def set_state(self, new_state: ConnectionState, error: Optional[str] = None):
        """设置状态"""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
            if error:
                self._last_error = error

            # 状态变更时通知回调
            if old_state != new_state:
                self._notify_state_change(old_state, new_state)

    def on_connection_success(self):
        """连接成功回调"""
        self._cancel_retry_timer()
        self._retry_count = 0
        self.set_state(ConnectionState.CONNECTED)
        print(f"[{self.service_name}] Connected successfully")

    def on_connection_failed(self, error: Optional[str] = None) -> bool:
        """连接失败回调

        返回:
            True - 继续重连
            False - 已达最大重试次数，进入永久降级
        """
        self._last_error = error

        if self.state == ConnectionState.CONNECTED:
            # 正常连接状态下断开，尝试重连
            self.set_state(ConnectionState.DEGRADED)
        elif self.state == ConnectionState.DEGRADED:
            # 已经在重连中，增加重试计数
            pass
        elif self.state == ConnectionState.CONNECTING:
            self.set_state(ConnectionState.DEGRADED)

        self._retry_count += 1
        # 只打印简洁的错误信息，避免打印完整堆栈
        error_short = str(error)[:80] + "..." if error and len(str(error)) > 80 else error
        print(f"[{self.service_name}] Connection failed (attempt {self._retry_count}/{self._max_retry_attempts}): {error_short}")

        if self._retry_count >= self._max_retry_attempts:
            self.set_state(ConnectionState.DEGRADED_PERMANENT, error)
            print(f"[{self.service_name}] Max retry attempts reached, entering permanent degraded mode")
            return False

        return True

    def get_retry_delay(self) -> float:
        """获取下一次重试延迟（指数退避）"""
        delay = min(self._base_retry_delay * (2 ** (self._retry_count - 1)), self._max_retry_delay)
        return delay

    def start_reconnect_timer(self, reconnect_fn: Callable[[], bool]):
        """启动重连定时器

        Args:
            reconnect_fn: 重连函数，返回 True 表示成功
        """
        with self._retry_timer_lock:
            self._cancel_retry_timer()

            if self.is_permanently_degraded:
                return

            delay = self.get_retry_delay()
            print(f"[{self.service_name}] Scheduling reconnect in {delay:.1f}s...")

            def _do_reconnect():
                self.set_state(ConnectionState.CONNECTING)
                success = reconnect_fn()
                if success:
                    self.on_connection_success()
                else:
                    if self.on_connection_failed(self._last_error):
                        self.start_reconnect_timer(reconnect_fn)
                    else:
                        # 永久降级，不做更多操作
                        pass

            self._retry_timer = threading.Timer(delay, _do_reconnect)
            self._retry_timer.daemon = True
            self._retry_timer.start()

    def _cancel_retry_timer(self):
        """取消重连定时器"""
        if self._retry_timer:
            self._retry_timer.cancel()
            self._retry_timer = None

    def manual_reconnect(self, reconnect_fn: Callable[[], bool]) -> bool:
        """手动触发重连

        重置重试计数并尝试连接。
        """
        self._retry_count = 0
        self.set_state(ConnectionState.CONNECTING)
        success = reconnect_fn()
        if success:
            self.on_connection_success()
        else:
            if self.on_connection_failed(self._last_error):
                self.start_reconnect_timer(reconnect_fn)
        return success

    def reset(self):
        """重置状态"""
        self._cancel_retry_timer()
        self._retry_count = 0
        self._last_error = None
        self.set_state(ConnectionState.DISCONNECTED)

    def register_state_callback(self, callback: Callable[[ConnectionState, ConnectionState], None], description: str = ""):
        """注册状态变更回调

        Args:
            callback: 回调函数，签名 (old_state, new_state)
            description: 回调描述（用于调试）
        """
        self._state_callbacks.append((callback, description))

    def _notify_state_change(self, old_state: ConnectionState, new_state: ConnectionState):
        """通知状态变更"""
        for callback, desc in self._state_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                print(f"[{self.service_name}] State callback error ({desc}): {e}")

    def get_fallback_data(self, data_type: str) -> Optional[Any]:
        """获取降级数据

        Args:
            data_type: 数据类型，如 "qubits.json", "experiments.json"

        Returns:
            数据内容，失败返回 None
        """
        fallback_file = self._fallback_data_path / data_type
        if not fallback_file.exists():
            print(f"[{self.service_name}] Fallback data not found: {fallback_file}")
            return None

        try:
            with open(fallback_file, "r", encoding="utf-8") as f:
                if fallback_file.suffix == ".json":
                    return json.load(f)
                else:
                    return f.read()
        except Exception as e:
            print(f"[{self.service_name}] Failed to load fallback data {fallback_file}: {e}")
            return None

    def load_fallback_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
        """加载降级配置

        Args:
            config_path: 配置文件路径，默认从 config/fallback_config.json 加载

        Returns:
            配置字典
        """
        if config_path is None:
            # 默认路径
            current = Path(__file__).parent.parent
            config_path = current / "config" / "fallback_config.json"

        if not config_path.exists():
            print(f"[FallbackManager] Config not found: {config_path}, using defaults")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[FallbackManager] Failed to load config: {e}")
            return {}

    def get_status_info(self) -> Dict[str, Any]:
        """获取状态信息"""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "is_connected": self.is_connected,
            "is_degraded": self.is_degraded,
            "is_permanently_degraded": self.is_permanently_degraded,
            "retry_count": self._retry_count,
            "retry_delay": self.get_retry_delay() if self.is_degraded else None,
            "max_retry_attempts": self._max_retry_attempts,
            "last_error": self._last_error,
            "fallback_data_path": str(self._fallback_data_path),
        }
