# zcode-vision-helper

为 ZCode 纯文本主模型"借一双眼睛"的**脚本看图版**：收到图片时自动委派 `vision-helper` 子代理，由它调用脚本，把图片直接发给你在 ZCode 设置里配置的视觉模型并转述结果。

> 本项目基于 [50kg/zcode-deepseek-eye](https://github.com/50kg/zcode-deepseek-eye)（MIT License）改进，保留其 `setup-vision-helper` skill 与路由规则，新增"脚本眼睛"方案。感谢原作者。

## 为什么要脚本版

上游方案的子代理通过 Read 工具读图（`model` 字段指向视觉模型），实测有几类翻车场景：

1. **模态门控误伤**：部分 OpenAI 兼容的自定义视觉模型明明支持图片输入，但配成子代理模型后，Read 工具报「模型不支持图像输入」——ZCode 对自定义模型 modalities 字段的门控与 Read 通路不互通；
2. **思考档位报错**：子代理 `model` 字段指向一个没选过"思考档位"的自定义模型时，子代理直接启动失败（reasoning-level-missing）；
3. **Windows PATH 坑**：很多 Windows 机器只有 `py` 启动器而没有 `python` 命令，子代理里写死的命令跑不通。

脚本版把"看图"从子代理的 Read 通路挪到 HTTP 直连，绕开以上全部问题：

- 子代理**不写 `model` 字段**（跟随主模型，只当"跑腿"，永远不会踩思考档位的坑），用 Bash 调脚本；
- 脚本把图片 base64 后直接调用你在 ZCode 设置里配好的视觉模型（OpenAI 兼容 `/chat/completions`），**理论上任何 OpenAI 兼容的视觉模型都能当眼睛**；
- 输出强制 UTF-8（避免中文 Windows 的 GBK 编码崩溃）、`max_tokens` 放大到 4000（避免思考过程挤占额度导致描述截断）、HTTP 错误会把响应体打出来（方便排查密钥/额度问题）。

## 安全性

- **本仓库不包含任何 API Key、账号、路径等敏感信息**；
- 脚本运行时从你本机的 `~/.zcode/v2/config.json` 动态读取对应 provider 的 `apiKey` / `baseURL`（就是你在 ZCode 设置里填的那个），也可以用环境变量覆盖；
- 换密钥只需要在 ZCode 设置里改，脚本永远不用动。
- 脚本内置安全约束：接口地址仅允许 http/https 且解析后不得指向内网/环回/保留地址、禁用重定向；图片路径必须绝对、规范化后不得含 `..`、必须位于目录白名单内（默认用户主目录，可用 `VISION_EYE_ALLOWED_DIRS` 扩展）且仅限常见图片格式。

## 安装

前提：已在 ZCode 设置里添加一个支持图片的模型并填好 API Key（例如 `agnes-2.5-flash`、`qwen3-vl-flash`、`glm-4.6v-flash` 等，任选其一）。

**方式 A：配合 skill（推荐）**

1. 把本仓库 `skills/setup-vision-helper/` 整个文件夹复制到 `~/.zcode/skills/`（Windows 即 `C:\Users\<你的用户名>\.zcode\skills\`）；
2. 完全退出 ZCode 再重开，新会话输入 **`帮我配置视觉助手`**，按提示选择你的"眼睛"模型——skill 会创建 Read 型子代理和路由规则；
3. 用本仓库 `agents/vision-helper.md` **覆盖** skill 生成的 `~/.zcode/agents/vision-helper.md`，并把 `agents/vision_api.py` 复制到 `~/.zcode/agents/`；
4. 再完全重启一次 ZCode，贴图测试。

**方式 B：全手动**

1. 把 `agents/vision_api.py`、`agents/vision-helper.md` 复制到 `~/.zcode/agents/`；
2. 把 `templates/agents-rule.md.snippet` 的内容追加到 `~/.zcode/AGENTS.md`（没有就创建）；
3. 完全退出 ZCode 再重开，贴图测试。

> 路径说明：脚本默认眼睛模型为 `agnes-2.5-flash`，脚本会自动在 config.json 里寻找配置了该模型的 provider；用其他模型时设置环境变量 `VISION_EYE_MODEL`（详见脚本头部注释）。Windows 上子代理会优先用 `py` 启动器，其次 `python`；macOS/Linux 用 `python3`。

## 使用

配置完成后无需任何操作：会话里发图片，主模型看不到图像内容时会自动派 `vision-helper` 去读并转述。

删除：新会话对 ZCode 说"删除视觉助手"。

## 目录结构

```
├── LICENSE                                 # MIT（原项目版权声明，按许可要求保留）
├── README.md
├── skills/setup-vision-helper/SKILL.md     # 上游原版 skill（未改动）
├── agents/vision-helper.md                 # 脚本版子代理定义（无 model 字段）
├── agents/vision_api.py                    # 看图脚本（动态读配置，零内置密钥）
└── templates/agents-rule.md.snippet        # 图片路由规则
```

## License

MIT。基于 [50kg/zcode-deepseek-eye](https://github.com/50kg/zcode-deepseek-eye) 修改，原项目版权与许可见 [LICENSE](LICENSE)。
