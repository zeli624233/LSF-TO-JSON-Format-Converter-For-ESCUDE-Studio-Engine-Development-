# 从源码运行与开发

## 推荐环境

- Python 3.10+
- Windows 10/11 或其他支持 tkinter 的系统

## 创建虚拟环境

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -e .
```

## 运行

```bash
python main.py
python main.py convert -i input_dir -o json_dir -r
```

## 开发说明

核心代码在：

- `lsf_to_json_converter/core.py`：LSF 解析与 JSON 生成
- `lsf_to_json_converter/cli.py`：命令行
- `lsf_to_json_converter/gui.py`：GUI
