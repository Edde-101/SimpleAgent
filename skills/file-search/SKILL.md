---
name: file-search
description: 在本地文件系统中搜索文件名包含指定关键词的文件，递归遍历用户主目录
user-invocable: true
argument-hint: "[keyword]"
---

# 文件搜索技能

## 功能概述

在用户主目录（`Path.home()`）下递归搜索文件名中包含指定关键词的所有文件，返回匹配文件的完整路径列表。

## 执行方式

通过 Python 脚本执行搜索：

```bash
python -c "from skills.file-search.file_search import file_search; import json; print(json.dumps(file_search('<keyword>'), ensure_ascii=False, indent=2))"
```

或直接导入模块调用 `file_search(keyword)` 函数。

## 搜索范围

- 根目录：`Path.home()`（用户主目录）
- 搜索方式：`os.walk` 递归遍历所有子目录
- 匹配规则：文件名包含关键词（大小写敏感，取决于操作系统）

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 文件名搜索关键词 |

## 输出格式

返回 `list[str]`，每项为匹配文件的完整绝对路径。未找到匹配时返回空列表 `[]`。

## 使用示例

**用户输入**：`/file_search keyword=report`

**执行流程**：
1. 提取关键词 `report`
2. 调用 `file_search("report")`
3. 返回匹配结果：如 `["/home/user/Documents/report_2024.pdf", "/home/user/Downloads/report_template.docx"]`
4. 以列表或表格形式展示给用户，如果结果过多则提供摘要

**用户输入**：`/file_search keyword=.env`

**输出示例**：
```
找到 2 个匹配文件:
  - C:\Users\xxx\project\.env
  - C:\Users\xxx\other\.env.local
```

## 注意事项

- 搜索从用户主目录开始，范围可能很大，搜索时间取决于文件数量
- 仅在文件名中匹配，不搜索文件内容
- 返回路径使用操作系统原生格式（Windows 使用反斜杠，Linux/Mac 使用正斜杠）
- 不需要用户确认即可直接执行，这是纯读取操作
