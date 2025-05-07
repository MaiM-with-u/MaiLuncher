# MaiLuncher 打包指南

这个文档介绍如何使用打包工具将 MaiLuncher 打包为可执行文件。

## 打包方式选择

本项目提供两种打包方式：
1. 使用 Nuitka 打包（推荐）- 性能更好，打包结果更小
2. 使用 PyInstaller 打包 - 兼容性更好，更容易处理特殊依赖

## Nuitka 打包方式

### 基本用法

最简单的打包命令：

```bash
python build.py
```

这将创建一个带有控制台窗口的可执行文件，放置在 `dist` 目录下。

### 常用选项

#### 隐藏控制台窗口

```bash
python build.py --no-console
```

#### 清理旧的构建文件

```bash
python build.py --clean
```

#### 指定输出文件名

```bash
python build.py --output-name MyApp
```

### 高级选项

#### 创建单文件可执行程序

```bash
python build.py --onefile
```
注意：单文件模式启动较慢，但分发更方便。

#### 排除特定模块或包

```bash
python build.py --exclude config logs temp
```

#### 包含额外的数据文件

```bash
python build.py --include-data "data=data" "images=res/images"
```

#### 调试模式

```bash
python build.py --debug
```

#### 加速编译（多核）

```bash
python build.py --jobs 4
```

## PyInstaller 打包方式

PyInstaller 是另一种流行的 Python 应用打包工具，有时在特定场景下比 Nuitka 更适用。

### 基本用法

```bash
python build_pyinstaller.py
```

这会创建一个多文件分发包，排除 config 目录。

### 常用选项

#### 隐藏控制台窗口

```bash
python build_pyinstaller.py --no-console
```

#### 清理旧的构建文件

```bash
python build_pyinstaller.py --clean
```

#### 指定输出文件名

```bash
python build_pyinstaller.py --output-name MyApp
```

#### 指定自定义图标

```bash
python build_pyinstaller.py --icon path/to/icon.png
```

### 高级选项

#### 添加额外的数据文件

```bash
python build_pyinstaller.py --additional-data "data;data" "images;images"
```
注意：PyInstaller 使用分号(;)分隔源路径和目标路径，而不是等号(=)。

#### 排除额外的模块

```bash
python build_pyinstaller.py --exclude-modules pandas numpy
```

#### 调试模式

```bash
python build_pyinstaller.py --debug
```

## 常见问题解决

### 1. 执行文件无法运行，提示Python相关错误

Nuitka 方案：
```bash
python -m pip install --upgrade nuitka
python build.py --clean
```

PyInstaller 方案：
```bash
python -m pip install --upgrade pyinstaller
python build_pyinstaller.py --clean
```

### 2. 缺少图片或资源文件

Nuitka：使用 `--include-data` 选项
PyInstaller：使用 `--additional-data` 选项

### 3. 打包过程中断或失败

两种方案都可以使用 `--debug` 选项查看详细错误。

### 4. 找不到flet插件错误

如果使用Nuitka打包时出现相关错误，不用担心，我们的脚本已经更新来解决这个问题。现在脚本直接包含flet包，而不是作为插件。

### 5. 图标转换问题

为避免图标转换问题，我们已从Nuitka打包脚本中移除了图标设置。图像资源将被正常包含在分发包中。

### 6. 运行时DLL错误

如果运行时出现缺少DLL的错误，比如提示"找不到python311.dll"，有几种解决方案：

1. 使用更新版本的PyInstaller脚本，它会自动打包Python解释器
   ```bash
   python build_pyinstaller.py --clean
   ```

2. 确保Python安装在系统中，并且PATH环境变量包含Python目录

3. 如果仍然有问题，可以尝试Nuitka打包：
   ```bash
   python build.py --clean
   ```

### 7. 哪种打包方式更好？

- Nuitka：生成的可执行文件运行更快，但打包过程更复杂
- PyInstaller：打包过程更简单，但生成的可执行文件可能更大，运行更慢

根据你的需求选择合适的打包方式。

## 完整参数列表

运行以下命令查看所有可用选项：

```bash
python build.py --help
```

或者

```bash
python build_pyinstaller.py --help
``` 