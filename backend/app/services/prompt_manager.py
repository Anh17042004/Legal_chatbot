import os
import yaml
from app.core.logger import logger
from pathlib import Path


class PromptManager:
    def __init__(self):
        self.prompts = {}
        self.prompt_file = Path(__file__).resolve().parent.parent / "prompts" / "system_prompts.yaml"

    def load_prompts(self):
        try:
            with open(self.prompt_file, 'r', encoding='utf-8') as file:
                self.prompts = yaml.safe_load(file)
            logger.info("✅ Đã load thành công cấu hình Prompts từ YAML.")
        except Exception as e:
            logger.error(f"❌ Lỗi khi load file Prompts: {e}")

    def get_prompt(self, category: str, version: str = None) -> str:
        """
        Lấy prompt theo category (rag_generation, query_rewriter).
        Nếu không truyền version, sẽ lấy active_version.
        """
        if category not in self.prompts:
            return ""
            
        category_data = self.prompts[category]
        target_version = version if version else category_data.get('active_version')
        
        return category_data.get('versions', {}).get(target_version, "")

# Singleton instance
prompt_manager = PromptManager()