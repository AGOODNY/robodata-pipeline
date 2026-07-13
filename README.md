# RoboData Pipeline

## 1. 简介

项目采用前后端分离结构：

```text
robodata-pipeline/
├── backend/   # 后端接口、数据读取、媒体访问与格式转换
└── frontend/  # Web 页面与数据可视化
```

主要技术栈：

- 前端：Vue 3、TypeScript、Vite、Vue Router、ECharts
- 后端：Python、FastAPI、Uvicorn、Pydantic
- 数据处理：NumPy、Pandas、PyArrow、h5py
- 图像与视频：Pillow、PyAV/FFmpeg
- 数据格式：Raw、LeRobot 2.1、LeRobot 3.0、HDF5

平台默认把 `robodata-pipeline` 所在目录的上一级目录作为数据根目录，并扫描其中包含 `meta/info.json` 的数据集。转换结果保存在数据根目录下的 `outputs/` 文件夹中，源数据不会被修改。

## 2. 如何启动前后端服务

以下命令均从项目根目录 `robodata-pipeline` 开始执行。建议分别打开两个 PowerShell 窗口运行后端和前端。

### 2.1 启动后端

首次运行时，创建 Python 虚拟环境并安装依赖：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖安装完成后，可以使用项目提供的脚本启动后端：

```powershell
.\start_backend.cmd
```

也可以直接使用 Uvicorn 启动，并启用开发时自动重载：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端默认地址为 `http://127.0.0.1:8000`，接口文档地址为 `http://127.0.0.1:8000/docs`。

如需使用其他数据目录，请在启动后端前设置 `ROBODATA_DATA_ROOT`：

```powershell
$env:ROBODATA_DATA_ROOT="D:\path\to\datasets"
.\start_backend.cmd
```

### 2.2 启动前端

首次运行时安装前端依赖：

```powershell
cd frontend
npm.cmd install
```

启动前端开发服务：

```powershell
npm.cmd run dev
```

浏览器访问 `http://127.0.0.1:5173` 即可打开平台。

如果当前 PowerShell 允许执行 `npm.ps1`，也可以将上述命令中的 `npm.cmd` 替换为 `npm`。

## 3. 平台的功能

### 数据集管理与识别

- 自动扫描本地数据根目录以及 `outputs/` 转换结果目录。
- 识别 Raw、LeRobot 2.1、LeRobot 3.0 和 HDF5 数据集。
- 展示数据集格式、机器人类型、Episode 数量、帧数和采样率等概要信息。

### 数据集与 Episode 浏览

- 查看数据集元数据、特征定义、任务信息和统计信息。
- 按 Episode 浏览任务、帧数、时间范围及相机资源。
- 播放 LeRobot 视频，并查看 observation state、action 等时序曲线。
- 浏览 Raw 数据集的相机帧、机械臂关节、末端位姿和夹爪等原始数据。
- 播放 HDF5 中保存的 RGB 帧，并同步查看状态与动作曲线。

### 数据格式转换

- 支持 Raw、LeRobot 2.1、LeRobot 3.0 和 HDF5 之间适用的格式转换。
- 转换前执行 Episode 级预检，统计有效 Episode、输出帧数和清理结果。
- Raw 转换支持 Joint、TCP 和 Joint + TCP 动作模式，以及任务文本覆盖。
- 支持对带停止标记的 Raw Episode 执行尾部智能清理，不修改原始数据。
- 后台显示转换阶段、Episode、帧数和百分比进度，并支持取消任务。

