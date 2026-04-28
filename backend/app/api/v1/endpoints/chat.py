import json
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from app.domain.schemas.chat import ChatRequest, ChatResponse, ChatHistoryResponse
from app.domain.schemas.chat import ChatSessionItem, ChatSessionListResponse
from app.services.lightrag_orchestrator import rag_orchestrator
from app.services.chat_history_service import chat_history
from app.services.query_rewriter import query_rewriter
from app.services.classifier_query import intent_router, stream_fast_reply
from app.core.logger import logger
import time
from app.services.audit_service import audit_service
from app.api.deps.auth import get_current_user_id
from sqlalchemy import select, func
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models import AuditLog, User


router = APIRouter()

async def check_and_deduct_credit(user_id: int):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user or user.credits <= 0:
            raise HTTPException(status_code=402, detail="Bạn đã hết Credit. Hãy nạp thêm để tiếp tục sử dụng!")
        user.credits -= 1
        await db.commit()

async def ensure_session_owner(session_id: str, current_user_id: int) -> None:
    if not await audit_service.session_has_logs(session_id):
        return

    if not await audit_service.session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập session này")


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    current_user_id: int = Depends(get_current_user_id),
):
    await ensure_session_owner(session_id, current_user_id)
    messages = await chat_history.get_history(session_id)
    return ChatHistoryResponse(session_id=session_id, messages=messages)


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(current_user_id: int = Depends(get_current_user_id)):
    

    async with AsyncSessionLocal() as db:
        stmt = (
            select(AuditLog)
            .where(AuditLog.user_id == current_user_id)
            .order_by(AuditLog.created_at.desc())
        )
        result = await db.execute(stmt)
        logs = result.scalars().all()

        sessions: list[ChatSessionItem] = []
        seen: set[str] = set()
        for log in logs:
            if log.session_id in seen:
                continue
            seen.add(log.session_id)
            count = sum(1 for item in logs if item.session_id == log.session_id)
            sessions.append(
                ChatSessionItem(
                    session_id=log.session_id,
                    title=log.user_query or log.session_id,
                    updated_at=log.created_at,
                    message_count=count,
                )
            )

        return {"data": sessions}


@router.post("/sync", response_model=ChatResponse)
async def chat_sync(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
):
    session_id = request.session_id or f"anon_{int(time.time() * 1000)}"
    if request.session_id:
        await ensure_session_owner(session_id, current_user_id)
        
    await check_and_deduct_credit(current_user_id)
    
    start_time = time.time()
    
    try:
        history = await chat_history.get_history(session_id)
        intent_result = await intent_router.classify_intent(request.message, history)
        intent = intent_result["intent"]
        fast_reply = intent_router.get_fast_response(intent)
        if fast_reply:
            answer = fast_reply
            refs = []
            search_query = request.message

            background_tasks.add_task(chat_history.add_message, session_id, "user", request.message)
            background_tasks.add_task(chat_history.add_message, session_id, "assistant", answer)
            background_tasks.add_task(
                audit_service.log_interaction,
                session_id,
                current_user_id,
                request.message,
                search_query,
                answer,
                time.time() - start_time,
                refs,
            )
            return ChatResponse(response=answer, references=refs)

        search_query = await query_rewriter.rewrite(request.message, history)

        result = await rag_orchestrator.query(
            message=search_query, mode=request.mode, history=history, stream=False
        )
        answer = result.get("llm_response", {}).get("content", "Xin lỗi, tôi không tìm thấy thông tin.")
        refs = result.get("data", {}).get("references", [])
        
        # Background Tasks: Lưu DB ngầm sau khi đã trả kết quả cho User
        background_tasks.add_task(chat_history.add_message, session_id, "user", request.message)
        background_tasks.add_task(chat_history.add_message, session_id, "assistant", answer)
        background_tasks.add_task(
            audit_service.log_interaction, 
            session_id,
            current_user_id,
            request.message,
            search_query,
            answer,
            time.time() - start_time,
            refs,
        )
        return ChatResponse(response=answer, references=refs)
    except Exception:
        logger.exception("Lỗi khi xử lý chat sync")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống, vui lòng thử lại.")


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user_id: int = Depends(get_current_user_id),
):
    session_id = request.session_id or f"anon_{int(time.time() * 1000)}"
    if request.session_id:
        await ensure_session_owner(session_id, current_user_id)
        
    await check_and_deduct_credit(current_user_id)
        
    start_time = time.time()
    
    try:
        history = await chat_history.get_history(session_id)
        intent_result = await intent_router.classify_intent(request.message, history)

        intent = intent_result["intent"]

        fast_reply = intent_router.get_fast_response(intent)

        # greeting / capability / toxic / out_of_domain / unsafe / unclear
        if fast_reply:
            await chat_history.add_message(session_id, "user", request.message)
            await chat_history.add_message(session_id, "assistant", fast_reply)
            await audit_service.log_interaction(
                session_id=session_id,
                user_id=current_user_id,
                user_query=request.message,
                rewritten_query=request.message,
                bot_response=fast_reply,
                processing_time=time.time() - start_time,
                references=[],
            )
            return StreamingResponse(
                stream_fast_reply(fast_reply),
                media_type="text/event-stream"
            )

        # legal_query mới đi tiếp vào RAG pipeline
        search_query = await query_rewriter.rewrite(
            request.message,
            history
        )

        result = await rag_orchestrator.query(
            message=search_query,
            mode=request.mode,
            history=history,
            stream=True
        )

        # hàm đẩy dữ liệu chuẩn SSE
        async def event_generator():
            full_answer = ""
            references = result.get("data", {}).get("references", [])
            
            try:
                # Bắt đầu stream Text
                llm_res = result.get("llm_response", {})
                if llm_res.get("is_streaming"):
                    async for chunk in llm_res.get("response_iterator"):
                        if chunk:
                            full_answer += chunk
                            chunk_json = json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)
                            yield f"data: {chunk_json}\n\n"
                else:
                    content = llm_res.get("content", "")
                    full_answer = content
                    chunk_json = json.dumps({"type": "chunk", "content": content}, ensure_ascii=False)
                    yield f"data: {chunk_json}\n\n"

                # # Gửi references sau khi đã stream xong nội dung trả lời
                # meta_json = json.dumps({"type": "meta", "references": references}, ensure_ascii=False)
                # yield f"data: {meta_json}\n\n"
                
                # Tín hiệu kết thúc
                done_json = json.dumps({"type": "done"})
                yield f"data: {done_json}\n\n"
                
            except Exception as e:
                logger.error(f"❌ Lỗi trong stream generator: {str(e)}")
                err_json = json.dumps({"type": "error", "content": f"Lỗi: {str(e)}"}, ensure_ascii=False)
                yield f"data: {err_json}\n\n"
            
            finally:
                processing_time = time.time() - start_time
                try:
                    await chat_history.add_message(session_id, "user", request.message)
                    await chat_history.add_message(session_id, "assistant", full_answer)
                    await audit_service.log_interaction(
                        session_id=session_id,
                        user_id=current_user_id,
                        user_query=request.message,
                        rewritten_query=search_query,
                        bot_response=full_answer,
                        processing_time=processing_time,
                        references=references,
                    )
                except Exception as db_err:
                    logger.error(f"❌ Lỗi khi lưu dữ liệu trong finally: {str(db_err)}")

        return StreamingResponse(event_generator(), media_type="text/event-stream")  # meta_type của SSE

    except Exception:
        logger.exception("❌ Lỗi khi khởi tạo chat streaming!")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống, vui lòng thử lại.")