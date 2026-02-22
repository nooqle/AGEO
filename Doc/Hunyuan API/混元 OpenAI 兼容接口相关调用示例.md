元 OpenAI 兼容接口相关调用示例
最近更新时间：2026-01-08 10:25:11

我的收藏
本页目录：
对话(chat completions)
多轮对话(chat completions)
图生文(如 hunyuan-vision)
Function Calling
OpenAI 兼容参数
混元自定义参数
与OpenAI的差异
/v1/chat/completions
/v1/embeddings
Embedding
混元 API 兼容了 OpenAI 的接口规范，这意味着您可以直接使用 OpenAI 官方提供的 SDK 来调用混元大模型。您仅需要将 base_url 和 api_key 替换成混元的相关配置，不需要对应用做额外修改，即可无缝将您的应用切换到混元大模型。
base_url：https://api.hunyuan.cloud.tencent.com/v1。
api_key：需在控制台 API Key 页面进行创建，操作步骤请参考 API Key 管理。
接口请求地址完整路径：https://api.hunyuan.cloud.tencent.com/v1/chat/completions。
第三方软件集成混元，您可参见 第三方软件集成混元指南 。
调用情况可在 控制台 中查看。计费详情请参见 混元生文计费概述。
混元生文 hunyuan 接口默认限制为5个并发，限额由主子账号共享。
说明：
并发：是指能同时处理的会话数量。例如接口默认提供 m 个并发数，代表最多能同时处理 m 个已提交的会话，需要等待 m 个会话中的任一个会话处理完毕后才能开始处理下一个会话。
对话(chat completions)
cURL
Python
NodeJS
Golang
curl https://api.hunyuan.cloud.tencent.com/v1/chat/completions \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $HUNYUAN_API_KEY" \
-d '{
  "model": "hunyuan-turbos-latest",
  "messages": [
        {
            "role": "user",
            "content": "Say this is a test."
        }
    ],
  "enable_enhancement": true
}'
﻿
多轮对话(chat completions)
多轮对话是指携带上下文的对话，用户请求时需将之前所有对话历史（即多条 user 和 assistant ）拼接好,  传递给混元/chat/completions接口，即可实现多轮对话。
cURL
Python
NodeJS
Golang
curl --location 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions' \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $HUNYUAN_API_KEY" \
--data '{
  "model": "hunyuan-turbos-latest",
  "messages": [
        {
            "role": "user",
            "content": "What'\''s the highest mountain in the world? Keep it short."
        },
        {
            "role": "assistant",
            "content": "Mount Everest."
        },
        {
            "role": "user",
            "content": "What is the second?"
        }
    ],
  "enable_enhancement": true
}'
﻿
图生文(如 hunyuan-vision)
图生文(Image-to-Text)，是一种输入图片和文本，输出文本的大模型能力。混元的 vision 系列模型均可参考此文档，相关模型可参见 产品概述 。
ImageUrl.Url 支持图片链接和图片 base64 两种方式。其中图片 base64 的格式为："data:image/jpeg;base64,xxxxxxx"（注意：data:image/jpeg;base64之后的逗号需使用英文逗号）
下面是 jpeg 图片转 base64的各语言代码示例 （其他图片格式注意修改为对应的 MIME 类型，例如： image/png，image/webp，image/bmp 等）：
Python
NodeJS
Golang
import base64
﻿
with open("1.jpeg", 'rb') as image_file:
    encoded_image = base64.b64encode(image_file.read())
    print("data:image/jpeg;base64,"+encoded_image.decode('utf-8'))
cURL
Python
NodeJS
Golang
curl --location 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions' \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $HUNYUAN_API_KEY" \
--data '{
  "model": "hunyuan-vision",
  "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What'\''s in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://qcloudimg.tencent-cloud.cn/raw/42c198dbc0b57ae490e57f89aa01ec23.png"
                    }
                }
            ]
        }
    ]
}'
﻿
Function Calling
function call 是指模型在回答用户问题时，调用外部函数或API来获得信息或与外部系统交互的能力。
function call 使用流程（以获取某地温度举例）：
定义函数 get_weather。
第一次请求对话接口：传递用户问题和函数定义（方法名称、描述、参数列表），由模型选择合适的函数并填充函数的参数。
第一次接收模型的响应：在客户侧调用函数获得结果（函数需要由客户的代码来调用，模型只会给出要调用的函数和参数而不会执行调用）。
第二次请求对话接口：在第一次的请求基础上，附加上第一次的响应和函数调用的结果，放到多轮上下文中，再次请求模型。
第二次接收模型的响应：模型生成最终结果。
﻿
第一次请求示例：
cURL
Python
NodeJS
Golang
curl --location 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions' \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $HUNYUAN_API_KEY" \
--data '{
  "model": "hunyuan-turbos-latest",
  "messages": [
        {
            "role": "user",
            "content": "What'\''s the weather like in Paris today?"
        }
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current temperature for provided coordinates in celsius.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number"
                        },
                        "longitude": {
                            "type": "number"
                        }
﻿
                    },
                    "required": [
                        "latitude","longitude"
                    ]
                }
            }
        }
    ]
}'
第一次响应示例：
JSON
{
  "id": "cabe32d2b30dd30ac3d7aad02f235dd4",
  "choices": [
    {
      "finish_reason": "tool_calls",
      "index": 0,
      "message": {
        "content": "调用天气查询工具（get_weather）来获取巴黎的天气信息。\n\t\n\t用户想要知道今天巴黎的天气。我需要调用天气查询工具（get_weather）来获取巴黎的天气信息。",
        "role": "assistant",
        "tool_calls": [
          {
            "id": "call_cvdrgkk2c3mceb26d7sg",
            "function": {
              "arguments": "{\"latitude\":48.8566,\"longitude\":2.3522}",
              "name": "get_weather"
            },
            "type": "function",
            "index": 0
          }
        ]
      }
    }
  ],
  "created": 1742452818,
  "model": "hunyuan-turbos-latest",
  "object": "chat.completion",
  "system_fingerprint": "",
  "usage": {
    "completion_tokens": 48,
    "prompt_tokens": 22,
    "total_tokens": 70
  }
}
第二次请求示例：
cURL
Python
NodeJS
Golang
curl --location 'https://api.hunyuan.cloud.tencent.com/v1/chat/completions' \
-H "Content-Type: application/json" \
-H "Authorization: Bearer $HUNYUAN_API_KEY" \
--data '{
  "model": "hunyuan-turbos-latest",
  "messages": [
        {
            "role": "user",
            "content": "What'\''s the weather like in Paris today?"
        },
        {
            "role": "assistant",
            "content": "调用天气查询工具（get_weather）来获取巴黎的天气信息。\n\t\n\t用户想要知道今天巴黎的天气。我需要调用天气查询工具（get_weather）来获取巴黎的天气信息。",
            "tool_calls": [
                {
                    "id": "call_cvdu67s2c3mafqgr1g6g",
                    "function": {
                    "arguments": "{\"latitude\":48.8566,\"longitude\":2.3522}",
                    "name": "get_weather"
                    },
                    "type": "function",
                    "index": 0
                }
            ]
        },
        {
            "role": "tool",
            "tool_call_id": "call_cvdu67s2c3mafqgr1g6g",
            "content": "11.7"
        }
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current temperature for provided coordinates in celsius.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number"
                        },
                        "longitude": {
                            "type": "number"
                        }
﻿
                    },
                    "required": [
                        "latitude","longitude"
                    ]
                }
            }
        }
    ]
}'
第二次响应示例：
JSON
{
  "id": "b03283653e27bc78a9c095699cfbc123",
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "content": "The current temperature in Paris is 7.6°C.",
        "role": "assistant"
      }
    }
  ],
  "created": 1742453367,
  "model": "hunyuan-turbos-latest",
  "object": "chat.completion",
  "system_fingerprint": "",
  "usage": {
    "completion_tokens": 24,
    "prompt_tokens": 71,
    "total_tokens": 95
  },
  "note": "以上内容为AI生成，不代表开发者立场，请勿删除或修改本标记"
}
之后可以继续进行对话。
OpenAI 兼容参数
参数名称
必选
类型
默认值
描述
model
是
string
无
模型名称，可选值参考 产品概述 中混元生文模型列表。
示例值：hunyuan-turbos-latest
messages
是
object[]
无
聊天上下文信息。相关字段可参考上文调用示例。
说明：
长度最多为 40，按对话时间从旧到新在数组中排列。
message.role 可选值：system、user、assistant、 tool（ function call 场景）。
messages 中 content 总长度不能超过模型输入长度上限（可参考 产品概述 文档），超过则会截断最前面的内容，只保留尾部内容。
stream
否
boolean
false
流式调用开关。
说明：
未传值时默认为非流式调用（false）。
流式调用时以 SSE 协议增量返回结果（返回值取 choices[n].delta 中的值，需要拼接增量数据才能获得完整结果）。
非流式调用时：
 调用方式与普通 HTTP 请求无异。
接口响应耗时较长，如需更低时延建议设置为 true。
只返回一次最终结果（返回值取 choices[n].message 中的值）。
             示例值：false
max_tokens
否
integer
4096
限制一次请求中模型生成 completion 的最大 token 数。输入 token 和输出 token 的总长度受模型的上下文长度的限制。
seed
否
integer
无
说明： 
1. 确保模型的输出是可复现的。
2. 取值区间为非0正整数，最大值10000。 
3. 非必要不建议使用，不合理的取值会影响效果。
示例值：1
stop
否
string[]
无
自定义结束生成字符串。
调用 OpenAI 接口时，如果您指定了 stop 参数, 模型会停止在匹配到 stop 的内容之前。
在调用混元接口时，会停止在匹配到 stop 的内容之后。
说明：未来我们可能会修改此行为以便和 OpenAI 保持一致。但是目前有使用该参数的情况下，开发者需要注意该参数是否会对应用造成影响，以及未来该行为调整时带来的影响。
temperature
否
number
无
说明：
影响模型输出多样性，模型已有默认参数，不传值时使用各模型推荐值，不推荐用户修改。
取值区间为 [0.0, 2.0]。较高的数值会使输出更加多样化和不可预测，而较低的数值会使其更加集中和确定。
top_p
否
number
0
说明：
影响输出文本的多样性。模型已有默认参数，不传值时使用各模型推荐值，不推荐用户修改。
取值区间为 [0.0, 1.0]。取值越大，生成文本的多样性越强。
tools
否
object[]
无
可调用的工具列表，相关字段可参考上文调用示例。
tool_choice
否
object
无
工具使用选项，可选值包括 none、auto、custom。
说明：
仅对 hunyuan-turbos、hunyuan-functioncall 模型生效。
none：不调用工具。
     auto：模型自行选择生成回复或调用工具。
     custom：强制模型调用指定的工具。
未设置时，默认值为 auto。
     示例值：auto
stream_options
否
object
无
流式输出相关选项。只有在 stream 参数为 true 时，才可设置此参数。
﻿
混元自定义参数
参数名称
必选
类型
默认值
描述
citation
否
boolean
false
搜索引文角标开关。
说明：
配合 enable_enhancement 和 search_info 参数使用。打开后，回答中命中搜索的结果会在片段后增加角标标志，对应 search_info 列表中的链接。
false：开关关闭；true：开关打开。
未传值时默认开关关闭（false）。
enable_enhancement
否
boolean
false
功能增强（如搜索）开关。
说明：
hunyuan-lite 无功能增强（如搜索）能力，该参数对 hunyuan-lite 版本不生效。
未传值时默认关闭开关。
关闭时将直接由主模型生成回复内容，可以降低响应时延（对于流式输出时的首字时延尤为明显）。但在少数场景里，回复效果可能会下降。
安全审核能力不属于功能增强范围，不受此字段影响。
2025年04月20日 00:00:00起，由默认开启状态转为默认关闭状态。
enable_multimedia
否
boolean
false
多媒体开关。
详细介绍请阅读 多媒体介绍 中的说明。
说明：
该参数目前仅对白名单内用户生效，如您想体验该功能请 联系我们。
该参数仅在功能增强（如搜索）开关开启（enable_enhancement=true）并且极速版搜索开关关闭（enable_speed_search=false）时生效。
hunyuan-lite 无多媒体能力，该参数对 hunyuan-lite 版本不生效。
未传值时默认关闭。
开启并搜索到对应的多媒体信息时，会输出对应的多媒体地址，可以定制个性化的图文消息。
enable_recommended_questions
否
boolean
false
推荐问答开关。
说明：
未传值时默认关闭。
开启后，在返回值的最后一个包中会增加 recommended_questions 字段表示推荐问答， 最多返回3条。
force_search_enhancement
否
boolean
false
强制搜索增强开关。
说明：
未传值时默认关闭。
开启后，将强制走AI搜索，当 AI 搜索结果为空时，由大模型回复兜底话术。
search_info
否
boolean
false
在值为 true 且命中搜索时，接口会返回 search_info。
与OpenAI的差异
/v1/chat/completions
stop
调用 OpenAI 的接口时，如果您指定了 stop 参数, 模型会停止在匹配到 stop 的内容之前。
在调用混元接口时，会停止在匹配到 stop 的内容之后。
以原始输出 “我是一个AI助手可以帮助您在不同方面做出更好的决策，解答您的疑问并提供可靠的信息。”为例：
类型
stop 参数
模型输出
OpenAI
助手
我是一个 AI
混元
助手
我是一个 AI 助手
说明：
未来我们可能会修改此行为以便和 OpenAI 保持一致。
但是目前有使用该参数的情况下，开发者需要注意该参数是否会对应用造成影响，以及未来该行为调整时带来的影响。
stream_options
当流式返回且 stream_options.include_usage=true 时，会在最后一个数据块中返回 usage 信息。
/v1/embeddings
embedding 接口目前仅支持 input 和 model 参数，model 当前固定为 hunyuan-embedding，dimensions 固定为 1024。
说明：
我们将努力保证混元与 OpenAI 的兼容性，但是仍然会存在一些细微的差异（通常来说并不会破坏整体的兼容性或者影响功能的使用）。
本文档会列出混元兼容接口与 OpenAI 的差异，开发者可以自行检查并评估对您应用的影响。
Embedding
cURL
curl --location 'https://api.hunyuan.cloud.tencent.com/v1/embeddings' \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer $HUNYUAN_API_KEY' \
--data '{
  "model": "hunyuan-embedding",
  "input": "你好"
}'
输出示例：
{
    "object": "list",
    "data": [
        {
            "index": 0,
            "embedding": [
                -0.0009261319064535201,
                -0.01005222275853157,
                ......
            ],
            "object": "embedding"
        }
    ],
    "model": "hunyuan-embedding",
    "usage": {
        "prompt_tokens": 3,
        "total_tokens": 3
    }
}