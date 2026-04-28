import json
from ollama import AsyncClient

from app.core.config import settings
from app.core.logger import logger
from app.services.prompt_manager import prompt_manager


DEFAULT_RESULT = {
    "intent": "unclear",
    "confidence": 0.0,
    "policy": "fallback",
}

RESPONSE_MAP = {
    "greeting": "Xin chào! Tôi là Trợ lý Pháp luật Hôn nhân và Gia đình. Tôi có thể hỗ trợ gì cho bạn hôm nay?",
    "farewell": "Tạm biệt! Nếu có câu hỏi gì khác về pháp luật, hãy quay lại nhé. Chúc bạn một ngày tốt lành!",
    "acknowledge": "Tôi rất vui vì đã giúp được bạn. Bạn có câu hỏi gì khác về vấn đề pháp lý này không?",
    "capability": "Tôi là AI pháp luật, được tạo bởi Tuấn Anh, chuyên hỗ trợ các vấn đề pháp luật như ly hôn, quyền nuôi con, chia tài sản, cấp dưỡng, đăng ký kết hôn và các thủ tục pháp lý liên quan.",
    "out_of_domain": "Tôi hiện chỉ hỗ trợ các vấn đề liên quan đến pháp luật. Vui lòng đặt câu hỏi trong lĩnh vực pháp luật để tôi hỗ trợ tốt nhất.",
    "toxic": "Tôi ở đây để hỗ trợ bạn về các vấn đề pháp luật. Nếu câu trả lời trước chưa phù hợp, bạn có thể nói rõ hơn để tôi hỗ trợ tốt hơn.",
    "unsafe": "Tôi không thể hỗ trợ nội dung này.",
    "unclear": "Xin vui lòng mô tả rõ hơn vấn đề pháp lý để tôi hỗ trợ chính xác hơn.",
}

VALID_INTENTS = {
    "greeting",
    "farewell",
    "acknowledge",
    "capability",
    "legal_query",
    "out_of_domain",
    "toxic",
    "unsafe",
    "unclear",
}


class IntentRouter:
    def _build_classifier_messages(self, user_message: str, history: list[dict] | None) -> list[dict]:
        # Send messages in chat order so the model sees true roles instead of a flattened blob.
        history = history or []
        recent = history[-6:]

        messages = [
            {
                "role": "system",
                "content": prompt_manager.get_prompt("intent_classifier"),
            }
        ]

        for msg in recent:
            role = msg.get("role", "user")
            content = str(msg.get("content", "")).strip()
            if not content or role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})
        return messages

    async def classify_intent(self, user_message: str, history: list[dict] | None = None) -> dict:
        try:
            client = AsyncClient(
                host=settings.LLM_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.OLLAMA_API_KEY}"
                } if settings.OLLAMA_API_KEY else {}
            )

            response = await client.chat(
                model=settings.LLM_MODEL,
                messages=self._build_classifier_messages(user_message, history),
                options={"temperature": 0.0},
            )

            raw = response.get("message", {}).get("content", "").strip()
            logger.info(f"🧠 Intent raw: {raw}")

            data = json.loads(raw)

            intent = data.get("intent", "unclear")
            confidence = float(data.get("confidence", 0))
            policy = data.get("policy", "fallback")

            if intent not in VALID_INTENTS or confidence < 0.75:
                return DEFAULT_RESULT

            return {
                "intent": intent,
                "confidence": confidence,
                "policy": policy,
            }

        except Exception as e:
            logger.warning(f"⚠️ Intent Router error: {str(e)}")
            return DEFAULT_RESULT

    def get_fast_response(self, intent: str):
        if intent == "legal_query":
            return None
        return RESPONSE_MAP.get(intent, RESPONSE_MAP["unclear"])


intent_router = IntentRouter()


async def stream_fast_reply(answer: str):
    yield f"data: {json.dumps({'type': 'chunk', 'content': answer}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"