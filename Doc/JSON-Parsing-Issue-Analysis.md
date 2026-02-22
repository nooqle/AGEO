# A1-A5 工具 JSON 解析问题深度分析报告

**日期**: 2026-01-31
**分析范围**: `aeo-platform/backend/app/tools/executors.py`

---

## 一、问题现象

在测试中观察到的错误：
```
Event: error - Failed to parse A1 output: Extra data: line 162 column 1 (char 5013)
```

这个错误表明 JSON 解析器在第 5013 个字符处发现了额外的数据，意味着提取的字符串包含了多个 JSON 对象或在 JSON 后面有额外内容。

---

## 二、当前解析逻辑分析

### 2.1 代码位置

JSON 解析逻辑在 `executors.py` 中出现 3 次：
- **A1 (品牌竞品分析)**: 第 115-121 行
- **A2 (营销画像生成)**: 第 191-197 行
- **A3 (问题模拟)**: 第 272-278 行

### 2.2 当前实现

```python
# 当前的 JSON 解析逻辑（A1/A2/A3 相同）
json_start = content.find("{")
json_end = content.rfind("}")
if json_start != -1 and json_end != -1:
    json_str = content[json_start:json_end + 1]
    result_data = json.loads(json_str)
else:
    result_data = json.loads(content)
```

### 2.3 问题分析

这个简单的解析方法存在**严重缺陷**：

#### 问题 1: 无法处理多个 JSON 对象

如果 LLM 输出包含多个 JSON 对象：
```
这是分析结果：
{"brand_profile": {...}}
补充说明：
{"additional_info": {...}}
```

`find("{")` 找到第一个 `{`，`rfind("}")` 找到最后一个 `}`，结果会包含两个 JSON 对象，导致 "Extra data" 错误。

#### 问题 2: 无法处理 JSON 后的文本

如果 LLM 在 JSON 后添加解释：
```
{"brand_profile": {...}}

以上是分析结果，如有问题请告知。
```

虽然 `rfind("}")` 会找到正确的位置，但如果 LLM 在解释中使用了 `{` 或 `}`，就会出问题。

#### 问题 3: 无法处理嵌套的 markdown code block

如果 LLM 使用 markdown 格式：
```
```json
{"brand_profile": {...}}
```

这里是分析说明...

```json
{"summary": {...}}
```
```

`rfind("}")` 会找到第二个 JSON 的 `}`，导致解析失败。

#### 问题 4: 无法处理 JSON 中的字符串包含 `{` 或 `}`

如果 JSON 中的字符串值包含花括号：
```json
{
  "description": "这是一个 {示例} 描述"
}
```

虽然这种情况下 `find/rfind` 通常能工作，但如果 LLM 在 JSON 外部也使用了花括号，就会出问题。

---

## 三、LLM 输出格式分析

### 3.1 Prompt 要求

查看 `prompts/brand_competition_agent.md`，prompt 要求 LLM：
```
你必须以 JSON 格式输出分析结果，格式如下：

```json
{
  "brand_profile": {...},
  "competitors": [...],
  ...
}
```
```

### 3.2 实际 LLM 输出

MiniMax M2.1 模型在使用 `reasoning_split=True` 时，输出结构为：
- `reasoning_details`: 思考过程（不包含在 content 中）
- `content`: 最终输出

但是，LLM 可能在 `content` 中输出：
1. 纯 JSON
2. Markdown code block 包裹的 JSON
3. JSON + 解释文本
4. 多个 JSON 对象

### 3.3 错误原因推断

错误 "Extra data: line 162 column 1 (char 5013)" 最可能的原因是：

**LLM 输出了多个 JSON 对象**，例如：
```
```json
{
  "brand_profile": {...},
  "competitors": [...],
  ...
}
```

以下是补充分析：

```json
{
  "additional_analysis": {...}
}
```
```

当前代码会提取从第一个 `{` 到最后一个 `}` 的所有内容，包含了两个 JSON 对象，导致解析失败。

---

## 四、影响范围

### 4.1 受影响的工具

| 工具 | 文件位置 | 解析逻辑 | 受影响 |
|------|---------|---------|--------|
| A1 (品牌竞品分析) | executors.py:115-121 | find/rfind | ✅ 是 |
| A2 (营销画像生成) | executors.py:191-197 | find/rfind | ✅ 是 |
| A3 (问题模拟) | executors.py:272-278 | find/rfind | ✅ 是 |
| A4 (答案抓取) | executors.py:308-418 | 使用现有 Agent | ❌ 否 |
| A5 (数据分析) | executors.py:420-570 | 使用现有 Agent | ❌ 否 |

### 4.2 问题严重程度

- **A1**: 🔴 高 - 作为第一个工具，失败会影响整个流程
- **A2**: 🟡 中 - 依赖 A1 输出，A1 失败则不会执行
- **A3**: 🟡 中 - 依赖 A1/A2 输出

---

## 五、修复方案

### 5.1 方案 A: 增强 JSON 提取逻辑（推荐）

使用更智能的 JSON 提取方法：

```python
import re

def extract_json_from_response(content: str) -> dict:
    """从 LLM 响应中提取 JSON。

    支持以下格式：
    1. 纯 JSON
    2. Markdown code block 包裹的 JSON
    3. JSON 前后有文本
    4. 多个 JSON 对象（只取第一个）
    """
    # 方法 1: 尝试提取 markdown code block 中的 JSON
    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_block_pattern, content)

    for match in matches:
        try:
            # 尝试解析每个 code block
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # 方法 2: 尝试找到完整的 JSON 对象（使用括号匹配）
    def find_json_object(text: str, start: int = 0) -> tuple[int, int] | None:
        """找到第一个完整的 JSON 对象的起止位置。"""
        brace_count = 0
        json_start = -1

        for i, char in enumerate(text[start:], start):
            if char == '{':
                if brace_count == 0:
                    json_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and json_start != -1:
                    return (json_start, i + 1)

        return None

    result = find_json_object(content)
    if result:
        json_str = content[result[0]:result[1]]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 方法 3: 直接尝试解析整个内容
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 方法 4: 回退到原有逻辑
    json_start = content.find("{")
    json_end = content.rfind("}")
    if json_start != -1 and json_end != -1:
        json_str = content[json_start:json_end + 1]
        return json.loads(json_str)

    raise ValueError("无法从响应中提取有效的 JSON")
```

### 5.2 方案 B: 使用 JSON 修复库

使用 `json_repair` 库自动修复常见的 JSON 格式问题：

```python
from json_repair import repair_json

def extract_json_from_response(content: str) -> dict:
    """使用 json_repair 库提取和修复 JSON。"""
    # 先尝试提取 markdown code block
    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_block_pattern, content)

    for match in matches:
        try:
            repaired = repair_json(match.strip())
            return json.loads(repaired)
        except:
            continue

    # 尝试修复整个内容
    try:
        repaired = repair_json(content)
        return json.loads(repaired)
    except:
        pass

    raise ValueError("无法从响应中提取有效的 JSON")
```

### 5.3 方案 C: 修改 Prompt 强制输出格式

在 prompt 中添加更严格的输出格式要求：

```markdown
## 输出格式要求

**⚠️ 严格要求**：
1. 只输出一个 JSON 对象，不要输出多个
2. 不要在 JSON 前后添加任何解释文本
3. 不要使用 markdown code block
4. 直接输出纯 JSON，例如：
   {"brand_profile": {...}, "competitors": [...]}
```

---

## 六、推荐修复方案

### 6.1 短期修复（推荐）

**采用方案 A**，创建一个通用的 JSON 提取函数，替换所有 A1-A3 工具中的解析逻辑。

**修改文件**: `executors.py`

**新增函数**:
```python
def _extract_json_from_response(self, content: str) -> dict:
    """从 LLM 响应中智能提取 JSON。"""
    import re

    # 方法 1: 尝试提取 markdown code block 中的 JSON
    json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_block_pattern, content)

    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # 方法 2: 使用括号匹配找到第一个完整的 JSON 对象
    brace_count = 0
    json_start = -1

    for i, char in enumerate(content):
        if char == '{':
            if brace_count == 0:
                json_start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and json_start != -1:
                json_str = content[json_start:i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # 继续查找下一个 JSON 对象
                    json_start = -1
                    continue

    # 方法 3: 直接尝试解析整个内容
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    raise ValueError("无法从响应中提取有效的 JSON")
```

**修改 A1/A2/A3 的解析逻辑**:
```python
# 替换原有的 find/rfind 逻辑
try:
    result_data = self._extract_json_from_response(content)
except ValueError as e:
    yield {
        "type": "error",
        "error": f"Failed to parse output: {str(e)}",
        "raw_response": content
    }
    return
```

### 6.2 长期优化

1. **统一输出格式**: 考虑使用 structured output（如果 MiniMax 支持）
2. **添加重试机制**: 如果解析失败，可以要求 LLM 重新输出
3. **输出验证**: 使用 Pydantic 模型验证输出结构

---

## 七、影响评估

### 7.1 修复影响范围

| 文件 | 修改行数 | 风险等级 |
|------|---------|---------|
| `executors.py` | ~50 行 | 🟢 低 |

### 7.2 测试建议

1. 测试纯 JSON 输出
2. 测试 markdown code block 包裹的 JSON
3. 测试 JSON + 解释文本
4. 测试多个 JSON 对象
5. 测试嵌套 JSON 结构

---

## 八、总结

### 问题根因
当前的 JSON 解析逻辑过于简单，使用 `find("{")` 和 `rfind("}")` 无法正确处理 LLM 输出的多种格式。

### 影响范围
A1、A2、A3 三个工具受影响，其中 A1 影响最大。

### 推荐方案
采用方案 A，创建智能 JSON 提取函数，支持多种输出格式。

### 修复优先级
🔴 **高** - 影响核心功能，建议尽快修复。

---

**报告编制**: Claude Opus 4.5
**日期**: 2026-01-31
