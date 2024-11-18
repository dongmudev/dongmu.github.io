import os
import re
import requests
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup
import frontmatter
import html2text
from slugify import slugify
from collections import Counter
from zhipuai import ZhipuAI
import mimetypes
import uuid
import shutil

client = ZhipuAI(api_key="30e7f246c91c2bc062887ec8aab16ff3.YyZwIQuO1eIwV8gw") 

def html_to_markdown(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # 删除包含javascript:void(0)的链接
    for link in soup.find_all('a', href=re.compile(r'javascript:void\(0\)')):
        link.decompose()

    # 删除包含日期时间的元素
    for time_elem in soup.find_all('em', id='publish_time'):
        time_elem.decompose()

    # 处理带有 class="code-snippet__fix" 的代码片段
    for code_snippet in soup.find_all(class_='code-snippet__fix'):
        code_text = code_snippet.get_text()
        # 将代码片段转换为 Markdown 格式
        code_markdown = f'\n```\n{code_text}\n```\n'
        code_snippet.replace_with(code_markdown)

    # 将处理后的 HTML 转换为 Markdown
    h = html2text.HTML2Text()
    h.ignore_links = False
    markdown_content = h.handle(str(soup))
    
    # 使用正则表达式删除日期时间行
    markdown_content = re.sub(r'_\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2}_\s*____\n?', '', markdown_content)
    
    # 使用正则表达式删除任何可能剩余的包含javascript:void(0)的行
    markdown_content = re.sub(r'.*javascript:void\(0\).*\n?', '', markdown_content)
    
    # 删除文章开头的标题和下划线（更严格的匹配模式）
    markdown_content = re.sub(r'^#\s+.*?\n\n_{2,}\n', '', markdown_content, flags=re.MULTILINE)
    markdown_content = re.sub(r'^#\s+.*?\n+', '', markdown_content, flags=re.MULTILINE)
    # 删除任何剩余的连续下划线行
    markdown_content = re.sub(r'^\_{2,}\s*$\n?', '', markdown_content, flags=re.MULTILINE)
    

    
    # 删除"心智工具箱"相关的图片和文本行
    markdown_content = re.sub(r'^.*阳志平的私人写作空间.*\n', '', markdown_content, flags=re.MULTILINE)

    # 清理可能剩余的连续星号
    markdown_content = re.sub(r'\*{4,}', '', markdown_content)
    
    # 修改正则表达式以匹配实际格式
    pattern = r'(!\[.*?\]\(\.\/assets\/[^\)]+\))\s*\n\s*([^\n]+?)\s*\n'

    # 保留图片但删除其后的第一行文字
    markdown_content = re.sub(pattern, r'\1\n\n', markdown_content)

    return markdown_content.strip()

def download_and_save_image(url, save_dir, article_date, article_dir):
    try:
        if url.startswith('./assets/'):
            # 获取原始图片路径（从文章目录中的assets文件夹）
            original_path = os.path.join(article_dir, url)
            if os.path.exists(original_path):
                # 生成新的文件名：日期-原文件名
                original_filename = os.path.basename(url)
                new_filename = f"{article_date}-{original_filename}"
                save_path = os.path.join(save_dir, new_filename)
                
                # 复制文件
                shutil.copy2(original_path, save_path)
                return os.path.join('/assets/post_images', new_filename)
            return None
            
        return None
    except Exception as e:
        print(f"复制图片失败: {url}. 错误: {e}")
    return None

def analyze_content_for_tags(content):
    # 定义栏目对应的关键词
    category_keywords = {
        '人生发展问答': ['职业发展', '人生规划', '个人成长', '目标设定', '决策', '选择'],
        '美好生活': ['生活方式', '幸福', '快乐', '健康', '生活质量', '生活态度'],
        '咨询手记': ['心理咨询', '案例', '治疗', '心理健康', '咨询经验'],
        '角色榜样': ['榜样', '成功人士', '典范', '影响力', '领袖'],
        '东木和我': ['东木咨询', '服务介绍', '团队', '理念', '方法论']
    }

    # 计算关键词出现次数
    category_count = Counter()
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            count = len(re.findall(keyword, content, re.IGNORECASE))
            category_count[category] += count

    # 选择最相关的类别作为标签
    threshold = 2
    tags = [category for category, count in category_count.items() if count >= threshold]
    
    return tags

def generate_filename(title, content):
    prompt = f"""
    请你根据以下文章内容,取英文标题,全小写,最多五个单词,方便被seo捕捉到。格式为每个单词使用"-"分隔:

    标题: {title}
    内容: {content[:4000]}  # 只取前4000个字符,避免超出token限制
    """
    
    response = client.chat.completions.create(
        model="glm-4-flash",
        messages=[{"role": "user", "content": prompt}]
    )
    
    filename = response.choices[0].message.content.strip()
    return filename

def convert_html_to_md(input_folder, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    image_dir = os.path.join('assets', 'post_images')
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)
    
    # 遍历html文件夹下的所有子文件夹
    for root, dirs, files in os.walk(input_folder):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(.+)', dir_name)
            
            if match and 'index.html' in os.listdir(dir_path):
                date = match.group(1)
                title = match.group(2)
                
                # 读取index.html文件
                html_path = os.path.join(dir_path, 'index.html')
                with open(html_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                # 转换内容
                markdown_content = html_to_markdown(content)
                
                # 处理图片时传入文章目录路径
                def replace_image(match):
                    img_url = match.group(1)
                    new_path = download_and_save_image(img_url, image_dir, date, dir_path)
                    if new_path:
                        return f'![]({new_path})'
                    return match.group(0)
                
                # 查找并替换所有图片链接
                img_pattern = r'!\[.*?\]\((\.\/assets\/[^\s\)]+)\)'
                markdown_content = re.sub(img_pattern, replace_image, markdown_content)
                
                # 生成文件名
                try:
                    generated_filename = generate_filename(title, markdown_content)
                    output_filename = f"{date}-{generated_filename}.md"
                except Exception as e:
                    print(f"生成文件名时出错: {e}. 使用默认文件名。")
                    output_filename = f"{date}-{slugify(title, max_length=50)}.md"
                
                output_path = os.path.join(output_folder, output_filename)
                
                # 获取标签
                tags = analyze_content_for_tags(markdown_content)
                
                # 写入文件
                with open(output_path, 'w', encoding='utf-8') as file:
                    file.write('---\n')
                    file.write('layout: post\n')
                    file.write(f'title: "{title}"\n')
                    file.write(f'date: {date}\n')
                    file.write(f'tags: {tags}\n')
                    file.write('style: huoshui\n')
                    file.write('---\n\n')
                    file.write(markdown_content)
                
                print(f'已转换: {dir_name}/index.html -> {output_filename}')

# 使用示例
input_folder = 'html'
output_folder = '_posts'
convert_html_to_md(input_folder, output_folder)