# 寻找大鸡蛋

语言版本: [English](README.md) | [Deutsch](README_DE.md)

## 直接访问网站：[find-l-eggs.live](https://find-l-eggs.live)

一个轻量级网页应用（不使用 Node.js），用于查看 Erlangen、Fürth 和 Nürnberg 的超市是否有 L 号鸡蛋。

## 功能

- 使用 OpenStreetMap 地图展示 `Supermarkets.txt` 中的超市点位
- 4 种点位状态：
  - 绿色 = 大量
  - 黄色 = 少量
  - 红色 = 没有
  - 灰色 = 暂无信息 / 低于阈值
- 点击点位可查看品牌与地址，并提交投票（大量 / 少量 / 没有）
- 投票有效期：12 小时
- 同一 IP 在 1 小时内不能给同一超市提交相同状态的投票
- 地图点位颜色按最高票状态显示
- 0 票显示灰色，1~2 票显示浅色，3 票以上仅在最新一次提交发生于 3 小时内时显示深色（否则显示浅色）
- 若两种或三种状态平票，则最后一票投票最晚的状态优先
- 界面支持英文、中文、德文切换

## 运行

1. 确保已安装 Python 3。
2. 在当前目录运行：

```powershell
python app.py
```

3. 打开：

```text
http://127.0.0.1:8000
```

## 运行时生成的数据文件

- `geocode_cache.json`（地址 -> 坐标缓存）
- `votes.db`（SQLite 投票存储）

## 说明

- 首次运行可能较慢，因为需要从 OpenStreetMap Nominatim 拉取坐标并缓存。
- 投票 API 本地运行、实现轻量，适合简单部署。
