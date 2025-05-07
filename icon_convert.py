from PIL import Image
import os

def convert_png_to_ico(input_path, output_path, sizes=None):
    """
    将PNG图像转换为ICO格式
    
    参数:
        input_path: 输入PNG文件路径
        output_path: 输出ICO文件路径
        sizes: 图标尺寸列表，默认为[16, 32, 48, 64, 128, 256]
    """
    if sizes is None:
        sizes = [16, 32, 48, 64, 128, 256]
    
    try:
        # 打开原始图像
        img = Image.open(input_path)
        
        # 创建不同尺寸的图像
        icon_images = []
        for size in sizes:
            # 调整大小并保持纵横比
            resized_img = img.copy()
            resized_img.thumbnail((size, size), Image.Resampling.LANCZOS)
            icon_images.append(resized_img)
        
        # 保存为ICO文件
        icon_images[0].save(
            output_path, 
            format='ICO', 
            sizes=[(img.width, img.height) for img in icon_images],
            append_images=icon_images[1:]
        )
        
        print(f"转换成功! ICO文件已保存到: {output_path}")
        return True, icon_images
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False, None

def save_all_icon_sizes(input_file, output_dir, sizes=None):
    """
    将PNG图像转换为不同尺寸的图标，并分别保存
    
    参数:
        input_file: 输入PNG文件路径
        output_dir: 输出目录
        sizes: 图标尺寸列表，默认为[16, 32, 48, 64, 128, 256]
    """
    if sizes is None:
        sizes = [16, 64, 256]
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取输入文件名（不带扩展名）
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    
    try:
        # 打开原始图像
        img = Image.open(input_file)
        
        # 为每个尺寸创建并保存图像
        for size in sizes:
            # 调整大小并保持纵横比
            resized_img = img.copy()
            resized_img.thumbnail((size, size), Image.Resampling.LANCZOS)
            
            # 保存为PNG文件
            # output_path = os.path.join(output_dir, f"{base_name}_{size}x{size}.png")
            # resized_img.save(output_path, format='PNG')
            # print(f"已保存 {size}x{size} 图标到: {output_path}")
            
            # 保存为ICO文件
            output_path_ico = os.path.join(output_dir, f"{base_name}_{size}x{size}.ico")
            resized_img.save(output_path_ico, format='ICO')
            print(f"已保存 {size}x{size} ICO图标到: {output_path_ico}")
        
        # 同时生成一个包含所有尺寸的ICO文件
        ico_output_path = os.path.join(output_dir, f"{base_name}.ico")
        success, _ = convert_png_to_ico(input_file, ico_output_path, sizes)
        
        if success:
            print(f"已创建包含所有尺寸的ICO文件: {ico_output_path}")
            return True
        
    except Exception as e:
        print(f"处理失败: {str(e)}")
    
    return False

if __name__ == "__main__":
    # 输入文件路径
    input_file = "src/MaiGoi/assets/icon.png"
    
    # 输出目录路径
    output_dir = "src/asset/icons"
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 输入文件 {input_file} 不存在!")
    else:
        # 1. 转换和保存所有尺寸的图标
        save_all_icon_sizes(input_file, output_dir)
        
        # 2. 同时保存一份完整的ICO在MaiGoi/assets目录
        output_file = os.path.join("src/MaiGoi/assets", "icon.ico")
        convert_png_to_ico(input_file, output_file) 