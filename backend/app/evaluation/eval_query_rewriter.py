#!/usr/bin/env python3
"""
Query Rewriter Evaluation Script cho Legal AI Platform

Đánh giá chất lượng Query Rewriter qua 3 tiêu chí (LLM-as-judge):
  - Semantic Preservation: Câu rewrite giữ nguyên ý nghĩa câu hỏi gốc?
  - Context Enrichment: Có bổ sung đủ context từ lịch sử chat?
  - Standalone Clarity: Câu rewrite có tự đứng độc lập được?

Usage:
    python -m app.evaluation.eval_query_rewriter
    python -m app.evaluation.eval_query_rewriter --limit 5
    python -m app.evaluation.eval_query_rewriter --dataset path/to/custom.json

Kết quả lưu tại: app/evaluation/results/
    - rewriter_eval_YYYYMMDD_HHMMSS.json
    - rewriter_eval_YYYYMMDD_HHMMSS.csv
"""

import asyncio
import csv
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Fix Windows console encoding ────────────────────────────
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Paths & Env ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env", override=False)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ── Judge Prompt ─────────────────────────────────────────────
JUDGE_SYSTEM_PROMPT = """\
Bạn là chuyên gia đánh giá chất lượng câu hỏi pháp lý.
Nhiệm vụ: So sánh câu hỏi gốc (follow-up ngắn) với câu đã viết lại (rewritten), dựa trên lịch sử hội thoại.

Chấm điểm 3 tiêu chí, mỗi tiêu chí thang 1-10:

1. SEMANTIC_PRESERVATION (Giữ nguyên ý nghĩa):
   - 10: Ý nghĩa hoàn toàn giống câu gốc
   - 7-9: Giữ ý chính, có thể thêm/bớt chi tiết nhỏ
   - 4-6: Ý chính đúng nhưng thiếu hoặc thừa nhiều
   - 1-3: Sai ý nghĩa gốc

2. CONTEXT_ENRICHMENT (Bổ sung ngữ cảnh):
   - 10: Bổ sung đầy đủ context từ history, tạo câu hoàn chỉnh
   - 7-9: Bổ sung phần lớn context cần thiết
   - 4-6: Bổ sung một phần, còn thiếu
   - 1-3: Không bổ sung hoặc bổ sung sai context

3. STANDALONE_CLARITY (Tự đứng độc lập):
   - 10: Đọc câu rewrite mà không cần history vẫn hiểu đầy đủ
   - 7-9: Hiểu được phần lớn, có chỗ hơi mơ hồ
   - 4-6: Cần đọc history mới hiểu hết
   - 1-3: Không thể hiểu nếu không có history

CHỈ trả về JSON hợp lệ, KHÔNG giải thích:
{
  "semantic_preservation": <1-10>,
  "context_enrichment": <1-10>,
  "standalone_clarity": <1-10>,
  "comment": "<1 dòng nhận xét ngắn>"
}"""

JUDGE_USER_TEMPLATE = """\
LỊCH SỬ HỘI THOẠI:
{history_text}

CÂU HỎI GỐC (follow-up): {follow_up}

CÂU ĐÃ VIẾT LẠI (rewritten): {rewritten}

CÂU MONG ĐỢI (reference): {expected}

Hãy chấm điểm câu rewritten."""


# ── Evaluator ────────────────────────────────────────────────
class QueryRewriterEvaluator:
    """Đánh giá chất lượng Query Rewriter bằng LLM-as-judge."""

    def __init__(self, test_dataset_path: str = None, limit: int = None):
        from app.services.prompt_manager import prompt_manager
        prompt_manager.load_prompts()

        from app.services.query_rewriter import QueryRewriterService
        self.rewriter = QueryRewriterService()

        if test_dataset_path is None:
            test_dataset_path = Path(__file__).parent / "rewriter_test_dataset.json"

        self.test_dataset_path = Path(test_dataset_path)
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
        self.limit = limit
        self.test_cases = self._load_dataset()

        from app.core.config import settings
        self.settings = settings
        self.llm_model = settings.LLM_MODEL
        self.llm_base_url = settings.LLM_BASE_URL

    def _load_dataset(self) -> list[dict]:
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(f"Khong tim thay dataset: {self.test_dataset_path}")

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if self.limit:
            data = data[: self.limit]

        print(f"[LOAD] {len(data)} test cases tu {self.test_dataset_path.name}")
        return data

    # ── LLM Judge ────────────────────────────────────────────
    async def _judge_rewrite(
        self, history: list, follow_up: str, rewritten: str, expected: str
    ) -> dict:
        """Dùng LLM chấm điểm câu rewrite."""
        from app.infrastructure.llm.ollama_service import get_ollama_client

        history_text = "\n".join(
            f"  [{m['role'].upper()}]: {m['content']}" for m in history
        )
        user_prompt = JUDGE_USER_TEMPLATE.format(
            history_text=history_text,
            follow_up=follow_up,
            rewritten=rewritten,
            expected=expected,
        )

        client = get_ollama_client()
        response = await client.chat(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0.0},
        )

        raw = response.get("message", {}).get("content", "").strip()

        # Parse JSON from response (handle markdown code blocks)
        json_str = raw
        if "```" in json_str:
            # Extract JSON from code block
            start = json_str.find("{")
            end = json_str.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = json_str[start:end]

        try:
            scores = json.loads(json_str)
            return {
                "semantic_preservation": int(scores.get("semantic_preservation", 5)),
                "context_enrichment": int(scores.get("context_enrichment", 5)),
                "standalone_clarity": int(scores.get("standalone_clarity", 5)),
                "comment": scores.get("comment", ""),
                "raw_response": raw,
            }
        except (json.JSONDecodeError, ValueError):
            return {
                "semantic_preservation": 5,
                "context_enrichment": 5,
                "standalone_clarity": 5,
                "comment": "JSON parse error",
                "raw_response": raw,
                "parse_error": True,
            }

    # ── Evaluate single ──────────────────────────────────────
    async def evaluate_single(self, idx: int, test_case: dict) -> dict:
        history = test_case["history"]
        follow_up = test_case["follow_up"]
        expected = test_case["expected_standalone"]
        category = test_case.get("category", "unknown")
        description = test_case.get("description", "")

        # Step 1: Run rewriter
        start = time.time()
        try:
            rewritten = await self.rewriter.rewrite(follow_up, history)
        except Exception as e:
            return {
                "test_number": idx,
                "follow_up": follow_up,
                "description": description,
                "category": category,
                "rewritten": "",
                "expected": expected,
                "scores": {},
                "error": f"Rewriter error: {e}",
                "rewrite_time": round(time.time() - start, 2),
            }
        rewrite_time = time.time() - start

        # Step 2: Judge the rewrite
        try:
            judge_start = time.time()
            scores = await self._judge_rewrite(history, follow_up, rewritten, expected)
            judge_time = time.time() - judge_start
        except Exception as e:
            scores = {
                "semantic_preservation": 0,
                "context_enrichment": 0,
                "standalone_clarity": 0,
                "comment": f"Judge error: {e}",
            }
            judge_time = 0

        # Composite score (weighted: standalone_clarity most important)
        sp = scores.get("semantic_preservation", 0)
        ce = scores.get("context_enrichment", 0)
        sc = scores.get("standalone_clarity", 0)
        composite = round((sp * 0.3 + ce * 0.3 + sc * 0.4) / 10, 3)

        return {
            "test_number": idx,
            "follow_up": follow_up,
            "description": description,
            "category": category,
            "rewritten": rewritten,
            "expected": expected,
            "scores": {
                "semantic_preservation": sp,
                "context_enrichment": ce,
                "standalone_clarity": sc,
                "composite": composite,
            },
            "comment": scores.get("comment", ""),
            "rewrite_time": round(rewrite_time, 2),
            "judge_time": round(judge_time, 2),
        }

    # ── Compute metrics ──────────────────────────────────────
    @staticmethod
    def _compute_metrics(results: list[dict]) -> dict:
        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        if not successful:
            return {"overall": {}, "per_category": {}, "failed": len(failed)}

        # Overall averages
        sp_vals = [r["scores"]["semantic_preservation"] for r in successful]
        ce_vals = [r["scores"]["context_enrichment"] for r in successful]
        sc_vals = [r["scores"]["standalone_clarity"] for r in successful]
        comp_vals = [r["scores"]["composite"] for r in successful]

        overall = {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "avg_semantic_preservation": round(sum(sp_vals) / len(sp_vals), 2),
            "avg_context_enrichment": round(sum(ce_vals) / len(ce_vals), 2),
            "avg_standalone_clarity": round(sum(sc_vals) / len(sc_vals), 2),
            "avg_composite": round(sum(comp_vals) / len(comp_vals), 3),
            "avg_rewrite_time": round(sum(r["rewrite_time"] for r in successful) / len(successful), 2),
        }

        # Per-category breakdown
        categories = set(r["category"] for r in successful)
        per_category = {}
        for cat in sorted(categories):
            cat_results = [r for r in successful if r["category"] == cat]
            per_category[cat] = {
                "count": len(cat_results),
                "avg_semantic": round(sum(r["scores"]["semantic_preservation"] for r in cat_results) / len(cat_results), 2),
                "avg_context": round(sum(r["scores"]["context_enrichment"] for r in cat_results) / len(cat_results), 2),
                "avg_standalone": round(sum(r["scores"]["standalone_clarity"] for r in cat_results) / len(cat_results), 2),
                "avg_composite": round(sum(r["scores"]["composite"] for r in cat_results) / len(cat_results), 3),
            }

        # Find best and worst
        sorted_by_comp = sorted(successful, key=lambda r: r["scores"]["composite"])
        worst = sorted_by_comp[:3] if len(sorted_by_comp) >= 3 else sorted_by_comp
        best = sorted_by_comp[-3:] if len(sorted_by_comp) >= 3 else sorted_by_comp

        return {
            "overall": overall,
            "per_category": per_category,
            "worst_cases": [{"test": r["test_number"], "follow_up": r["follow_up"][:50], "composite": r["scores"]["composite"]} for r in worst],
            "best_cases": [{"test": r["test_number"], "follow_up": r["follow_up"][:50], "composite": r["scores"]["composite"]} for r in best],
        }

    # ── Print report ─────────────────────────────────────────
    @staticmethod
    def _print_report(metrics: dict, results: list[dict]):
        o = metrics.get("overall", {})
        pc = metrics.get("per_category", {})

        print()
        print("=" * 70)
        print("  QUERY REWRITER EVALUATION")
        print("=" * 70)
        print(f"  Total: {o.get('total', 0)}  |  OK: {o.get('successful', 0)}  |  Failed: {o.get('failed', 0)}")
        print(f"  Avg rewrite time: {o.get('avg_rewrite_time', 0)}s")
        print()

        # Overall scores
        for metric_key, label in [
            ("avg_semantic_preservation", "Semantic Preservation"),
            ("avg_context_enrichment", "Context Enrichment"),
            ("avg_standalone_clarity", "Standalone Clarity"),
        ]:
            val = o.get(metric_key, 0)
            bar = "#" * int(val) + "." * (10 - int(val))
            color = "[OK]" if val >= 7 else ("[MID]" if val >= 5 else "[LOW]")
            print(f"  {color} {label:<25s} [{bar}]  {val:.1f}/10")

        comp = o.get("avg_composite", 0)
        comp_pct = comp * 100
        color = "[OK]" if comp >= 0.7 else ("[MID]" if comp >= 0.5 else "[LOW]")
        print(f"\n  {color} Composite Score:  {comp_pct:.1f}%")
        print()

        # Per-category breakdown
        if pc:
            print("-" * 70)
            print(f"  {'Category':<22s} {'N':>3s} {'Semantic':>9s} {'Context':>9s} {'Standalone':>11s} {'Composite':>10s}")
            print("-" * 70)
            for cat, m in pc.items():
                print(f"  {cat:<22s} {m['count']:>3d} {m['avg_semantic']:>9.1f} {m['avg_context']:>9.1f} {m['avg_standalone']:>11.1f} {m['avg_composite']*100:>9.1f}%")
            print()

        # Detailed results
        print("-" * 70)
        print("  DETAILED RESULTS:")
        print("-" * 70)
        successful = [r for r in results if "error" not in r]
        for r in successful:
            sc = r["scores"]
            comp_icon = "[OK]" if sc["composite"] >= 0.7 else ("[MID]" if sc["composite"] >= 0.5 else "[LOW]")
            print(f"\n  #{r['test_number']:>2d} [{r['category']}] {comp_icon}")
            print(f"      Follow-up:  \"{r['follow_up']}\"")
            print(f"      Rewritten:  \"{r['rewritten'][:100]}\"")
            print(f"      Expected:   \"{r['expected'][:100]}\"")
            print(f"      Scores: SP={sc['semantic_preservation']}  CE={sc['context_enrichment']}  SC={sc['standalone_clarity']}  -> {sc['composite']*100:.0f}%")
            if r.get("comment"):
                print(f"      Judge: {r['comment']}")

        print()
        print("=" * 70)

    # ── Save results ─────────────────────────────────────────
    def _save_results(self, metrics: dict, results: list[dict]) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        report = {
            "evaluation_config": {
                "llm_model": self.llm_model,
                "llm_endpoint": self.llm_base_url,
                "dataset": str(self.test_dataset_path),
                "total_cases": len(results),
                "timestamp": datetime.now().isoformat(),
            },
            "metrics": metrics,
            "detailed_results": results,
        }

        json_path = self.results_dir / f"rewriter_eval_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        csv_path = self.results_dir / f"rewriter_eval_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "test_number", "category", "follow_up", "rewritten", "expected",
                "semantic_preservation", "context_enrichment", "standalone_clarity",
                "composite", "comment", "rewrite_time", "judge_time",
            ])
            for r in results:
                sc = r.get("scores", {})
                writer.writerow([
                    r["test_number"], r["category"],
                    r["follow_up"], r.get("rewritten", "")[:200], r["expected"][:200],
                    sc.get("semantic_preservation", ""),
                    sc.get("context_enrichment", ""),
                    sc.get("standalone_clarity", ""),
                    sc.get("composite", ""),
                    r.get("comment", ""),
                    r.get("rewrite_time", ""),
                    r.get("judge_time", ""),
                ])

        return json_path, csv_path

    # ── Main runner ──────────────────────────────────────────
    async def run_evaluation(self) -> dict:
        total_start = time.time()

        print()
        print("=" * 70)
        print("  LEGAL AI — QUERY REWRITER EVALUATION")
        print("=" * 70)
        print(f"  LLM Model:    {self.llm_model}")
        print(f"  LLM Endpoint: {self.llm_base_url}")
        print(f"  Test cases:   {len(self.test_cases)}")
        print(f"  Dataset:      {self.test_dataset_path.name}")
        print("=" * 70)

        results = []
        for idx, test_case in enumerate(self.test_cases, start=1):
            follow_up = test_case["follow_up"][:40]
            category = test_case.get("category", "?")

            print(f"\n  [{idx:>2d}/{len(self.test_cases)}] \"{follow_up}\" ({category})")
            print(f"       Rewriting...", end="", flush=True)

            result = await self.evaluate_single(idx, test_case)
            results.append(result)

            if "error" in result:
                print(f"  ERROR: {result['error']}")
            else:
                sc = result["scores"]
                print(f" done ({result['rewrite_time']}s)")
                print(f"       -> \"{result['rewritten'][:70]}\"")
                print(f"       Judging...", end="", flush=True)
                print(f" SP={sc['semantic_preservation']} CE={sc['context_enrichment']} SC={sc['standalone_clarity']} -> {sc['composite']*100:.0f}%")

            await asyncio.sleep(0.3)

        total_time = time.time() - total_start

        metrics = self._compute_metrics(results)
        metrics["total_time"] = round(total_time, 1)

        self._print_report(metrics, results)

        json_path, csv_path = self._save_results(metrics, results)
        print(f"\n  JSON: {json_path}")
        print(f"  CSV:  {csv_path}")
        print(f"  Total time: {total_time:.1f}s")
        print()

        return {"metrics": metrics, "results": results}


# ── CLI ──────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Danh gia Query Rewriter cho Legal AI Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-d", "--dataset", type=str, default=None)
    parser.add_argument("-l", "--limit", type=int, default=None)

    args = parser.parse_args()

    evaluator = QueryRewriterEvaluator(
        test_dataset_path=args.dataset,
        limit=args.limit,
    )

    asyncio.run(evaluator.run_evaluation())


if __name__ == "__main__":
    main()
