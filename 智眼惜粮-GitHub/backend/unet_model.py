# unet_model.py（完全匹配训练时的U-Net结构）
import torch


class DoubleConv(torch.nn.Module):
    """两次卷积+批归一化+ReLU（与训练代码100%一致）"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.double_conv = torch.nn.Sequential(
            torch.nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            torch.nn.BatchNorm2d(out_channels),
            torch.nn.ReLU(inplace=True),
            torch.nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            torch.nn.BatchNorm2d(out_channels),
            torch.nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.double_conv(x)


class UNet(torch.nn.Module):
    """与训练代码完全一致的U-Net结构"""

    def __init__(self, num_classes):
        super().__init__()
        # 编码器
        self.enc1 = DoubleConv(3, 64)
        self.pool1 = torch.nn.MaxPool2d(2)
        self.enc2 = DoubleConv(64, 128)
        self.pool2 = torch.nn.MaxPool2d(2)
        self.enc3 = DoubleConv(128, 256)
        self.pool3 = torch.nn.MaxPool2d(2)
        self.middle = DoubleConv(256, 512)  # 中间层
        # 解码器
        self.upconv3 = torch.nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.dec3 = DoubleConv(512, 256)  # 256(上采样)+256(编码器)=512
        self.upconv2 = torch.nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(256, 128)  # 128+128=256
        self.upconv1 = torch.nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(128, 64)  # 64+64=128
        # 输出层
        self.out_conv = torch.nn.Conv2d(64, num_classes, kernel_size=1)

    def forward(self, x):
        # 编码器特征
        enc1 = self.enc1(x)  # (B,64,H,W)
        enc2 = self.enc2(self.pool1(enc1))  # (B,128,H/2,W/2)
        enc3 = self.enc3(self.pool2(enc2))  # (B,256,H/4,W/4)
        middle = self.middle(self.pool3(enc3))  # (B,512,H/8,W/8)
        # 解码器
        dec3 = self.upconv3(middle)  # (B,256,H/4,W/4)
        dec3 = self.dec3(torch.cat([dec3, enc3], dim=1))  # 拼接编码器特征
        dec2 = self.upconv2(dec3)  # (B,128,H/2,W/2)
        dec2 = self.dec2(torch.cat([dec2, enc2], dim=1))
        dec1 = self.upconv1(dec2)  # (B,64,H,W)
        dec1 = self.dec1(torch.cat([dec1, enc1], dim=1))
        return self.out_conv(dec1)  # (B, NUM_CLASSES, H, W)