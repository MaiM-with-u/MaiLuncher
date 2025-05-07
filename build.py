import os
import subprocess
import sys
import shutil
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="MaiLuncher 打包工具 - 基于Nuitka的打包脚本")
    
    # 基本选项
    parser.add_argument("--no-console", action="store_true", help="不显示控制台窗口")
    parser.add_argument("--clean", action="store_true", help="打包前清理dist目录")
    parser.add_argument("--output-name", default="MaiLuncher", help="输出文件名")
    
    # 高级选项
    parser.add_argument("--cache-dir", default=None, help="指定Nuitka缓存目录")
    parser.add_argument("--exclude", nargs='+', default=["config"], help="指定不跟踪的包/模块列表")
    parser.add_argument("--include-data", nargs='+', default=[], 
                        help="额外包含的数据目录，格式为source=target")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--jobs", type=int, default=None, help="并行编译的作业数")
    parser.add_argument("--onefile", action="store_true", 
                        help="创建单文件可执行程序(会导致启动速度变慢，但分发更方便)")
    
    return parser.parse_args()

def build_app():
    args = parse_args()
    print("===== MaiLuncher 打包工具 =====")
    print("开始打包应用程序...")
    
    # 创建输出目录
    output_dir = "dist"
    if args.clean and os.path.exists(output_dir):
        print(f"清理输出目录: {output_dir}")
        shutil.rmtree(output_dir)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 构建基础Nuitka命令
    cmd = [
        "python", "-m", "nuitka",
        "--standalone" if not args.onefile else "--onefile",  # 独立还是单文件模式
        "--follow-imports",                         # 跟踪所有导入
    ]
    
    # 添加图标
    icon_path = "src/asset/icons/icon_256x256.ico"
    if os.path.exists(icon_path):
        cmd.append(f"--windows-icon-from-ico={icon_path}")
    else:
        print(f"警告: 图标文件未找到于 {icon_path}")
    
    # 添加无控制台选项
    if args.no_console:
        cmd.append("--windows-disable-console")
    
    # 添加资源文件 - 确保包含所有资源
    cmd.append("--include-data-dir=src/MaiGoi/assets=src/MaiGoi/assets")  # 始终包含基础资源
    for data_item in args.include_data:
        if "=" in data_item:
            cmd.append(f"--include-data-dir={data_item}")
    
    # 添加包含包
    cmd.append("--include-package=src")  # 包含基础包
    cmd.append("--include-package=flet")  # 确保flet模块被包含
    
    # 添加排除跟踪
    for exclude_item in args.exclude:
        cmd.append(f"--nofollow-import-to={exclude_item}")
    
    # 添加缓存目录
    if args.cache_dir:
        cmd.append(f"--cache-dir={args.cache_dir}")
    
    # 添加并行编译作业数
    if args.jobs:
        cmd.append(f"--jobs={args.jobs}")
    
    # 添加调试选项
    if args.debug:
        cmd.append("--debug")
    
    # 添加输出选项
    cmd.extend([
        f"--output-dir={output_dir}",               # 输出目录
        f"--output-filename={args.output_name}",    # 输出文件名
        "main.py"                               # 入口文件
    ])
    
    # 执行打包命令
    print(f"执行命令: {' '.join(cmd)}")
    print("\n正在编译，这可能需要几分钟时间...\n")
    
    try:
        result = subprocess.run(cmd)
        
        # 输出结果
        if result.returncode == 0:
            print("\n✅ 打包成功!")
            
            if args.onefile:
                exe_path = os.path.join(output_dir, f"{args.output_name}.exe")
                print(f"\n单文件应用程序位置: {exe_path}")
            else:
                dist_path = os.path.join(output_dir, f"{args.output_name}.dist")
                exe_path = os.path.join(output_dir, f"{args.output_name}.exe")
                
                print(f"\n应用程序位置:")
                print(f"  可执行文件: {exe_path}")
                print(f"  分发目录: {dist_path}")
            
            print("\n使用方法:")
            print(f"  1. 直接运行 {args.output_name}.exe")
            print(f"  2. 如果遇到问题，可以试试从命令行启动")
            
            print("\n常见问题排查:")
            print("  1. 如果提示缺少DLL，请确保安装了最新的Visual C++ Redistributable")
            print("  2. 如果提示Python相关错误，尝试重新打包时添加 --standalone 选项")
            print("  3. 如果资源文件丢失，请检查资源路径是否正确")
        else:
            print("\n❌ 打包失败!")
            print("\n可能的原因及解决方案:")
            print("  1. 确保安装了所有依赖: pip install -r requirements.txt")
            print("  2. 确保Nuitka安装正确: pip install nuitka --upgrade")
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