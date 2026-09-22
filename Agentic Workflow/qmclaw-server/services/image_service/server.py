"""
services/image_service/server.py - 图像服务

提供图像分类和模型管理功能：
- PyTorch/ONNX 推理
- 模型训练
- 图像分类
"""

import json
import random
import time
import threading
import sys
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseService, ServiceConfig, run_service, _safe_print
from ..common import setup_logging, config


def _log(msg: str):
    """安全日志输出"""
    _safe_print(f"[image_service] {msg}")


_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


def _preprocess_image(path, size=(224, 224), flip: bool = False, brightness: float = None):
    """把图片读成归一化后的 CHW 浮点张量。

    故意不用 torchvision：本环境只装了 torch 没装 torchvision，所以缩放和归一化
    用 PIL + numpy 自己完成（训练与推理共用，保证两边预处理一致）。
    """
    import numpy as np
    import torch
    from PIL import Image

    img = Image.open(path).convert("RGB")
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img = img.resize(size)

    arr = np.asarray(img, dtype="float32") / 255.0
    if brightness is not None:
        arr = np.clip(arr * brightness, 0.0, 1.0)
    arr = (arr - np.array(_IMAGENET_MEAN, dtype="float32")) / np.array(_IMAGENET_STD, dtype="float32")
    return torch.from_numpy(arr.transpose(2, 0, 1))


# 模型和图像目录
MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models"
IMAGE_DIR = Path(__file__).parent.parent.parent.parent / "images"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)


class ImageService(BaseService):
    """图像服务

    核心功能:
    - 图像分类推理
    - 模型训练
    - 模型管理
    """

    def __init__(self, port: int = 3007):
        cfg = ServiceConfig(
            name="image_service",
            host="localhost",
            port=port,
        )
        super().__init__(cfg)

        # 模型加载状态
        self._model: Optional[Any] = None
        self._model_backend: str = "pytorch"  # pytorch or onnx
        self._model_loaded: bool = False
        self._model_lock = threading.Lock()

        # 分类标签
        self._class_names: List[str] = ["good", "bad"]
        self._model_path = MODEL_DIR / "classifier.pth"

        # 分类历史（内存中，供 /classify/stats 统计最近判定结果）
        self._classification_history: List[Dict[str, Any]] = []
        self._history_lock = threading.Lock()

        # 训练状态
        self._training: bool = False
        self._training_progress: float = 0.0

        _log("Image service initialized")
        _log(f"Model dir: {MODEL_DIR}")
        _log(f"Image dir: {IMAGE_DIR}")

    def _load_model(self) -> bool:
        """加载模型"""
        with self._model_lock:
            if self._model_loaded:
                return True

            if not self._model_path.exists():
                _log(f"Model file not found: {self._model_path}")
                return False

            try:
                if self._model_backend == "pytorch":
                    import torch
                    import torch.nn as nn

                    # 简单的 CNN 模型
                    class SimpleCNN(nn.Module):
                        def __init__(self, num_classes=2):
                            super().__init__()
                            self.features = nn.Sequential(
                                nn.Conv2d(3, 16, 3, padding=1),
                                nn.ReLU(),
                                nn.MaxPool2d(2),
                                nn.Conv2d(16, 32, 3, padding=1),
                                nn.ReLU(),
                                nn.MaxPool2d(2),
                                nn.Conv2d(32, 64, 3, padding=1),
                                nn.ReLU(),
                                nn.MaxPool2d(2),
                            )
                            self.classifier = nn.Sequential(
                                nn.Flatten(),
                                nn.Linear(64 * 28 * 28, 128),
                                nn.ReLU(),
                                nn.Dropout(0.5),
                                nn.Linear(128, num_classes),
                            )

                        def forward(self, x):
                            x = self.features(x)
                            x = self.classifier(x)
                            return x

                    checkpoint = torch.load(self._model_path, map_location='cpu')

                    # 训练时会把类别顺序一起存下来，否则 good/bad 可能颠倒
                    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
                        classes = checkpoint.get("classes") or self._class_names
                        state_dict = checkpoint["state_dict"]
                    else:  # 兼容只有 state_dict 的旧模型
                        classes = self._class_names
                        state_dict = checkpoint

                    self._model = SimpleCNN(num_classes=len(classes))
                    self._model.load_state_dict(state_dict)
                    self._class_names = list(classes)
                    self._model.eval()
                    self._model_loaded = True
                    _log(f"PyTorch model loaded (classes={self._class_names})")

                elif self._model_backend == "onnx":
                    import onnxruntime as ort
                    self._model = ort.InferenceSession(str(self._model_path.with_suffix('.onnx')))
                    self._model_loaded = True
                    _log("ONNX model loaded")

                return self._model_loaded

            except Exception as e:
                _log(f"Model load error: {e}\n{traceback.format_exc()}")
                return False

    def _classify_image(self, image_path: str, threshold: float = 0.75) -> Dict[str, Any]:
        """分类单张图像"""
        if not self._load_model():
            return {"error": "Model not loaded"}

        try:
            import torch

            img_tensor = _preprocess_image(image_path).unsqueeze(0)

            # 推理
            with torch.no_grad():
                outputs = self._model(img_tensor)
                probabilities = torch.softmax(outputs, dim=1)[0]
                predicted_class = torch.argmax(probabilities).item()
                confidence = probabilities[predicted_class].item()

            result = {
                "class": self._class_names[predicted_class],
                "confidence": float(confidence),
                "probabilities": {
                    name: float(prob) for name, prob in zip(self._class_names, probabilities.tolist())
                },
                "needs_review": confidence < threshold,
            }

            self._record_classification(image_path, result)
            return result

        except Exception as e:
            _log(f"Classification error: {e}\n{traceback.format_exc()}")
            return {"error": str(e)}

    def _record_classification(self, image_path: str, result: Dict[str, Any]) -> None:
        """记录一次分类结果，供 /classify/stats 统计（仅内存，重启即清空）"""
        try:
            with self._history_lock:
                self._classification_history.append({
                    "timestamp": time.time(),
                    "path": str(image_path),
                    "filename": Path(image_path).name,
                    "class": result.get("class"),
                    "confidence": result.get("confidence"),
                    "needs_review": result.get("needs_review"),
                })
                # 只保留最近 500 条，避免无限增长
                if len(self._classification_history) > 500:
                    self._classification_history = self._classification_history[-500:]
        except Exception as exc:
            _log(f"WARNING: failed to record classification: {exc}")

    def _classify_folder(self, folder_path: str, threshold: float = 0.75, margin: float = 0.15) -> Dict[str, Any]:
        """批量分类文件夹中的图像"""
        if not self._load_model():
            return {"error": "Model not loaded"}

        folder = Path(folder_path)
        if not folder.exists():
            return {"error": f"Folder not found: {folder_path}"}

        # 获取所有图像文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
        image_files = [f for f in folder.iterdir() if f.suffix.lower() in image_extensions]

        if not image_files:
            return {"error": "No images found in folder", "results": []}

        results = []
        stats = {"good": 0, "bad": 0, "review": 0}

        for img_path in image_files:
            result = self._classify_image(str(img_path), threshold)
            if "error" not in result:
                result["filename"] = img_path.name
                results.append(result)

                # 统计
                if result["needs_review"]:
                    stats["review"] += 1
                elif result["class"] == "good":
                    stats["good"] += 1
                else:
                    stats["bad"] += 1

        return {
            "total": len(results),
            "stats": stats,
            "results": results,
        }

    def _train_model(self, epochs: int = 20, batch_size: int = 32, imbalance_mode: str = "weighted") -> Dict[str, Any]:
        """训练模型"""
        if self._training:
            return {"error": "Training already in progress"}

        # 检查训练数据
        train_dir = IMAGE_DIR / "train"
        if not train_dir.exists():
            return {"error": f"Training data not found: {train_dir}"}

        self._training = True
        self._training_progress = 0.0

        def train_async():
            try:
                import torch
                import torch.nn as nn

                _log(f"Starting training: epochs={epochs}, batch_size={batch_size}")

                # 类别目录名即类名（等价于 torchvision 的 ImageFolder，但不依赖它）
                classes = sorted(d.name for d in train_dir.iterdir() if d.is_dir())
                if not classes:
                    raise RuntimeError(f"No class sub-folders found under {train_dir}")

                samples = []
                for cls in classes:
                    for p in sorted((train_dir / cls).iterdir()):
                        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
                            samples.append((p, classes.index(cls)))

                if not samples:
                    raise RuntimeError(f"No images found under {train_dir}")

                _log(f"Training samples: {len(samples)}, classes: {classes}")

                num_classes = len(classes)
                self._class_names = classes

                # 创建模型
                class SimpleCNN(nn.Module):
                    def __init__(self, num_classes=2):
                        super().__init__()
                        self.features = nn.Sequential(
                            nn.Conv2d(3, 16, 3, padding=1),
                            nn.ReLU(),
                            nn.MaxPool2d(2),
                            nn.Conv2d(16, 32, 3, padding=1),
                            nn.ReLU(),
                            nn.MaxPool2d(2),
                            nn.Conv2d(32, 64, 3, padding=1),
                            nn.ReLU(),
                            nn.MaxPool2d(2),
                        )
                        self.classifier = nn.Sequential(
                            nn.Flatten(),
                            nn.Linear(64 * 28 * 28, 128),
                            nn.ReLU(),
                            nn.Dropout(0.5),
                            nn.Linear(128, num_classes),
                        )

                    def forward(self, x):
                        x = self.features(x)
                        x = self.classifier(x)
                        return x

                model = SimpleCNN(num_classes=num_classes)

                # 损失函数（处理类别不平衡）
                if imbalance_mode == "weighted":
                    class_counts = [0] * num_classes
                    for _, label in samples:
                        class_counts[label] += 1
                    weights = [1.0 / c if c > 0 else 1.0 for c in class_counts]
                    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights))
                else:
                    criterion = nn.CrossEntropyLoss()

                optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

                # 训练循环
                for epoch in range(epochs):
                    model.train()
                    random.shuffle(samples)
                    total_loss = 0.0
                    correct = 0
                    total = 0
                    n_batches = max(1, (len(samples) + batch_size - 1) // batch_size)

                    for batch_idx in range(n_batches):
                        batch = samples[batch_idx * batch_size:(batch_idx + 1) * batch_size]

                        # 轻量数据增强：随机水平翻转 + 随机亮度
                        images = torch.stack([
                            _preprocess_image(
                                p,
                                flip=random.random() < 0.5,
                                brightness=random.uniform(0.8, 1.2) if random.random() < 0.5 else None,
                            )
                            for p, _ in batch
                        ])
                        labels = torch.tensor([label for _, label in batch], dtype=torch.long)

                        optimizer.zero_grad()
                        outputs = model(images)
                        loss = criterion(outputs, labels)
                        loss.backward()
                        optimizer.step()

                        total_loss += loss.item()
                        _, predicted = torch.max(outputs.data, 1)
                        total += labels.size(0)
                        correct += (predicted == labels).sum().item()

                        self._training_progress = (epoch + (batch_idx + 1) / n_batches) / epochs

                    accuracy = 100 * correct / total
                    avg_loss = total_loss / n_batches
                    _log(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}, Accuracy: {accuracy:.2f}%")

                # 保存模型（连同类别顺序一起存，加载时才能正确对应 good/bad）
                model.eval()
                torch.save({"state_dict": model.state_dict(), "classes": classes}, self._model_path)
                _log(f"Model saved to {self._model_path} (classes={classes})")

                self._model = model
                self._model_loaded = True

            except Exception as e:
                _log(f"Training error: {e}\n{traceback.format_exc()}")
            finally:
                self._training = False
                self._training_progress = 1.0

        thread = threading.Thread(target=train_async)
        thread.daemon = True
        thread.start()

        return {"success": True, "message": "Training started"}

    def handle_request(self, method: str, path: str, data: Dict[str, Any], query: Dict[str, List[str]]) -> Dict[str, Any]:
        """处理图像请求"""
        if path == "/health":
            return self._handle_health()
        elif path == "/classify/single":
            return self._handle_classify_single(data)
        elif path == "/classify/folder":
            return self._handle_classify_folder(data)
        elif path == "/train":
            return self._handle_train(data)
        elif path == "/model/info":
            return self._handle_model_info()
        elif path == "/training/status":
            return self._handle_training_status()
        # 注意：Express 网关实际转发的是 /stats 和 /classify/latest，
        # 这里把更直白的 /classify/stats、/classify/latest-experiment 也一并支持。
        elif path in ("/stats", "/classify/stats"):
            return self._handle_classify_stats(query)
        elif path in ("/classify/latest", "/classify/latest-experiment"):
            return self._handle_classify_latest_experiment(data)
        else:
            raise ValueError(f"Unknown path: {path}")

    def _handle_classify_stats(self, query: Dict[str, List[str]]) -> Dict[str, Any]:
        """最近一段时间的分类统计（前端「分类统计」面板）"""
        since_hours = 24.0
        if query.get("sinceHours"):
            try:
                since_hours = float(query["sinceHours"][0])
            except (TypeError, ValueError):
                pass

        cutoff = time.time() - since_hours * 3600
        with self._history_lock:
            recent = [h for h in self._classification_history if h["timestamp"] >= cutoff]

        stats = {"good": 0, "bad": 0, "review": 0}
        for item in recent:
            if item.get("needs_review"):
                stats["review"] += 1
            elif item.get("class") == "good":
                stats["good"] += 1
            else:
                stats["bad"] += 1

        return {
            "sinceHours": since_hours,
            "total": len(recent),
            "stats": stats,
            "modelLoaded": self._model_loaded,
            "modelExists": self._model_path.exists(),
            "recent": recent[-20:][::-1],
        }

    def _handle_classify_latest_experiment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """分类最近一次实验出的图（优先按 qubit 名匹配文件名）"""
        if not self._load_model():
            return {"error": "Model not loaded. Train a model first (POST /train)."}

        qubit = (data.get("qubit") or "").strip()
        threshold = data.get("reviewThreshold", data.get("threshold", 0.75))

        base = Path(__file__).parent.parent.parent.parent
        search_dirs = [base / "qmclaw-web" / "public" / "plots", IMAGE_DIR]
        extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}

        candidates = []
        for folder in search_dirs:
            if folder.is_dir():
                candidates += [f for f in folder.iterdir() if f.suffix.lower() in extensions]

        if not candidates:
            return {"error": "No experiment images found", "searched": [str(d) for d in search_dirs]}

        pool = [f for f in candidates if qubit.lower() in f.name.lower()] if qubit else []
        latest = max(pool or candidates, key=lambda f: f.stat().st_mtime)

        result = self._classify_image(str(latest), threshold)
        if "error" in result:
            return result

        result.update({
            "filename": latest.name,
            "path": str(latest),
            "qubit": qubit or None,
            "matched_qubit": bool(qubit and qubit.lower() in latest.name.lower()),
        })
        return result

    def _handle_health(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "service": "image_service",
            "model_loaded": self._model_loaded,
            "model_backend": self._model_backend,
            "training": self._training,
        }

    def _handle_classify_single(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """分类单张图像"""
        image_path = data.get("imagePath", "")
        threshold = data.get("threshold", 0.75)

        if not image_path:
            return {"error": "imagePath is required"}

        return self._classify_image(image_path, threshold)

    def _handle_classify_folder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """批量分类"""
        folder_path = data.get("folderPath", "")
        threshold = data.get("threshold", 0.75)
        margin = data.get("margin", 0.15)

        if not folder_path:
            return {"error": "folderPath is required"}

        return self._classify_folder(folder_path, threshold, margin)

    def _handle_train(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """训练模型"""
        epochs = data.get("epochs", 20)
        batch_size = data.get("batchSize", 32)
        imbalance_mode = data.get("imbalanceMode", "weighted")

        return self._train_model(epochs, batch_size, imbalance_mode)

    def _handle_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_path": str(self._model_path),
            "model_exists": self._model_path.exists(),
            "model_loaded": self._model_loaded,
            "backend": self._model_backend,
            "classes": self._class_names,
        }

    def _handle_training_status(self) -> Dict[str, Any]:
        """获取训练状态"""
        return {
            "training": self._training,
            "progress": self._training_progress,
        }

    def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        return {
            "status": "healthy",
            "service": "image_service",
            "model_loaded": self._model_loaded,
            "training": self._training,
        }


def main():
    """主入口"""
    service = ImageService(port=3007)
    run_service(service)


if __name__ == "__main__":
    main()
