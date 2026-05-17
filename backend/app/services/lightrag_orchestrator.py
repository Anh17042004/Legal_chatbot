import os
from pathlib import Path

from lightrag import LightRAG, QueryParam
from app.infrastructure.llm.ollama_service import custom_ollama_model_complete
from lightrag.utils import EmbeddingFunc

from app.core.config import settings
from app.core.logger import logger
from app.infrastructure.llm.embedding_service import embedding_service
from app.services.prompt_manager import prompt_manager
from app.infrastructure.llm.rerank_service import rerank_service


class LightRAGOrchestrator:
    def __init__(self):
        self.rag = None
        project_root = Path(__file__).resolve().parents[3]
        self.working_dir = str(project_root / "rag_storage")
        self.pg_workspace = settings.POSTGRES_WORKSPACE

    def _build_lightrag_postgres_env(self) -> dict[str, str]:
        return {
            "POSTGRES_HOST": settings.POSTGRES_HOST,
            "POSTGRES_PORT": str(settings.POSTGRES_PORT),
            "POSTGRES_USER": settings.POSTGRES_USER,
            "POSTGRES_PASSWORD": settings.POSTGRES_PASSWORD,
            "POSTGRES_DATABASE": settings.POSTGRES_DATABASE,
            "POSTGRES_ENABLE_VECTOR": "true" if settings.POSTGRES_ENABLE_VECTOR else "false",
            "POSTGRES_WORKSPACE": self.pg_workspace,
        }

    def _configure_lightrag_postgres_env(self):
        os.environ.update(self._build_lightrag_postgres_env())

    def _build_rerank_func(self):
        """Tạo rerank function nếu ENABLE_RERANK=True."""
        if not settings.ENABLE_RERANK:
            logger.info("Rerank: DISABLED")
            return None

        rerank_service.load_model()
        logger.info(f"Rerank: ENABLED ({settings.RERANK_MODEL})")
        return rerank_service.rerank

    async def initialize(self):
        logger.info(f"Khoi tao LightRAG tai: {self.working_dir}")
        os.makedirs(self.working_dir, exist_ok=True)

        self._configure_lightrag_postgres_env()
        logger.info(f"LightRAG PG workspace: {self.pg_workspace}")

        embedding_service.load_model()

        rerank_func = self._build_rerank_func()

        self.rag = LightRAG(
            working_dir=self.working_dir,
            llm_model_func=custom_ollama_model_complete,
            llm_model_name=settings.LLM_MODEL,
            llm_model_max_async=2,
            default_llm_timeout=settings.LLM_TIMEOUT,
            embedding_func=EmbeddingFunc(
                embedding_dim=embedding_service.embedding_dim,
                max_token_size=256,
                func=embedding_service.embed_texts,
            ),
            kv_storage="PGKVStorage",
            doc_status_storage="PGDocStatusStorage",
            vector_storage="MilvusVectorDBStorage",
            graph_storage="Neo4JStorage",
            addon_params={"language": "Vietnamese"},
            rerank_model_func=rerank_func,
        )

        logger.info("Dang ket noi toi Milvus, Neo4j va PGKV...")
        await self.rag.initialize_storages()
        logger.info("LightRAG storages da san sang.")

    async def query(
        self,
        message: str,
        mode: str = "mix",
        history: list | None = None,
        stream: bool = True,
        enable_rerank: bool | None = None,
    ) -> dict:
        system_prompt = prompt_manager.get_prompt("rag_generation")
        history = history or []

        # enable_rerank
        rerank = enable_rerank if enable_rerank is not None else settings.ENABLE_RERANK

        param = QueryParam(
            mode=mode,
            top_k=20,
            chunk_top_k=15,  # giới hạn lấy số chunks
            stream=stream,
            conversation_history=history,
            user_prompt=system_prompt,
            include_references=True,
            enable_rerank=rerank,
        )

        logger.info(f"Dang search '{message}' voi mode '{mode}', rerank={rerank}...")
        return await self.rag.aquery_llm(message, param=param)

rag_orchestrator = LightRAGOrchestrator()
