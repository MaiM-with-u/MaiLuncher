import os
import subprocess
import sys
import shutil
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="MaiLuncher PyInstaller打包工具")
    
    # 基本选项
    parser.add_argument("--no-console", action="store_true", help="不显示控制台窗口")
    parser.add_argument("--clean", action="store_true", help="打包前清理dist目录")
    parser.add_argument("--icon", default="src/asset/icons/icon_256x256.ico", help="指定应用图标路径")
    parser.add_argument("--icon-size", default="256", choices=["16", "32", "48", "64", "128", "256"], 
                        help="指定图标大小 (16, 32, 48, 64, 128, 256)")
    parser.add_argument("--output-name", default="MaiLuncher", help="输出文件名")
    parser.add_argument("--output-dir", default="dist_pyins", help="指定输出目录")
    
    # 高级选项
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--additional-data", nargs='+', default=[], 
                        help="额外包含的数据文件，格式为source;dest")
    parser.add_argument("--exclude-modules", nargs='+', default=[], 
                        help="排除特定模块")
    
    return parser.parse_args()

def build_app():
    args = parse_args()
    print("===== MaiLuncher PyInstaller打包工具 =====")
    print("开始打包应用程序...")
    
    # 检查PyInstaller是否安装
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller 安装完成")
    
    # 如果指定了图标大小，使用对应大小的图标
    if args.icon_size != "256" or not os.path.exists(args.icon):
        default_icon = f"src/asset/icons/icon_{args.icon_size}x{args.icon_size}.ico"
        if os.path.exists(default_icon):
            args.icon = default_icon
            print(f"使用图标: {args.icon}")
        else:
            print(f"警告: 指定大小的图标 {default_icon} 不存在，将使用默认图标")
    
    # 创建输出目录
    output_dir = args.output_dir
    if args.clean and os.path.exists(output_dir):
        print(f"清理输出目录: {output_dir}")
        shutil.rmtree(output_dir)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 创建build目录在output_dir下
    build_dir = os.path.join(output_dir, "build")
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)
    
    # 方法1: 不使用spec文件，直接使用命令行参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", args.output_name,
        "--distpath", output_dir,
        "--workpath", build_dir,  # 设置工作目录为build_pyins/build
        "--noconfirm",
        "--log-level", "INFO",
        "--clean" if args.clean else "",
    ]
    
    # 添加无控制台选项
    if args.no_console:
        cmd.append("--windowed")
    else:
        cmd.append("--console")
    
    # 添加图标
    if os.path.exists(args.icon):
        cmd.extend(["--icon", args.icon])
    
    # 添加排除选项
    cmd.append("--exclude-module")
    cmd.append("config")
    for module in args.exclude_modules:
        cmd.append("--exclude-module")
        cmd.append(module)
    
    # 添加数据文件
    cmd.extend(["--add-data", "src/MaiGoi/assets;src/MaiGoi/assets"])
    cmd.extend(["--add-data", "src/asset/icons;src/asset/icons"])
    for data_item in args.additional_data:
        if ";" in data_item:
            cmd.extend(["--add-data", data_item])
    
    # 添加隐藏导入
    for module in ["flet", "psutil", "toml", "tomlkit", "httpx", "ansi2html", "flet_core", "flet_runtime"]:
        cmd.extend(["--hidden-import", module])
    
    # 添加主脚本
    cmd.append("main.py")
    
    # 过滤掉空字符串
    cmd = [item for item in cmd if item]
    
    # 执行打包命令
    print(f"执行命令: {' '.join(cmd)}")
    print("\n正在编译，这可能需要几分钟时间...\n")
    
    try:
        result = subprocess.run(cmd)
        
        # 输出结果
        if result.returncode == 0:
            print("\n✅ 打包成功!")
            
            dist_path = os.path.join(output_dir, args.output_name)
            exe_path = os.path.join(dist_path, f"{args.output_name}.exe")
            
            print(f"\n应用程序位置:")
            print(f"  可执行文件: {exe_path}")
            print(f"  分发目录: {dist_path}")
            
            print("\n使用方法:")
            print(f"  1. 直接运行 {args.output_name}.exe")
            print(f"  2. 如果遇到问题，可以试试从命令行启动")
            
            print("\n常见问题排查:")
            print("  1. 如果提示缺少DLL，请确保安装了最新的Visual C++ Redistributable")
            print("  2. 如果提示模块找不到，检查是否有隐式依赖未被检测到")
            print("  3. 如果资源文件丢失，尝试使用--additional-data选项添加")
        else:
            print("\n❌ 打包失败!")
            print("\n可能的原因及解决方案:")
            print("  1. 确保安装了所有依赖: pip install -r requirements.txt")
            print("  2. 确保PyInstaller安装正确: pip install pyinstaller --upgrade")
            print("  3. 尝试添加 --debug 选项查看详细错误")
    except Exception as e:
        print(f"\n❌ 打包过程中出现异常: {e}")
    
    print("\n打包过程完成!")
    
if __name__ == "__main__":
    try:
        build_app()
    except KeyboardInterrupt:
        print("\n\n打包过程被用户中断!")
        sys.exit(1) 