from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Bạn là trợ lý AI hỗ trợ livestream bán hàng trên Facebook, trả lời bằng tiếng Việt.
Vai trò: tư vấn viên thân thiện, ngắn gọn, giúp khách hàng đặt hàng nhanh chóng.
Quy tắc:
- Trả lời ngắn (1-2 câu), lịch sự, thân thiện, dùng "ạ" cuối câu
- Không bịa thông tin sản phẩm nếu không có dữ liệu
- Nếu không chắc, nhẹ nhàng yêu cầu khách gửi thêm mã sản phẩm, màu, hoặc size
- Luôn xưng "em", gọi khách là "mình" hoặc tên khách"""


class GeminiClient:
    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            import google.generativeai as genai
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is not set")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._model = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                system_instruction=_SYSTEM_PROMPT,
            )
        return self._model

    def _generate_sync(self, prompt: str) -> str:
        import google.generativeai as genai
        model = self._get_model()
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=150,
            ),
        )
        return response.text.strip()

    async def generate(self, prompt: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._generate_sync, prompt)


gemini_client = GeminiClient()
