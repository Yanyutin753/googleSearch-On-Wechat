import os
import requests
import json
from bot import bot_factory
from bridge.bridge import Bridge
from bridge.reply import Reply, ReplyType
from config import conf
from common.log import logger
from langchain.utilities import GoogleSerperAPIWrapper
import plugins
from plugins import Plugin, Event, EventContext, EventAction
from channel.chat_channel import check_contain, check_prefix
from channel.chat_message import ChatMessage
import random


@plugins.register(
    name="GoogleSearch",
    desire_priority=1,
    hidden=False,
    desc="A plugin that fetches daily search",
    version="0.1",
    author="yangyang",
)
class GoogleSearch(Plugin):
    def __init__(self):
        super().__init__()
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.serper_api_key = config["serper_api_key"]
                print("[GoogleSearch] 初始化")
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context 
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.warn(f"[GoogleSearch] init failed, {config_path} not found.")
            else:
                logger.warn("[GoogleSearch] init failed.")
            raise e

    def on_handle_context(self, e_context: EventContext):
        content = e_context["context"].content
        if content.startswith("搜索 "):
            self.handle_text_search(e_context, content[len("搜索 "):])
        elif content.startswith("搜图 "):
            self.handle_image_search(e_context, content[len("搜图 "):])
            

    def handle_text_search(self, e_context, query):
        cmsg : ChatMessage = e_context['context']['msg']
        session_id = cmsg.from_user_id
        os.environ["SERPER_API_KEY"] = self.serper_api_key
        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "gl": "cn",
            "hl": "zh-cn"
        })
        headers = {
            'X-API-KEY': self.serper_api_key,
            'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        query += response.text + "\n----------------\n"
        prompt = "你是一位群聊机器人，聊天记录已经在你的大脑中被你总结成多段摘要总结，你需要对它们进行摘要总结，最后输出一篇完整的摘要总结，用列表的形式输出。\n"
        btype = Bridge().btype['chat']
        bot = bot_factory.create_bot(Bridge().btype['chat'])
        session = bot.sessions.build_session(session_id, prompt)
        session.add_query(query)
        result = bot.reply_text(session)
        total_tokens, completion_tokens, reply_content = result['total_tokens'], result['completion_tokens'], result['content']
        logger.debug("[Summary] total_tokens: %d, completion_tokens: %d, reply_content: %s" % (total_tokens, completion_tokens, reply_content))
        reply = Reply()
        if completion_tokens == 0:
            reply = Reply(ReplyType.ERROR, "合并摘要失败，"+reply_content+"\n原始多段摘要如下：\n"+query)
        else:
            reply = Reply(ReplyType.TEXT,reply_content)     
        e_context['reply'] = reply
        e_context.action = EventAction.BREAK_PASS # 事件结束，并跳过处理context的默认逻辑

    def handle_image_search(self, e_context, query):
        url = "https://google.serper.dev/images"

        payload = json.dumps({
            "q": query,
            "gl": "cn",
            "hl": "zh-cn"
        })
        headers = {
            'X-API-KEY': self.serper_api_key,
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        if response.status_code == 200:
            data = response.json()

            if 'images' in data and len(data['images']) > 0:
                random_index = random.randint(0, 9)
                first_image = data['images'][random_index]

                if 'imageUrl' in first_image:
                    image_url = first_image['imageUrl']

                     # 如果是以 http:// 或 https:// 开头，且包含.jpg/.jpeg/.png/.gif/.webp，则认为是图片 URL
                    if (image_url.startswith("http://") or image_url.startswith("https://")):
                        response = requests.head(image_url)
                        if response.status_code == 200:
                            reply = Reply()
                            reply.type = ReplyType.IMAGE_URL
                            reply.content = image_url
                        else:
                            reply = Reply()
                            reply.type = ReplyType.TEXT
                            reply.content = "No imageUrl found in the first image."
                        
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                    else:
                        # 否则认为是普通文本
                        reply = Reply()
                        reply.type = ReplyType.TEXT
                        reply.content = image_url

                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                else:
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = "No imageUrl found in the first image."
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            else:
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "No images found in response."
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        else:
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = f"Request failed with status code: {response.status_code}\nResponse text: {response.text}"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def get_help_text(self, **kwargs):
        help_text = (
            "🥰输入 '搜索 <您需要搜索的内容>'，我会帮您进行文本搜索\n"
            "💌输入 '搜图 <您需要搜索的图片描述>'，我会帮您进行图像搜索"
        )
        return help_text
