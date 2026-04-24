# LSF文件转JSON文件Ver1.0

此工具用于把小E社引擎相关的 `.lsf` 资源描述文件批量转换为 `.json`。  
作者标识：ユイ可愛ね  
编译日期标识：26-4-25

软件标题：

```text
LSF文件转JSON文件Ver1.0（此工具针对小E社引擎开发  ユイ可愛ね制作  编译日期26-4-25）
```

## 功能

- 单个 `.lsf` 转 JSON
- 目录批量转换
- 可递归子目录
- 可保留目录结构
- 输出 records 原始坐标和 tag
- 输出 slot / variant / mid 拆分信息
- 输出 selection_groups，便于后续合成工具读取
- 提供 GUI 与命令行两种入口

## 运行 GUI

```bash
python main.py
```

或：

```bash
python -m lsf_to_json_converter gui
```

## 命令行示例

批量转换目录：

```bash
python main.py convert -i "E:/work3/output" -o "E:/work3/json" -r
```

扫描目录：

```bash
python main.py scan -i "E:/work3/output" -r
```

查看单个 LSF：

```bash
python main.py inspect "E:/work3/output/EV_B12.lsf"
```

查看 slot / variant：

```bash
python main.py slots "E:/work3/output/EV_B12.lsf" --variants
```

导出 records 表：

```bash
python main.py records "E:/work3/output/EV_B12.lsf" -o records.csv --format csv
```

直接输出单个完整 JSON：

```bash
python main.py dump "E:/work3/output/EV_B12.lsf" -o EV_B12.json
```

## 安装为命令

```bash
pip install -e .
lsf2json --version
lsf2json convert -i "E:/work3/output" -o "E:/work3/json" -r
```

## GitHub Actions

仓库内带有 `.github/workflows/build-windows.yml`，推送 tag 后可以自动打包 Windows exe：

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 许可证

MIT License。详见 [LICENSE](LICENSE)。
