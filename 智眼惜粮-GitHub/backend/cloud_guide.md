# 腾讯云GPU训练操作指南

---

## 一、你需要准备的东西

| 物品 | 说明 |
|------|------|
| 腾讯云账号 | 注册实名认证过 |
| 本地文件 | 当前项目的整个 `FastAPIProject1` 文件夹 |
| 钱 | 约 **10-20 元**（T4 GPU 按量计费，跑完就关） |

---

## 二、购买GPU实例（10分钟）

### 步骤1：进入GPU实例购买页
打开 https://console.cloud.tencent.com/cvm → 点击「新建」

### 步骤2：选择配置
```
计费模式：按量计费（跑完就销毁，最省钱）
地域：广州/上海（离你近）
机型：GPU计算型 GN7
  - 实例：GN7.2XLARGE32（1颗T4 GPU, 16GB显存, 8核32GB内存）
镜像：选「公共镜像」→ Ubuntu Server 22.04 LTS 64位
系统盘：云硬盘 100GB
网络：按流量计费，带宽选 5Mbps 或更高
安全组：勾选「放通22端口」(SSH)
```

### 步骤3：设置登录方式
- 选择「密钥对」→ 点击「新建密钥对」→ 命名为 `cloudgpu` → 下载 `.pem` 文件
- **把 .pem 文件放到桌面，后面要用**

### 步骤4：确认购买
点击「开通」，实例创建需要2-3分钟

### 步骤5：获取公网IP
在实例列表中找到创建的实例，复制「公网IPv4地址」

---

## 三、上传文件到云服务器

打开你本地的 **PowerShell** 或 **CMD**：

```powershell
# 假设你的 .pem 密钥在桌面
cd C:\Users\<你的用户名>\Desktop

# 压缩项目（不含增强图，只传原图）
cd "<你的项目路径>/后端/Fastapi/FastAPIProject1"

# 创建纯净压缩包(排除增强图和Python缓存)
tar -czf cloud_package.tar.gz `
  --exclude=files/augmented `
  --exclude=files/annotated `
  --exclude=__pycache__ `
  --exclude="*.pyc" `
  --exclude=".git" `
  augment_dataset.py train_waste_cause.py waste_cause_model.py `
  waste_cause_inference.py cloud_train_config.py cloud_run.sh `
  extract_features.py unet_model.py cluster_labels.py add_labels.py `
  config.py `
  waste_cause_features_labeled.csv `
  model/best.pt model/unet_best.pth `
  files/

# 查看压缩包大小
dir cloud_package.tar.gz
```

如果Windows没有tar命令，用下面这个替代：

```powershell
# 方法2：使用 Python 创建压缩包
python -c "
import zipfile, os, glob
base = r'<你的项目路径>/后端/Fastapi/FastAPIProject1'
with zipfile.ZipFile('cloud_package.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(base):
        # 排除增强图和缓存
        dirs[:] = [d for d in dirs if d not in ('augmented', 'annotated', '__pycache__', '.git')]
        for f in files:
            if f.endswith('.pyc'):
                continue
            full = os.path.join(root, f)
            arc = os.path.relpath(full, base)
            zf.write(full, arc)
            if len(zf.filelist) % 200 == 0:
                print(f'已打包 {len(zf.filelist)} 个文件...')
    print(f'完成，共 {len(zf.filelist)} 个文件')
"
```

### 上传压缩包
```powershell
# 把 YOUR_PUBLIC_IP 换成实例的公网IP
# 把 cloudgpu.pem 换成你下载的密钥文件名
scp -i C:\Users\<你的用户名>\Desktop\cloudgpu.pem cloud_package.tar.gz ubuntu@你的公网IP:~/ 
```

如果 scp 不可用，装个 MobaXterm (百度搜下载)，用它的 SFTP 拖拽上传。

---

## 四、连接服务器，配置环境

```powershell
# SSH连接
ssh -i C:\Users\<你的用户名>\Desktop\cloudgpu.pem ubuntu@你的公网IP
```

连上后，在云服务器终端依次执行：

```bash
# 1. 解压项目
cd ~
tar -xzf cloud_package.tar.gz
cd FastAPIProject1
ls  # 确认文件都在

# 2. 安装CUDA驱动环境（T4自带的，检查下）
nvidia-smi
# 应该看到 Tesla T4, CUDA 12.x

# 3. 安装 PyTorch CUDA版
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 4. 安装其他依赖
pip install pandas numpy opencv-python pillow scikit-learn tqdm matplotlib ultralytics albumentations

# 5. 验证
python -c "import torch; print('CUDA OK:', torch.cuda.is_available())"
# 必须显示: CUDA OK: True
```

---

## 五、一键训练

```bash
# 给脚本执行权限
chmod +x cloud_run.sh

# 后台运行（防止SSH断开中断训练）
nohup bash cloud_run.sh > training.log 2>&1 &

# 查看实时进度
tail -f training.log
# 按 Ctrl+C 退出查看（不会中断训练）
```

训练时间预估：**T4 GPU 约 25-35 分钟**（增强 15-20分钟 + 训练 10-15分钟）

---

## 六、下载结果

训练完成后，在本地 PowerShell 执行：

```powershell
# 下载模型和曲线图
scp -i C:\Users\<你的用户名>\Desktop\cloudgpu.pem ubuntu@你的公网IP:~/FastAPIProject1/model/waste_cause_3cls.pth "D:\毕业设计\...\FastAPIProject1\model\"
scp -i C:\Users\<你的用户名>\Desktop\cloudgpu.pem ubuntu@你的公网IP:~/FastAPIProject1/training_curves.png "D:\毕业设计\...\FastAPIProject1\"

# 也可以下载完整日志
scp -i C:\Users\<你的用户名>\Desktop\cloudgpu.pem ubuntu@你的公网IP:~/FastAPIProject1/training.log .
```

---

## 七、销毁实例（重要！不然一直扣费）

在腾讯云控制台 → 实例列表 → 选择你的GPU实例 → 更多 → **销毁/退还**

---

## 预计费用

| 项目 | 单价 | 用量 | 费用 |
|------|------|------|------|
| GN7.2XLARGE32 | ~6.5元/小时 | 1小时 | 6.5元 |
| 系统盘 100GB | ~0.05元/小时 | 1小时 | 0.05元 |
| 公网流量(上传) | ~0.8元/GB | ~1.5GB | 1.2元 |
| **合计** | | | **< 10元** |

---

## 云GPU vs 本地 RTX3050

| 对比 | 本地 RTX 3050 | 腾讯云 T4 |
|------|:----------:|:--------:|
| 显存 | 4GB | **16GB** |
| 可用 ResNet | 仅 resnet18 | **resnet50** |
| Batch Size | 16 | **48** |
| 增强速度 | ~2秒/张 | ~0.5秒/张 |
| 总耗时 | ~2小时 | **~30分钟** |
| 模型参数量 | 11M | **24M** |
| 费用 | 0 | ~8元 |
