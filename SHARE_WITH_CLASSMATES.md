# 洪策同学分享版

## 方式 A：发 GitHub 链接让同学本地运行

把这个仓库链接发给同学：

```text
https://github.com/ZKD-FDU/hongce
```

同学在自己的电脑上运行：

```bash
git clone https://github.com/ZKD-FDU/hongce.git
cd hongce
python3 -m pip install -r requirements.txt
python3 scripts/start_hongce.py
```

浏览器会自动打开：

```text
http://127.0.0.1:5173
```

如果没有自动打开，让同学手动复制这个地址到浏览器。

## 方式 B：发压缩包

如果同学不想用 Git，也可以把项目文件夹压缩后发给他。解压后进入项目根目录运行：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/start_hongce.py
```

浏览器会自动打开：

```text
http://127.0.0.1:5173
```

如果没有自动打开，手动复制这个地址到浏览器。

## 方式 C：同一个 Wi-Fi 下直接访问你的电脑

如果你和同学在同一个局域网，你可以在自己的电脑上运行：

```bash
HONGCE_HOST=0.0.0.0 HONGCE_PUBLIC_API_BASE=http://你的局域网IP:8000 python3 scripts/start_hongce.py
```

同学访问：

```text
http://你的局域网IP:5173
```

如果系统防火墙询问是否允许 Python 接收连接，需要允许。

## 运行环境

- 推荐 Python 3.11 或更新版本。
- 不需要外部大模型 Key。
- 不需要 Node/npm。
- 只需要运行 `python3 -m pip install -r requirements.txt` 安装 Python 依赖。

## 他可以操作什么

- 在“情景编辑器”选择 28 个应急管理部真实案例训练素材。
- 修改合成县域参数：脆弱人口比例、预警时刻、转移命令、危险到达、通信失败率、车辆、照护人员、担架、避难床位等。
- 点击“运行仿真”即时生成新的多智能体仿真结果。
- 在“政策对比”运行 A/B/C 批量实验，比较 S0-S5 政策。
- 查看事件流、叫应确认台、个体决策轨迹和复盘建议。

## 重要说明

- `127.0.0.1` 是每个人自己电脑上的本地地址，不能直接把你的 `127.0.0.1:5173` 发给同学当在线链接。
- 政策比较结果来自实际仿真运行，不是静态图表。
- 真实案例训练库来自应急管理部报告的结构化语料，运行时使用的是 `data/processed/` 下的小体积语料库。
- `data/raw/` 里的原始 PDF 和网页抓取结果体积较大，不是同学运行系统的必需文件。
