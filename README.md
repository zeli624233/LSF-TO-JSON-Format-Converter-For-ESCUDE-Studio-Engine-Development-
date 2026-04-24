# LSF TO JSON Format Converter (For ESCUDE Studio Engine Development)
将LSF文件转换成JSON格式，支持批量导出，脚本执行，GUI图形界面...（该工具是针对小E社引擎开发，由废村少女CG和人物立绘合成器项目衍生而来）

# LSF文件转JSON文件Ver1.0

一个用于把 `.lsf` 资源索引文件转换为可读 `.json` 的小工具。支持图形界面、命令行、目录批量转换、递归扫描、记录表导出和索引生成，方便后续做 PNG 合成、资源分析或调试。

## 功能

- 支持单个 `.lsf` 文件转换。
- 支持目录批量转换，可递归子目录。
- 支持保留原目录结构或平铺输出。
- 输出完整 records：坐标、尺寸、PNG 名称、tag 原始值、slot/variant/mid/high 字节。
- 输出 slots / selection_groups，方便后续合成工具识别身体、表情、红晕、饰品、特殊层、圣光等选项。
- 支持 records 导出为 CSV / TSV / JSON。
- 支持 validate、scan、inspect、slots、index 等调试命令。
- GUI 使用 Python 标准库 tkinter，无运行时第三方依赖。
- MIT 协议，可发布到 GitHub。

## 目录结构

```text
.
├─ assets/                         图标文件
├─ lsf_to_json_converter/          主程序包
│  ├─ cli.py                       命令行入口
│  ├─ core.py                      LSF 解析与 JSON 生成
│  ├─ gui.py                       GUI 界面
│  └─ __main__.py                  python -m 入口
├─ main.py                         兼容入口
├─ build_exe.bat                   Windows 打包 GUI + 控制台版
├─ build_exe_gui.bat               Windows 打包 GUI 版
├─ build_exe_console.bat           Windows 打包控制台版
├─ version_info.txt                Windows exe 版本信息
├─ pyproject.toml                  Python 项目信息
└─ LICENSE                         MIT 协议
```



可用命令：

| 命令 | 作用 |
|---|---|
| `gui` | 打开图形界面 |
| `convert` / `batch` | 单文件或目录批量转换 JSON |
| `scan` / `ls` / `list` | 扫描 LSF 文件列表 |
| `inspect` / `info` | 查看单个 LSF 的画布、记录数、槽位分类 |
| `slots` | 查看 slot / variant 明细 |
| `records` / `dump-records` | 导出 records 表，支持 CSV / TSV / JSON |
| `dump` | 单个 LSF 直接输出完整 JSON 到终端或文件 |
| `validate` / `check` | 批量检查 LSF 是否能解析 |
| `index` | 为目录生成 LSF 索引 JSON |
| `version` | 显示版本 |

查看帮助：

```bat
python main.py --help
python main.py convert --help
python main.py records --help
```

### 批量转换

把目录里的 LSF 全部转成 JSON：

```bat
python main.py convert -i "E:\work3\Haison_FD2\output" -o "E:\work3\Haison_FD2\json" -r
```

只转换匹配文件，并排除测试文件：

```bat
python main.py convert -i "E:\work3\output" -o "E:\work3\json" -r --include "EV_*.lsf" --exclude "*test*"
```

先预览输出位置，不实际写文件：

```bat
python main.py convert -i "E:\work3\output" -o "E:\work3\json" -r --dry-run
```

转换并保存统计与索引：

```bat
python main.py convert -i "E:\work3\output" -o "E:\work3\json" -r --summary "E:\work3\summary.json" --index "E:\work3\index.json"
```

常用参数：

```text
-r, --recursive             递归处理子目录
--flat                      不保留原目录结构，全部输出到一个目录
--preserve-tree             保留原目录结构，默认开启
--overwrite                 覆盖已有 JSON，默认开启
--skip-existing             已有 JSON 时跳过
--suffix .lsf.json          自定义输出后缀
--compact                   输出紧凑 JSON，不缩进
--no-layers                 不输出 layers 兼容字段
--dry-run                   只显示将要转换的结果，不实际写文件
--summary summary.json      额外保存转换统计
--index index.json          额外生成转换索引
--json                      命令行输出 JSON 格式统计
--quiet                     减少普通文本输出
--fail-fast                 第一个错误就停止
```

### 查看单个 LSF

```bat
python main.py inspect "E:\work3\output\st\3\01_Kagome.lsf"
python main.py slots "E:\work3\output\st\3\01_Kagome.lsf" --variants
```

### 导出 records 表

```bat
python main.py records "E:\work3\output\st\3\01_Kagome.lsf" -o "E:\work3\records.csv" --format csv
python main.py records "E:\work3\output\st\3\01_Kagome.lsf" -o "E:\work3\records.tsv" --format tsv
python main.py records "E:\work3\output\st\3\01_Kagome.lsf" -o "E:\work3\records.json" --format json
```

### 直接 dump 完整 JSON

```bat
python main.py dump "E:\work3\output\st\3\01_Kagome.lsf" -o "E:\work3\01_Kagome.json"
```

### 校验目录

```bat
python main.py validate -i "E:\work3\output" -r
```

### 生成索引

```bat
python main.py index -i "E:\work3\output" -o "E:\work3\lsf_index.json" -r --with-slots
```

## JSON 输出说明

生成的 JSON 主要包含：

- `header`：LSF 文件头信息。
- `canvas_width / canvas_height`：画布尺寸。
- `records`：每条 PNG 记录的坐标、尺寸、tag、slot、variant、mid 等原始信息。
- `slots`：按 slot/variant 分组后的结构。
- `selection_groups`：按工具推断出的可选组合项，便于合成工具读取。
- `fixed_record_indices`：默认固定图层。
- `layers`：兼容部分旧合成工具的图层字段。

注意：`selection_groups` 的分类是基于目前分析过的小E社引擎样本做的启发式规则；如果遇到新结构，建议优先查看 `records` 和 `slots` 原始数据。


## 协议

本项目使用 MIT License。详见 [LICENSE](LICENSE)。

