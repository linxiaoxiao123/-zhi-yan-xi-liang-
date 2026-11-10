"""
云GPU训练配置 — 根据显存自动选择最优参数
用法: 在train_waste_cause.py最前面 import cloud_train_config
      config = cloud_train_config.get_config()
"""
import torch


def get_gpu_info():
    if not torch.cuda.is_available():
        return {"name": "CPU", "vram_gb": 0}
    name = torch.cuda.get_device_name(0)
    vram_bytes = torch.cuda.get_device_properties(0).total_memory
    vram_gb = vram_bytes / (1024 ** 3)
    return {"name": name, "vram_gb": round(vram_gb, 1)}


def get_config():
    gpu = get_gpu_info()
    vram = gpu["vram_gb"]
    print(f"云GPU: {gpu['name']} ({vram}GB VRAM)")

    if vram >= 14:  # T4/V100-16GB/A10 — 大batch加速
        config = {
            "resnet_variant": "resnet50",
            "batch_size": 48,
            "num_epochs": 60,
            "learning_rate": 3e-5,
            "num_workers": 4,
        }
        tier = "高性能"
    elif vram >= 6:  # RTX 3060/4060
        config = {
            "resnet_variant": "resnet50",
            "batch_size": 20,
            "num_epochs": 60,
            "learning_rate": 3e-5,
            "num_workers": 4,
        }
        tier = "标准"
    else:  # RTX 3050 4GB or CPU
        config = {
            "resnet_variant": "resnet18",
            "batch_size": 16,
            "num_epochs": 60,
            "learning_rate": 3e-5,
            "num_workers": 2,
        }
        tier = "轻量"

    print(f"配置等级: {tier} | ResNet: {config['resnet_variant']} | "
          f"Batch: {config['batch_size']} | LR: {config['learning_rate']}")
    return config
