#!/usr/bin/env python3
"""
RAGAS Evaluation Script cho Legal AI Platform

Đánh giá chất lượng RAG bằng RAGAS metrics:
- Faithfulness: Câu trả lời có đúng với context không?
- Answer Relevancy: Câu trả lời có liên quan đến câu hỏi không?
- Context Recall: Có retrieve đủ thông tin không?
- Context Precision: Context có sạch không (ít noise)?

Hỗ trợ 3 chế độ đánh giá (--mode):
    compare   : So sánh A/B giữa query gốc và query đã rewrite (mặc định)
    raw       : Chỉ đánh giá với query gốc (không rewrite)
    rewritten : Chỉ đánh giá với query đã qua Query Rewriter

Usage:
    python -m app.evaluation.eval_legal_rag
    python -m app.evaluation.eval_legal_rag --mode compare
    python -m app.evaluation.eval_legal_rag --mode raw --limit 5
    python -m app.evaluation.eval_legal_rag --mode rewritten --dataset custom.json

Kết quả lưu tại: app/evaluation/results/
    - results_YYYYMMDD_HHMMSS.json  (Chi tiết đầy đủ)
    - results_YYYYMMDD_HHMMSS.csv   (CSV để phân tích)

Yêu cầu:
    pip install ragas datasets langchain-ollama langchain-huggingface
"""

import asyncio
import csv
import json
import math
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Suppress deprecation warnings
warnings.filterwarnings(
    "ignore",
    message=".*LangchainLLMWrapper is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*Unexpected type for token usage.*",
    category=UserWarning,
)

# Load .env từ thư mục backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env", override=False)

# Thêm backend vào sys.path để import app modules
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ============================================================
# Conditional imports — chỉ fail nếu chạy evaluation
# ============================================================
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        context_precision,
        context_recall,
        answer_relevancy,
    )
    from ragas.llms import LangchainLLMWrapper
    from langchain_ollama import ChatOllama
    from langchain_huggingface import HuggingFaceEmbeddings

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


# ============================================================
# Core Evaluator
# ============================================================
class LegalRAGEvaluator:
    """Đánh giá chất lượng hệ thống Legal AI Platform bằng RAGAS metrics."""

    def __init__(self, test_dataset_path: str = None, limit: int = None, enable_rerank: bool = False, eval_mode: str = "compare"):
        """
        Args:
            test_dataset_path: Đường dẫn file JSON chứa test dataset.
            limit: Chỉ chạy N câu đầu tiên (để test nhanh).
            enable_rerank: Bật reranking khi query RAG.
            eval_mode: Chế độ đánh giá ('compare', 'raw', 'rewritten').

        Biến môi trường cần thiết:
            OLLAMA_API_KEY: API key cho Ollama (dùng làm judge LLM)
            LLM_BASE_URL: Base URL của Ollama endpoint
            LLM_MODEL: Model name (mặc định: gpt-oss:120b-cloud)
        """
        if not RAGAS_AVAILABLE:
            raise ImportError(
                "RAGAS dependencies chưa cài đặt.\n"
                "Chạy: pip install ragas datasets langchain-ollama langchain-huggingface"
            )

        # ── Judge LLM (dùng Ollama model đang chạy) ─────────
        ollama_api_key = os.getenv("OLLAMA_API_KEY")
        llm_base_url = os.getenv("LLM_BASE_URL")
        llm_model = os.getenv("LLM_MODEL", "gpt-oss:120b-cloud")

        if not ollama_api_key:
            raise EnvironmentError(
                "OLLAMA_API_KEY chưa được set trong .env"
            )

        # Judge LLM dùng Ollama giống runtime của project
        client_kwargs = {}
        if ollama_api_key:
            client_kwargs = {
                "headers": {
                    "Authorization": f"Bearer {ollama_api_key}"
                }
            }

        base_llm = ChatOllama(
            model=llm_model,
            base_url=llm_base_url,
            temperature=0,
            client_kwargs=client_kwargs,
        )

        try:
            self.eval_llm = LangchainLLMWrapper(
                langchain_llm=base_llm,
                bypass_n=True,  # Ollama không hỗ trợ param 'n'
            )
        except Exception:
            self.eval_llm = base_llm

        # ── Embeddings (dùng cùng kiểu embedding như project) ────────
        model_name = "huyydangg/DEk21_hcmute_embedding"
        model_kwargs = {"device": "cpu"}
        encode_kwargs = {"normalize_embeddings": True}

        try:
            self.eval_embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs=model_kwargs,
                encode_kwargs=encode_kwargs,
            )
        except Exception as e:
            print(f"⚠️  Không thể khởi tạo embedding cho RAGAS: {e}")
            print("    Answer Relevancy metric sẽ bị bỏ qua.")

        # ── Dataset ──────────────────────────────────────────
        if test_dataset_path is None:
            test_dataset_path = Path(__file__).parent / "eval_lightRag_dataset.json"

        self.test_dataset_path = Path(test_dataset_path)
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
        self.limit = limit

        self.test_cases = self._load_test_dataset()

        # ── RAG Orchestrator (gọi trực tiếp, không qua HTTP) ─
        self.rag_orchestrator = None
        self.enable_rerank = enable_rerank
        self.eval_mode = eval_mode  # 'compare', 'raw', 'rewritten'

        # Store config for display
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url

    def _load_test_dataset(self) -> List[Dict[str, str]]:
        """Load test dataset từ JSON file."""
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy test dataset: {self.test_dataset_path}\n"
                f"Tạo file JSON với format:\n"
                f'[{{"question": "...", "ground_truth": "..."}}]'
            )

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if self.limit:
            data = data[: self.limit]

        print(f"📂 Loaded {len(data)} test cases từ {self.test_dataset_path}")
        return data

    async def _init_orchestrator(self):
        """Khởi tạo RAG orchestrator (kết nối Milvus, Neo4j, PG)."""
        if self.rag_orchestrator is not None:
            return

        # Tạm set ENABLE_RERANK theo flag eval để orchestrator load rerank model
        import app.core.config as cfg
        original_enable = cfg.settings.ENABLE_RERANK
        cfg.settings.ENABLE_RERANK = self.enable_rerank

        print(f"🔌 Đang khởi tạo LightRAG orchestrator (rerank={self.enable_rerank})...")
        from app.services.lightrag_orchestrator import LightRAGOrchestrator

        self.rag_orchestrator = LightRAGOrchestrator()
        await self.rag_orchestrator.initialize()
        print("✅ LightRAG orchestrator đã sẵn sàng.")

        # Restore config
        cfg.settings.ENABLE_RERANK = original_enable

    async def _query_rag(self, message: str) -> Dict[str, Any]:
        """
        Core: gọi rag_orchestrator.query() với message đã cho.
        Returns dict với answer, contexts, entities_count, relations_count, chunks_count.
        """
        await self._init_orchestrator()

        result = await self.rag_orchestrator.query(
            message=message,
            mode="mix",
            history=[],
            stream=False,
            enable_rerank=self.enable_rerank,
        )

        # Extract answer
        llm_response = result.get("llm_response", {})
        answer = llm_response.get("content", "")
        if not answer:
            answer = "Không tìm thấy thông tin liên quan."

        # Extract contexts từ chunks
        data = result.get("data", {})
        chunks = data.get("chunks", [])
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        contexts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if content:
                contexts.append(content)

        # Fallback: nếu không có chunks, dùng entity descriptions làm context
        if not contexts:
            for entity in entities:
                desc = entity.get("description", "")
                if desc:
                    contexts.append(desc)

        return {
            "answer": answer,
            "contexts": contexts,
            "entities_count": len(entities),
            "relations_count": len(relationships),
            "chunks_count": len(chunks),
        }

    async def generate_rag_response_raw(self, question: str) -> Dict[str, Any]:
        """Phase A: Gửi câu hỏi gốc trực tiếp vào RAG (không qua Query Rewriter)."""
        return await self._query_rag(question)

    async def generate_rag_response_rewritten(self, question: str) -> Dict[str, Any]:
        """Phase B: Viết lại câu hỏi bằng Query Rewriter rồi gửi vào RAG."""
        from app.services.query_rewriter import query_rewriter

        rewritten_question = await query_rewriter.rewrite(question, history=[])
        print(f"    📝 Rewritten: {rewritten_question[:100]}")

        response = await self._query_rag(rewritten_question)
        response["rewritten_query"] = rewritten_question
        return response

    async def _run_ragas(self, question: str, answer: str, contexts: list, ground_truth: str) -> Dict[str, Any]:
        """Chạy RAGAS evaluation cho 1 bộ (question, answer, contexts, ground_truth)."""
        if not contexts:
            return {
                "metrics": {"faithfulness": 0.0, "answer_relevance": 0.0, "context_recall": 0.0, "context_precision": 0.0},
                "ragas_score": 0.0,
                "eval_time": 0,
            }

        eval_dataset = Dataset.from_dict({
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [ground_truth],
        })

        metrics = [faithfulness, context_recall, context_precision]
        if self.eval_embeddings:
            metrics.append(answer_relevancy)

        eval_kwargs = {"dataset": eval_dataset, "metrics": metrics, "llm": self.eval_llm}
        if self.eval_embeddings:
            eval_kwargs["embeddings"] = self.eval_embeddings

        start = time.time()
        eval_results = evaluate(**eval_kwargs)
        eval_time = time.time() - start

        df = eval_results.to_pandas()
        row = df.iloc[0]

        result_metrics = {
            "faithfulness": float(row.get("faithfulness", 0)),
            "context_recall": float(row.get("context_recall", 0)),
            "context_precision": float(row.get("context_precision", 0)),
        }
        if self.eval_embeddings:
            result_metrics["answer_relevance"] = float(row.get("answer_relevancy", 0))

        for key, value in result_metrics.items():
            if _is_nan(value):
                result_metrics[key] = 0.0

        valid = [v for v in result_metrics.values() if not _is_nan(v)]
        ragas_score = sum(valid) / len(valid) if valid else 0.0

        return {"metrics": result_metrics, "ragas_score": ragas_score, "eval_time": eval_time}

    async def _run_single_phase(self, phase_name: str, question: str, ground_truth: str, gen_func) -> Dict[str, Any]:
        """Chạy 1 phase (raw hoặc rewritten): query RAG → RAGAS scoring."""
        print(f"  ⏳ [{phase_name}] Đang query RAG...")
        start = time.time()
        rag_response = await gen_func(question)
        rag_time = time.time() - start
        print(
            f"  ✅ [{phase_name}] RAG: {len(rag_response['answer'])} chars, "
            f"{len(rag_response['contexts'])} contexts ({rag_time:.1f}s)"
        )

        print(f"  ⏳ [{phase_name}] Đang chạy RAGAS evaluation...")
        ragas_result = await self._run_ragas(question, rag_response["answer"], rag_response["contexts"], ground_truth)

        m = ragas_result["metrics"]
        print(f"  ✅ [{phase_name}] RAGAS Score: {ragas_result['ragas_score']:.3f}  "
              f"(F={m.get('faithfulness',0):.2f} CR={m.get('context_recall',0):.2f} "
              f"CP={m.get('context_precision',0):.2f} AR={m.get('answer_relevance',0):.2f})")

        return {
            "answer": rag_response["answer"][:300],
            "rewritten_query": rag_response.get("rewritten_query", ""),
            "contexts_count": len(rag_response["contexts"]),
            "entities_count": rag_response.get("entities_count", 0),
            "relations_count": rag_response.get("relations_count", 0),
            "metrics": ragas_result["metrics"],
            "ragas_score": ragas_result["ragas_score"],
            "rag_time": rag_time,
            "eval_time": ragas_result["eval_time"],
        }

    async def evaluate_single_case(
        self, idx: int, test_case: Dict[str, str]
    ) -> Dict[str, Any]:
        """Đánh giá 1 test case theo eval_mode (compare/raw/rewritten)."""
        question = test_case["question"]
        ground_truth = test_case["ground_truth"]

        print(f"\n{'='*60}")
        print(f"📝 Test {idx}/{len(self.test_cases)}: {question[:80]}...")
        print(f"{'='*60}")

        result = {
            "test_number": idx,
            "question": question,
            "ground_truth": ground_truth[:300],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Phase A: Raw (không rewrite)
            if self.eval_mode in ("compare", "raw"):
                result["raw"] = await self._run_single_phase(
                    "RAW", question, ground_truth, self.generate_rag_response_raw
                )

            # Phase B: Rewritten (có rewrite)
            if self.eval_mode in ("compare", "rewritten"):
                result["rewritten"] = await self._run_single_phase(
                    "REWRITTEN", question, ground_truth, self.generate_rag_response_rewritten
                )

            # So sánh nhanh (nếu chạy compare)
            if self.eval_mode == "compare" and "raw" in result and "rewritten" in result:
                delta = result["rewritten"]["ragas_score"] - result["raw"]["ragas_score"]
                icon = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
                print(f"  {icon} Delta RAGAS: {delta:+.3f}  (raw={result['raw']['ragas_score']:.3f} → rewritten={result['rewritten']['ragas_score']:.3f})")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            result["error"] = str(e)

        return result

    @staticmethod
    def _avg_phase_metrics(results: list, phase: str) -> Dict[str, float]:
        """Tính trung bình metrics cho 1 phase (raw hoặc rewritten)."""
        phase_data = [r[phase] for r in results if phase in r and "error" not in r]
        if not phase_data:
            return {}
        avg = {}
        for key in phase_data[0]["metrics"]:
            vals = [d["metrics"][key] for d in phase_data if key in d["metrics"]]
            avg[key] = sum(vals) / len(vals) if vals else 0.0
        avg["ragas_score"] = sum(d["ragas_score"] for d in phase_data) / len(phase_data)
        return avg

    def _print_comparison(self, avg_raw: dict, avg_rewritten: dict):
        """In bảng so sánh A/B."""
        print("\n" + "=" * 70)
        print("📊 SO SÁNH A/B: QUERY GỐC  vs  QUERY REWRITTEN")
        print("=" * 70)
        print(f"  {'Metric':<25s} {'Raw':>10s} {'Rewritten':>10s} {'Delta':>10s}")
        print("-" * 70)

        metric_labels = {
            "faithfulness": "Faithfulness",
            "context_recall": "Context Recall",
            "context_precision": "Context Precision",
            "answer_relevance": "Answer Relevance",
            "ragas_score": "RAGAS Score",
        }

        for key, label in metric_labels.items():
            raw_val = avg_raw.get(key, 0)
            rew_val = avg_rewritten.get(key, 0)
            delta = rew_val - raw_val
            icon = "📈" if delta > 0.01 else ("📉" if delta < -0.01 else "➡️")
            print(f"  {label:<25s} {raw_val:>10.3f} {rew_val:>10.3f} {icon}{delta:>+9.3f}")

        print("=" * 70)

    def _print_single_summary(self, avg: dict, phase_label: str):
        """In tổng kết cho 1 phase duy nhất."""
        print("\n" + "=" * 70)
        print(f"📊 KẾT QUẢ ĐÁNH GIÁ — {phase_label}")
        print("=" * 70)
        for key, value in avg.items():
            label = key.replace("_", " ").title()
            bar = "█" * int(value * 20) + "░" * (20 - int(value * 20))
            print(f"    {label:22s} {bar} {value:.3f}")
        print("=" * 70)

    async def run_evaluation(self) -> Dict[str, Any]:
        """Chạy evaluation cho toàn bộ test dataset."""
        total_start = time.time()

        mode_label = {"compare": "COMPARE (Raw vs Rewritten)", "raw": "RAW (Không rewrite)", "rewritten": "REWRITTEN (Có rewrite)"}

        print("\n" + "=" * 70)
        print("🏛️  LEGAL AI PLATFORM — RAGAS EVALUATION")
        print("=" * 70)
        print(f"  Judge LLM:      {self.llm_model}")
        print(f"  LLM Endpoint:   {self.llm_base_url}")
        print(f"  Test cases:     {len(self.test_cases)}")
        print(f"  Dataset:        {self.test_dataset_path}")
        print(f"  Mode:           {mode_label.get(self.eval_mode, self.eval_mode)}")
        print(f"  Rerank:         {'✅ ENABLED' if self.enable_rerank else '❌ DISABLED'}")
        print(f"  Embeddings:     {'✅ Available' if self.eval_embeddings else '❌ Not available'}")
        print("=" * 70)

        results = []
        for idx, test_case in enumerate(self.test_cases, start=1):
            result = await self.evaluate_single_case(idx, test_case)
            results.append(result)

        total_time = time.time() - total_start

        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        print(f"\n  Tổng: {len(results)}  |  OK: {len(successful)}  |  Failed: {len(failed)}  |  Time: {total_time:.1f}s")

        # ── Tổng hợp và in kết quả ──────────────────────────
        avg_raw = self._avg_phase_metrics(results, "raw") if self.eval_mode in ("compare", "raw") else {}
        avg_rewritten = self._avg_phase_metrics(results, "rewritten") if self.eval_mode in ("compare", "rewritten") else {}

        if self.eval_mode == "compare" and avg_raw and avg_rewritten:
            self._print_comparison(avg_raw, avg_rewritten)
        elif avg_raw:
            self._print_single_summary(avg_raw, "QUERY GỐC (RAW)")
        elif avg_rewritten:
            self._print_single_summary(avg_rewritten, "QUERY REWRITTEN")

        # ── Lưu kết quả ─────────────────────────────────────
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = {
            "evaluation_config": {
                "judge_llm": self.llm_model,
                "llm_endpoint": self.llm_base_url,
                "dataset": str(self.test_dataset_path),
                "eval_mode": self.eval_mode,
                "total_cases": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "total_time_seconds": round(total_time, 2),
            },
            "detailed_results": results,
        }
        if avg_raw:
            report["average_metrics_raw"] = {k: round(v, 4) for k, v in avg_raw.items()}
        if avg_rewritten:
            report["average_metrics_rewritten"] = {k: round(v, 4) for k, v in avg_rewritten.items()}

        json_path = self.results_dir / f"results_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 JSON report: {json_path}")

        # CSV — mỗi test case 1 dòng, columns cho cả raw và rewritten
        csv_path = self.results_dir / f"results_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            header = ["test_number", "question"]
            if self.eval_mode in ("compare", "raw"):
                header += ["raw_ragas", "raw_faith", "raw_recall", "raw_precision", "raw_relevance", "raw_time"]
            if self.eval_mode in ("compare", "rewritten"):
                header += ["rew_ragas", "rew_faith", "rew_recall", "rew_precision", "rew_relevance", "rew_time"]
            if self.eval_mode == "compare":
                header += ["delta_ragas"]
            header += ["error"]
            writer.writerow(header)

            for r in results:
                row = [r.get("test_number", ""), r.get("question", "")[:100]]
                raw = r.get("raw", {})
                rew = r.get("rewritten", {})
                if self.eval_mode in ("compare", "raw"):
                    rm = raw.get("metrics", {})
                    row += [raw.get("ragas_score", ""), rm.get("faithfulness", ""), rm.get("context_recall", ""),
                            rm.get("context_precision", ""), rm.get("answer_relevance", ""), raw.get("rag_time", "")]
                if self.eval_mode in ("compare", "rewritten"):
                    wm = rew.get("metrics", {})
                    row += [rew.get("ragas_score", ""), wm.get("faithfulness", ""), wm.get("context_recall", ""),
                            wm.get("context_precision", ""), wm.get("answer_relevance", ""), rew.get("rag_time", "")]
                if self.eval_mode == "compare" and raw and rew:
                    row += [round(rew.get("ragas_score", 0) - raw.get("ragas_score", 0), 4)]
                elif self.eval_mode == "compare":
                    row += [""]
                row += [r.get("error", "")]
                writer.writerow(row)
        print(f"💾 CSV report:  {csv_path}")

        return report


# ============================================================
# CLI Entry Point
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Đánh giá chất lượng Legal AI Platform bằng RAGAS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python -m app.evaluation.eval_legal_rag --mode compare
  python -m app.evaluation.eval_legal_rag --mode raw --limit 5
  python -m app.evaluation.eval_legal_rag --mode rewritten
        """,
    )
    parser.add_argument(
        "-d", "--dataset",
        type=str,
        default=None,
        help="Đường dẫn file JSON test dataset",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Chỉ chạy N câu đầu tiên (để test nhanh)",
    )
    parser.add_argument(
        "--enable-rerank",
        action="store_true",
        default=True,
        help="Bật reranking",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["compare", "raw", "rewritten"],
        default="compare",
        help="Chế độ đánh giá: compare (A/B), raw (không rewrite), rewritten (có rewrite)",
    )

    args = parser.parse_args()

    evaluator = LegalRAGEvaluator(
        test_dataset_path=args.dataset,
        limit=args.limit,
        enable_rerank=args.enable_rerank,
        eval_mode=args.mode,
    )

    asyncio.run(evaluator.run_evaluation())


if __name__ == "__main__":
    main()

