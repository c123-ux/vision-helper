#!/usr/bin/env python3
# vision_api.py — ZCode 视觉助手"脚本眼睛"看图脚本
#
# 用法:
#   Windows:     py vision_api.py <图片路径> [用户问题]
#   macOS/Linux: python3 vision_api.py <图片路径> [用户问题]
#
# 原理: 把图片 base64 后，直接调用你在 ZCode 设置里配置的视觉模型
#       （OpenAI 兼容 /chat/completions 接口），绕开子代理 Read 工具的模态门控。
#
# 密钥安全: 本脚本不内置任何密钥。apiKey / baseURL 运行时动态读取
#   ~/.zcode/v2/config.json 中"包含目标模型的 provider"。可用环境变量覆盖:
#     VISION_EYE_MODEL        眼睛模型 id（默认 agnes-2.5-flash，换其他视觉模型就设它）
#     VISION_EYE_API_KEY      直接指定密钥（优先于 config.json）
#     VISION_EYE_BASE_URL     直接指定接口地址（优先于 config.json，一般以 /v1 结尾）
#     VISION_EYE_ALLOWED_DIRS 允许读取图片的额外根目录（路径分隔符连接，默认仅用户主目录）

import sys, os, json, base64, socket, ipaddress, pathlib
import urllib.request, urllib.error, urllib.parse

DEFAULT_MODEL = 'agnes-2.5-flash'
CONFIG_PATH = pathlib.Path.home() / '.zcode' / 'v2' / 'config.json'

MIME_MAP = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp'}

def find_provider(model):
    """在 config.json 里找包含该模型的 provider，返回 (baseURL, apiKey)。"""
    try:
        conf = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return '', ''
    for prov in conf.get('provider', {}).values():
        if model in prov.get('models', {}):
            opts = prov.get('options', {})
            return opts.get('baseURL', ''), opts.get('apiKey', '')
    return '', ''

def safe_url(u):
    """仅允许 http/https，且解析出的 IP 不得指向环回/私网/保留/链路本地地址。"""
    try:
        p = urllib.parse.urlparse(u)
        if p.scheme not in ('http', 'https') or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_loopback or ip.is_private or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False
    except (ValueError, socket.gaierror, OSError):
        return False
    return True

def load_allowed_dirs():
    """允许读取图片的根目录白名单（pathlib 列表）。默认仅用户主目录——
    已覆盖桌面/下载/图片/".zcode" 图片缓存等常见截图位置。"""
    dirs = [pathlib.Path.home().resolve()]
    for d in os.environ.get('VISION_EYE_ALLOWED_DIRS', '').split(os.pathsep):
        if d.strip():
            dirs.append(pathlib.Path(d.strip()).expanduser().resolve())
    return dirs

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print('用法: py vision_api.py <图片路径> [用户问题]')
        sys.exit(1)

    model = os.environ.get('VISION_EYE_MODEL', DEFAULT_MODEL)
    baseurl = os.environ.get('VISION_EYE_BASE_URL', '')
    apikey = os.environ.get('VISION_EYE_API_KEY', '')
    if not baseurl or not apikey:
        cfg_url, cfg_key = find_provider(model)
        baseurl = baseurl or cfg_url
        apikey = apikey or cfg_key
    if not baseurl or not apikey:
        print(f'错误: 没有找到模型 {model} 的接口配置。')
        print('请先在 ZCode 设置里添加一个支持图片的模型并填好 API Key，')
        print('或设置环境变量 VISION_EYE_MODEL / VISION_EYE_API_KEY / VISION_EYE_BASE_URL。')
        sys.exit(1)
    if not safe_url(baseurl):
        print(f'错误: 接口地址不可用（仅允许 http/https，且不得指向内网/环回/保留地址）：{baseurl}')
        sys.exit(1)

    # ── 图片路径安全校验（防目录穿越/任意文件读取，四重约束缺一不可）──
    img = pathlib.Path(sys.argv[1]).resolve()      # 1) 规范化为绝对真实路径
    if '..' in img.parts:                          # 2) 显式禁止任何 .. 路径段
        print(f'ERROR: 图片路径不允许包含 ".."：{sys.argv[1]}')
        sys.exit(1)
    allowed_dirs = load_allowed_dirs()
    if not any(img.is_relative_to(d) for d in allowed_dirs):   # 3) 目录白名单
        print(f'ERROR: 图片不在允许读取的目录白名单内（默认仅用户主目录，'
              f'可用环境变量 VISION_EYE_ALLOWED_DIRS 扩展）：{img}')
        sys.exit(1)
    if img.suffix.lower() not in MIME_MAP or not img.is_file():  # 4) 仅图片文件
        print(f'ERROR: 只允许读取图片文件（扩展名限 '
              f'{", ".join(sorted(MIME_MAP))}）：{img}')
        sys.exit(1)

    question = sys.argv[2] if len(sys.argv) > 2 else \
        '请详细描述这张图片，包括所有可见的文字、图像元素、颜色、场景，最后总结这张图是什么类型（截图/照片/图表/代码等）。'

    b64 = base64.b64encode(img.read_bytes()).decode()

    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': question},
            {'type': 'image_url', 'image_url': {'url': f'data:{MIME_MAP[img.suffix.lower()]};base64,{b64}'}}
        ]}],
        'max_tokens': 4000
    }).encode()

    req = urllib.request.Request(
        baseurl.rstrip('/') + '/chat/completions',
        data=body,
        headers={'Authorization': 'Bearer ' + apikey, 'Content-Type': 'application/json'}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=180) as resp:
            msg = json.loads(resp.read())['choices'][0]['message']
        print(f"[思考过程]\n{msg.get('reasoning_content', '')}\n\n[图片描述]\n{msg.get('content', '')}")
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'replace')[:500]
        except Exception:
            pass
        print(f'API 调用失败：HTTP {e.code}: {detail}')
        sys.exit(1)
    except Exception as e:
        print(f'API 调用失败：{e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
