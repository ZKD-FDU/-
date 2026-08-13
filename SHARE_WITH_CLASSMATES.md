# 洪策同学分享版

## 最简单启动

同学解压项目后，在项目根目录运行：

```bash
python3 scripts/start_hongce.py
```

浏览器会自动打开：

```text
http://127.0.0.1:5173
```

如果没有自动打开，手动复制这个地址到浏览器。

## 依赖

需要 Python 3.11+。如果提示缺少 `pydantic`，先运行：

```bash
python3 -m pip install pydantic
```

## 演示要点

- “运行仿真”会调用本地 API 生成新的多智能体仿真结果。
- “政策对比”里的 A/B/C 实验不是固定图表，会批量运行 S0-S5 后汇总。
- 没有外部模型 Key 也能完整运行。

## 如果想局域网共享

在你的电脑上运行：

```bash
HONGCE_HOST=0.0.0.0 HONGCE_PUBLIC_API_BASE=http://你的局域网IP:8000 python3 scripts/start_hongce.py
```

同学访问：

```text
http://你的局域网IP:5173
```

如果系统防火墙询问是否允许 Python 接收连接，需要允许。
