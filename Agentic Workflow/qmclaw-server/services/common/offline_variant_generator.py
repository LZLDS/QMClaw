"""
services/common/offline_variant_generator.py - 离线数据变体生成器

基于已有历史数据生成测量变体，模拟不同测量条件：
- 噪声缩放 (noise_scale)
- 幅度漂移 (amplitude_drift)
- 频率偏移 (frequency_offset)
- 相位噪声 (phase_noise)
- 数据点缺失 (dropout)
"""

import json
import random
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class VariantGenerator:
    """
    数据变体生成器

    基于原始 HDF5 数据，应用各种变换生成变体。
    """

    # 变体类型定义
    VARIANT_TYPES = {
        "noise_scale": {
            "name": "噪声缩放",
            "description": "按比例缩放数据噪声水平",
            "params": [
                {"name": "scale", "type": "float", "min": 0.1, "max": 3.0, "default": 1.0, "description": "噪声缩放因子"}
            ],
            "category": "noise"
        },
        "amplitude_drift": {
            "name": "幅度漂移",
            "description": "添加幅度偏移，模拟信号漂移",
            "params": [
                {"name": "drift", "type": "float", "min": -0.5, "max": 0.5, "default": 0.0, "description": "漂移比例 (-50% ~ +50%)"},
                {"name": "direction", "type": "select", "options": ["up", "down", "both"], "default": "both", "description": "漂移方向"}
            ],
            "category": "drift"
        },
        "frequency_offset": {
            "name": "频率偏移",
            "description": "在频率轴上添加偏移，模拟 LO 漂移",
            "params": [
                {"name": "offset", "type": "float", "min": -10.0, "max": 10.0, "default": 0.0, "description": "频率偏移 (MHz)"},
                {"name": "unit", "type": "select", "options": ["MHz", "kHz", "Hz"], "default": "MHz", "description": "单位"}
            ],
            "category": "frequency"
        },
        "phase_noise": {
            "name": "相位噪声",
            "description": "添加随机相位噪声",
            "params": [
                {"name": "std", "type": "float", "min": 0.0, "max": 0.5, "default": 0.0, "description": "相位噪声标准差 (rad)"},
                {"name": "seed", "type": "int", "min": 0, "max": 99999, "default": None, "description": "随机种子"}
            ],
            "category": "noise"
        },
        "dropout": {
            "name": "数据缺失",
            "description": "随机丢弃部分数据点",
            "params": [
                {"name": "ratio", "type": "float", "min": 0.0, "max": 0.5, "default": 0.0, "description": "缺失比例 (0~50%)"},
                {"name": "burst", "type": "bool", "default": False, "description": "是否突发缺失"}
            ],
            "category": "quality"
        },
        "time_drift": {
            "name": "时间漂移",
            "description": "在时间轴上添加非线性漂移",
            "params": [
                {"name": "rate", "type": "float", "min": -0.1, "max": 0.1, "default": 0.0, "description": "漂移速率"},
                {"name": "quadratic", "type": "float", "min": -0.01, "max": 0.01, "default": 0.0, "description": "二次项系数"}
            ],
            "category": "drift"
        },
        "iq_rotation": {
            "name": "IQ 旋转",
            "description": "对 IQ 数据应用旋转矩阵",
            "params": [
                {"name": "angle", "type": "float", "min": -180.0, "max": 180.0, "default": 0.0, "description": "旋转角度 (度)"}
            ],
            "category": "transform"
        },
        "mix_channels": {
            "name": "通道混合",
            "description": "混合两个通道的数据（用于模拟串扰）",
            "params": [
                {"name": "mix_ratio", "type": "float", "min": 0.0, "max": 0.5, "default": 0.0, "description": "混合比例"}
            ],
            "category": "quality"
        }
    }

    # 变体存储目录
    VARIANTS_DIR = Path(__file__).parent.parent.parent / "data" / "variants"
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)

    def __init__(self, offline_provider: 'OfflineDataProvider'):
        """
        初始化变体生成器

        Args:
            offline_provider: OfflineDataProvider 实例
        """
        self._provider = offline_provider

    def list_variant_types(self) -> List[Dict[str, Any]]:
        """列出所有支持的变体类型"""
        return [
            {
                "id": vid,
                "name": vinfo["name"],
                "description": vinfo["description"],
                "params": vinfo["params"],
                "category": vinfo["category"]
            }
            for vid, vinfo in self.VARIANT_TYPES.items()
        ]

    def list_categories(self) -> List[str]:
        """列出所有变体类别"""
        categories = set()
        for vinfo in self.VARIANT_TYPES.values():
            categories.add(vinfo["category"])
        return sorted(categories)

    def generate_variant(
        self,
        source_dataset_id: str,
        variant_type: str,
        params: Dict[str, Any],
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        生成数据变体

        Args:
            source_dataset_id: 源数据集 ID
            variant_type: 变体类型
            params: 变体参数
            seed: 随机种子

        Returns:
            变体信息字典
        """
        if variant_type not in self.VARIANT_TYPES:
            raise ValueError(f"Unknown variant type: {variant_type}")

        # 设置随机种子
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # 加载原始数据
        source_ds = self._provider.get_dataset(source_dataset_id)
        if not source_ds:
            raise ValueError(f"Dataset not found: {source_dataset_id}")

        original_data = self._provider.load_hdf5_data(source_ds.file_path)
        if not original_data:
            raise RuntimeError(f"Failed to load data from {source_ds.file_path}")

        # 应用变换
        data_dict = original_data.get("data", {})
        result = self._apply_variant(variant_type, data_dict, params)

        # 生成变体 ID
        variant_id = self._generate_variant_id(source_dataset_id, variant_type, params)

        # 保存变体
        variant_info = self._save_variant(variant_id, source_ds, result, params)

        return {
            "variant_id": variant_id,
            "source_id": source_dataset_id,
            "source_name": source_ds.name,
            "qubit": source_ds.qubit,
            "experiment_type": source_ds.experiment_type,
            "variant_type": variant_type,
            "params": params,
            "file_path": variant_info["file_path"],
            "preview": result.get("preview", {}),
            "metadata": variant_info["metadata"]
        }

    def _apply_variant(
        self,
        variant_type: str,
        data: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """应用变体变换"""
        method_name = f"_apply_{variant_type}"
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            return method(data, params)
        else:
            # 默认变换：添加高斯噪声
            return self._apply_default(data, params)

    def _apply_noise_scale(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """噪声缩放"""
        scale = params.get("scale", 1.0)

        result = {}
        preview = {}

        for key in ["x", "y", "data"]:
            if key in data:
                arr = np.array(data[key])
                if key == "x":
                    # X 轴不添加噪声
                    result[key] = arr.tolist()
                else:
                    # 计算原始标准差
                    original_std = np.std(arr)
                    original_mean = np.mean(arr)

                    # 生成噪声
                    noise = np.random.normal(0, original_std * (scale - 1), arr.shape)

                    # 应用缩放
                    scaled = arr + noise
                    result[key] = scaled.tolist()

                    preview[key] = {
                        "original_std": float(original_std),
                        "scaled_std": float(np.std(scaled)),
                        "scale_factor": scale
                    }

        return {"data": result, "preview": preview}

    def _apply_amplitude_drift(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """幅度漂移"""
        drift = params.get("drift", 0.0)
        direction = params.get("direction", "both")

        result = {}
        preview = {}

        for key in ["x", "y", "data"]:
            if key in data:
                arr = np.array(data[key])

                # 计算漂移
                if direction == "up":
                    drift_factor = abs(drift)
                elif direction == "down":
                    drift_factor = -abs(drift)
                else:  # both
                    drift_factor = drift

                # 应用漂移
                drifted = arr * (1 + drift_factor)
                result[key] = drifted.tolist()

                if key == "y":
                    preview[key] = {
                        "original_mean": float(np.mean(arr)),
                        "drifted_mean": float(np.mean(drifted)),
                        "drift_ratio": drift
                    }

        return {"data": result, "preview": preview}

    def _apply_frequency_offset(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """频率偏移"""
        offset = params.get("offset", 0.0)
        unit = params.get("unit", "MHz")

        # 转换为 Hz
        unit_multiplier = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6}.get(unit, 1.0)
        offset_hz = offset * unit_multiplier

        result = {}
        preview = {}

        if "x" in data:
            x = np.array(data["x"])
            # 假设 x 是频率，单位可能是 Hz 或其倍数
            # 检查 x 轴的大小，判断单位
            x_mean = np.mean(np.abs(x))
            if x_mean > 1e9:  # 大概是 Hz
                x_unit = 1.0
            elif x_mean > 1e6:  # 大概是 MHz
                x_unit = 1e-6
            elif x_mean > 1e3:  # 大概是 kHz
                x_unit = 1e-3
            else:
                x_unit = 1.0

            # 应用偏移
            x_offset = x + offset_hz * x_unit
            result["x"] = x_offset.tolist()
            preview["x"] = {
                "original_range": [float(np.min(x)), float(np.max(x))],
                "offset": offset_hz
            }

        # Y 轴保持不变
        for key in ["y", "data"]:
            if key in data:
                result[key] = data[key]

        return {"data": result, "preview": preview}

    def _apply_phase_noise(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """相位噪声"""
        std = params.get("std", 0.0)
        seed = params.get("seed")

        if seed is not None:
            np.random.seed(seed)

        result = {}
        preview = {}

        # 假设数据是复数形式 (I, Q)
        # 或者对实数数据添加相位扰动
        for key in ["x", "y", "data"]:
            if key in data:
                arr = np.array(data[key])

                if key == "x":
                    # X 轴添加噪声
                    noise = np.random.normal(0, std, arr.shape)
                    noisy = arr + noise
                else:
                    # Y 轴添加噪声
                    noise = np.random.normal(0, std, arr.shape)
                    noisy = arr + noise

                result[key] = noisy.tolist()

                if key == "y":
                    preview[key] = {
                        "original_std": float(np.std(arr)),
                        "noisy_std": float(np.std(noisy)),
                        "noise_std": std
                    }

        return {"data": result, "preview": preview}

    def _apply_dropout(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """数据点缺失"""
        ratio = params.get("ratio", 0.0)
        burst = params.get("burst", False)

        result = {}
        preview = {}

        for key in ["x", "y", "data"]:
            if key in data:
                arr = np.array(data[key])

                if key == "x":
                    # X 轴不做缺失
                    result[key] = arr.tolist()
                else:
                    n = len(arr)
                    n_drop = int(n * ratio)

                    if n_drop == 0:
                        result[key] = arr.tolist()
                    elif burst:
                        # 突发缺失：从某个位置开始连续缺失
                        start = random.randint(0, n - n_drop - 1)
                        mask = np.ones(n, dtype=bool)
                        mask[start:start + n_drop] = False
                        result[key] = arr[mask].tolist()
                    else:
                        # 随机缺失
                        indices = random.sample(range(n), n - n_drop)
                        indices.sort()
                        result[key] = arr[indices].tolist()

                    preview[key] = {
                        "original_length": n,
                        "dropped_length": n_drop if key == "y" else 0,
                        "ratio": ratio
                    }

        return {"data": result, "preview": preview}

    def _apply_time_drift(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """时间漂移"""
        rate = params.get("rate", 0.0)
        quadratic = params.get("quadratic", 0.0)

        result = {}
        preview = {}

        if "x" in data:
            x = np.array(data["x"])
            n = len(x)

            # 创建时间索引
            t = np.arange(n)

            # 应用漂移
            x_drifted = x * (1 + rate * t + quadratic * t ** 2)
            result["x"] = x_drifted.tolist()
            preview["x"] = {"rate": rate, "quadratic": quadratic}

        # Y 轴保持不变
        for key in ["y", "data"]:
            if key in data:
                result[key] = data[key]

        return {"data": result, "preview": preview}

    def _apply_iq_rotation(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """IQ 旋转"""
        angle_deg = params.get("angle", 0.0)
        angle_rad = np.radians(angle_deg)

        result = {}
        preview = {}

        # 检查是否有 I, Q 数据
        i_data = data.get("I")
        q_data = data.get("Q")

        if i_data is not None and q_data is not None:
            I = np.array(i_data)
            Q = np.array(q_data)

            # 旋转矩阵
            cos_a = np.cos(angle_rad)
            sin_a = np.sin(angle_rad)

            I_rotated = I * cos_a - Q * sin_a
            Q_rotated = I * sin_a + Q * cos_a

            result["I"] = I_rotated.tolist()
            result["Q"] = Q_rotated.tolist()

            preview["rotation"] = {"angle_degrees": angle_deg}
        else:
            # 对 x, y 应用旋转（假设是复数数据的实部和虚部）
            x = np.array(data.get("x", data.get("data", [[0]] * len(data.get("x", [])))))
            y = np.array(data.get("y", [0] * len(x)))

            cos_a = np.cos(angle_rad)
            sin_a = np.sin(angle_rad)

            x_rotated = x * cos_a - y * sin_a
            y_rotated = x * sin_a + y * cos_a

            result["x"] = x_rotated.tolist()
            result["y"] = y_rotated.tolist()
            preview["rotation"] = {"angle_degrees": angle_deg}

        # 复制其他数据
        for key in ["data"]:
            if key in data and key not in result:
                result[key] = data[key]

        return {"data": result, "preview": preview}

    def _apply_mix_channels(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """通道混合"""
        mix_ratio = params.get("mix_ratio", 0.0)

        result = {}
        preview = {}

        # 获取两个通道
        x = np.array(data.get("x", []))
        y = np.array(data.get("y", data.get("data", [[0, 0]] * len(x))))

        if len(x) > 0 and len(y) > 0:
            if y.ndim == 1:
                # 假设 x 是通道1，y 的轻微扰动是通道2
                noise = np.random.normal(0, np.std(y) * mix_ratio, y.shape)
                y_mixed = y + noise
            else:
                # y 是多列数据
                y_mixed = y.copy()
                if y.shape[1] > 1:
                    noise = np.random.normal(0, np.std(y[:, 1]) * mix_ratio, y[:, 1].shape)
                    y_mixed[:, 1] = y[:, 1] + noise

            result["x"] = x.tolist()
            result["y"] = y_mixed.tolist()
            preview["mix"] = {"ratio": mix_ratio}

        # 复制其他数据
        for key in ["data"]:
            if key in data and key not in result:
                result[key] = data[key]

        return {"data": result, "preview": preview}

    def _apply_default(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """默认变换：添加高斯噪声"""
        scale = params.get("scale", 0.1)

        result = {}
        for key in ["x", "y", "data"]:
            if key in data:
                arr = np.array(data[key])
                noise = np.random.normal(0, scale * np.std(arr), arr.shape)
                result[key] = (arr + noise).tolist()

        return {"data": result, "preview": {"method": "default_noise"}}

    def _generate_variant_id(
        self,
        source_id: str,
        variant_type: str,
        params: Dict[str, Any]
    ) -> str:
        """生成唯一的变体 ID"""
        # 创建确定性 ID
        param_str = json.dumps(params, sort_keys=True)
        hash_input = f"{source_id}:{variant_type}:{param_str}"
        hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        return f"variant_{source_id}_{variant_type}_{hash_val}"

    def _save_variant(
        self,
        variant_id: str,
        source_ds: Any,
        result: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存变体到文件"""
        # 保存目录
        variant_dir = self.VARIANTS_DIR / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)

        # 保存数据文件 (JSON 格式，便于调试)
        import h5py
        data_file = variant_dir / "data.hdf5"

        try:
            with h5py.File(str(data_file), 'w') as f:
                data_dict = result.get("data", {})

                # 保存为单个 2D 数组
                if "x" in data_dict and "y" in data_dict:
                    x = np.array(data_dict["x"])
                    y = np.array(data_dict["y"])
                    combined = np.column_stack([x, y])
                    f.create_dataset("data", data=combined)
                elif "data" in data_dict:
                    data = np.array(data_dict["data"])
                    f.create_dataset("data", data=data)

                # 保存元数据
                f.attrs["variant_id"] = variant_id
                f.attrs["source_name"] = source_ds.name
                f.attrs["qubit"] = source_ds.qubit
                f.attrs["experiment_type"] = source_ds.experiment_type

        except Exception as e:
            # 如果 h5py 失败，保存为 JSON
            json_file = variant_dir / "data.json"
            with open(json_file, "w") as f:
                json.dump(result.get("data", {}), f)

        # 保存变体元信息
        info = {
            "variant_id": variant_id,
            "source_id": f"{source_ds.date}_{source_ds.id}",
            "source_name": source_ds.name,
            "qubit": source_ds.qubit,
            "experiment_type": source_ds.experiment_type,
            "date": source_ds.date,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "params": params,
            "file_path": str(data_file),
        }

        info_file = variant_dir / "info.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)

        return {
            "file_path": str(data_file),
            "metadata": info
        }

    def list_variants(self, source_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出已生成的变体"""
        variants = []

        if not self.VARIANTS_DIR.exists():
            return variants

        for variant_dir in self.VARIANTS_DIR.iterdir():
            if not variant_dir.is_dir():
                continue

            info_file = variant_dir / "info.json"
            if not info_file.exists():
                continue

            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    info = json.load(f)

                # 过滤
                if source_id and info.get("source_id") != source_id:
                    continue

                variants.append(info)
            except Exception:
                continue

        return sorted(variants, key=lambda x: x.get("created_at", ""), reverse=True)

    def get_variant(self, variant_id: str) -> Optional[Dict[str, Any]]:
        """获取变体信息"""
        variant_dir = self.VARIANTS_DIR / variant_id
        info_file = variant_dir / "info.json"

        if not info_file.exists():
            return None

        try:
            with open(info_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def load_variant_data(self, variant_id: str) -> Optional[Dict[str, Any]]:
        """加载变体数据"""
        variant_dir = self.VARIANTS_DIR / variant_id

        # 尝试 HDF5
        data_file = variant_dir / "data.hdf5"
        if data_file.exists():
            try:
                import h5py
                with h5py.File(str(data_file), 'r') as f:
                    data = {}
                    if "data" in f:
                        arr = np.array(f["data"])
                        if arr.ndim == 2 and arr.shape[1] >= 2:
                            data["x"] = arr[:, 0].tolist()
                            data["y"] = arr[:, 1].tolist()
                        else:
                            data["data"] = arr.tolist()
                    return data
            except Exception:
                pass

        # 回退到 JSON
        json_file = variant_dir / "data.json"
        if json_file.exists():
            with open(json_file, "r") as f:
                return json.load(f)

        return None
