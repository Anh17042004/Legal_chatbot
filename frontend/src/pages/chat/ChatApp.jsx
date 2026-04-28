import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../../contexts/AuthContext';
import { chatApi } from '../../api/chatApi';
import { apiStream } from '../../api/client';
import './ChatApp.css';

const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 480;
const SIDEBAR_DEFAULT = 300;

export default function ChatApp() {
  const { user, logout, loadUser } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [mode, setMode] = useState('mix');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT);
  const [isDragging, setIsDragging] = useState(false);

  const messagesEndRef = useRef(null);
  const dragRef = useRef(null);
  const currentSessionIdRef = useRef(null);

  const quickPrompts = [
    'Điều kiện ly hôn đơn phương là gì?',
    'Quyền nuôi con sau ly hôn được xác định thế nào?',
    'Vượt đèn đỏ bị xử phạt bao nhiêu?',
    'Thủ tục đăng ký kết hôn gồm những gì?',
  ];

  const currentSession = sessions.find((s) => s.session_id === currentSessionId);

  /* ─── Data loading ─── */
  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    loadSessions();

    const handleVisibilityOrFocus = () => {
      if (!document.hidden) {
        loadSessions();
      }
    };

    const handleStorageSync = (event) => {
      if (event.key === 'auditLogsUpdatedAt') {
        loadSessions();
      }
    };

    const handleAuditUpdated = () => {
      loadSessions();
    };

    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    window.addEventListener('storage', handleStorageSync);
    window.addEventListener('audit-logs-updated', handleAuditUpdated);

    return () => {
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
      window.removeEventListener('storage', handleStorageSync);
      window.removeEventListener('audit-logs-updated', handleAuditUpdated);
    };
  }, []);

  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      return;
    }

    // Do not overwrite optimistic/live stream messages while streaming.
    if (isStreaming) return;

    loadHistory(currentSessionId);
  }, [currentSessionId, isStreaming]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    try {
      const res = await chatApi.getSessions();
      const sessionList = res.data || [];
      setSessions(sessionList);

      const activeSessionId = currentSessionIdRef.current;
      if (activeSessionId && !sessionList.some((s) => s.session_id === activeSessionId)) {
        setCurrentSessionId(null);
        setMessages([]);
      }
    } catch (err) { console.error(err); }
  };

  const loadHistory = async (sessionId) => {
    try {
      const res = await chatApi.getHistory(sessionId);
      setMessages(res.messages || []);
    } catch (err) { console.error(err); }
  };

  /* ─── Actions ─── */
  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setInput('');
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleQuickPrompt = (prompt) => {
    setCurrentSessionId(null);
    setMessages([]);
    setInput(prompt);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleSelectSession = (sessionId) => {
    setCurrentSessionId(sessionId);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  /* ─── Resize sidebar ─── */
  const handleResizeStart = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
  }, [sidebarWidth]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (e) => {
      const dx = e.clientX - dragRef.current.startX;
      const newW = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, dragRef.current.startWidth + dx));
      setSidebarWidth(newW);
    };
    const handleUp = () => setIsDragging(false);
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging]);

  /* ─── Submit chat ─── */
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    if (user && user.credits <= 0) {
      alert('Tài khoản của bạn đã hết Credit. Hãy nạp thêm hoặc liên hệ Admin!');
      return;
    }

    const userMessage = input.trim();
    const isNewSession = !currentSessionId;
    const activeSessionId = currentSessionId || `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    if (isNewSession) {
      setCurrentSessionId(activeSessionId);
    }

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setMessages((prev) => [...prev, { role: 'assistant', content: '', references: [] }]);
    setIsStreaming(true);

    try {
      const res = await apiStream('/chat/stream', {
        message: userMessage,
        mode,
        session_id: activeSessionId,
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;
      let botContent = '';
      let botRefs = [];
      let buffer = '';

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          let newlineIndex;
          while ((newlineIndex = buffer.indexOf('\n\n')) >= 0) {
            const line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 2);
            if (line.startsWith('data: ')) {
              const dataStr = line.substring(6);
              try {
                const data = JSON.parse(dataStr);
                if (data.type === 'chunk') {
                  botContent += data.content;
                  setMessages((prev) => {
                    if (!prev.length) return prev;
                    const msgs = [...prev];
                    msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: botContent };
                    return msgs;
                  });
                } else if (data.type === 'meta') {
                  botRefs = data.references || [];
                  setMessages((prev) => {
                    if (!prev.length) return prev;
                    const msgs = [...prev];
                    msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], references: botRefs };
                    return msgs;
                  });
                } else if (data.type === 'done') {
                  loadSessions();
                } else if (data.type === 'error') {
                  console.error('Stream error:', data.content);
                }
              } catch (_) { /* ignore partial JSON */ }
            }
          }
        }
      }
    } catch (err) {
      console.error('Chat error', err);
      if (err.message?.includes('Credit')) {
        alert('Tài khoản của bạn đã hết Credit. Hãy nạp thêm!');
      }
      setMessages((prev) => {
        const msgs = [...prev];
        msgs[msgs.length - 1].content = err.message || 'Có lỗi xảy ra khi kết nối đến máy chủ.';
        return msgs;
      });
    } finally {
      setIsStreaming(false);
      loadUser();
    }
  };

  /* ─── Render ─── */
  return (
    <div className="chat-root">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div className="mobile-backdrop" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Toggle button */}
      <button
        className={`sidebar-toggle ${sidebarOpen ? 'open' : ''}`}
        onClick={() => setSidebarOpen((v) => !v)}
        title={sidebarOpen ? 'Đóng sidebar' : 'Mở sidebar'}
      >
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          {sidebarOpen ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          )}
        </svg>
      </button>

      {/* Sidebar */}
      <aside
        className={`chat-sidebar ${sidebarOpen ? '' : 'collapsed'}`}
        style={sidebarOpen ? { '--sidebar-w': `${sidebarWidth}px` } : undefined}
      >
        <div className="sidebar-inner">
          <div className="sidebar-brand">
            <span className="sidebar-brand-tag">Legal AI Platform</span>
            <h2>Chat pháp luật</h2>
            <p>Tư vấn pháp lý thông minh: trả lời từng phần, dẫn luật đầy đủ.</p>
            <button className="sidebar-new-btn" onClick={handleNewChat}>
              + Đoạn chat mới
            </button>
          </div>

          <div className="sidebar-sessions">
            <div className="sidebar-sessions-label">
              <span>Lịch sử</span>
              <span className="sidebar-sessions-count">{sessions.length}</span>
            </div>

            {sessions.length === 0 ? (
              <div className="session-empty">
                Chưa có đoạn chat nào. Hãy gửi câu hỏi đầu tiên để bắt đầu.
              </div>
            ) : (
              <div className="session-list">
                {sessions.map((session) => (
                  <button
                    key={session.session_id}
                    className={`session-item ${currentSessionId === session.session_id ? 'active' : ''}`}
                    onClick={() => handleSelectSession(session.session_id)}
                  >
                    <div className="session-title">{session.title}</div>
                    <div className="session-meta">
                      <span>{new Date(session.updated_at).toLocaleDateString('vi-VN')}</span>
                      <span className="session-meta-dot">•</span>
                      <span>{session.message_count} tin nhắn</span>
                      <span className="session-id-tag">#{session.session_id.slice(0, 5)}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-user-card">
              <div className="sidebar-user-info">
                <div>
                  <div className="sidebar-user-name">{user?.full_name || user?.email}</div>
                  <div className="sidebar-user-badges">
                    <span className="badge-role">{user?.role}</span>
                    <span className="badge-credit">{user?.credits || 0} credit</span>
                  </div>
                </div>
              </div>
              <button className="sidebar-logout-btn" onClick={logout}>Đăng xuất</button>
            </div>
          </div>
        </div>
      </aside>

      {/* Resize handle */}
      {sidebarOpen && (
        <div
          className={`resize-handle ${isDragging ? 'dragging' : ''}`}
          onMouseDown={handleResizeStart}
        />
      )}

      {/* Main */}
      <main className="chat-main">
        <div className="chat-main-header">
          <div className={`chat-main-header-left ${sidebarOpen ? 'no-toggle-pad' : ''}`}>
            <div className="header-label">
              {currentSession ? 'Phiên đang mở' : 'Đoạn chat mới'}
            </div>
            <h1 className="header-title">
              {currentSession?.title || 'Đặt câu hỏi pháp lý để bắt đầu'}
            </h1>
          </div>

          <div className="chat-mode-select">
            <label>Chế độ truy vấn</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="mix">Mix (Đề xuất)</option>
              <option value="hybrid">Hybrid</option>
              <option value="local">Local</option>
              <option value="global">Global</option>
              <option value="naive">Naive</option>
            </select>
          </div>
        </div>

        <div className="chat-messages">
          <div className="chat-messages-inner">
            {messages.length === 0 ? (
              <div className="welcome-grid">
                <div className="welcome-card">
                  <span className="welcome-tag">Trợ lý pháp luật</span>
                  <h2 className="welcome-title">Hỏi đúng luật, xem đúng nguồn.</h2>
                  <p className="welcome-desc">
                    Giao diện này tối ưu cho chat pháp lý: phản hồi streaming, trích dẫn nguồn rõ ràng,
                    và giữ lịch sử theo phiên để viết lại truy vấn chính xác hơn.
                  </p>
                  <div className="quick-prompts">
                    {quickPrompts.map((prompt) => (
                      <button
                        key={prompt}
                        className="quick-prompt-btn"
                        onClick={() => handleQuickPrompt(prompt)}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="welcome-card">
                  <div className="tips-label">Gợi ý sử dụng</div>
                  <ul className="tips-list">
                    <li>
                      <span className="dot">•</span>
                      <span>Chọn chế độ <strong>mix</strong> để ưu tiên chất lượng câu trả lời.</span>
                    </li>
                    <li>
                      <span className="dot">•</span>
                      <span>Mỗi câu trả lời có phần <strong>references</strong> để kiểm chứng nguồn.</span>
                    </li>
                    <li>
                      <span className="dot">•</span>
                      <span>Lịch sử hội thoại được lưu theo phiên, thuận tiện tra cứu lại.</span>
                    </li>
                  </ul>
                  <div className="tips-warning">
                    <strong>Lưu ý:</strong> AI có thể mắc sai lầm. Hãy kiểm tra lại các quy định quan trọng trước khi áp dụng vào thực tế.
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`msg-row ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <div className="msg-bubble-bot">
                      <div className="msg-bot-header">
                        <div className="msg-bot-avatar">AI</div>
                        <div>
                          <div className="msg-bot-label">Trợ lý pháp luật</div>
                          <div className="msg-bot-status">
                            {isStreaming && idx === messages.length - 1
                              ? 'Đang tra cứu và tổng hợp...'
                              : 'Phản hồi có trích dẫn'}
                          </div>
                        </div>
                      </div>

                      {msg.content === '' && isStreaming && idx === messages.length - 1 ? (
                        <div className="thinking-dots">
                          <div className="thinking-dots-anim">
                            <span /><span /><span />
                          </div>
                          <span>AI đang tra cứu luật pháp...</span>
                        </div>
                      ) : (
                        <div className="legal-markdown">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      )}

                      {msg.references?.length > 0 && (
                        <div className="msg-refs">
                          <div className="msg-refs-label">Nguồn trích dẫn</div>
                          <div className="msg-refs-list">
                            {msg.references.map((ref, ri) => (
                              <span key={ri} className="msg-ref-tag">
                                {ref.label || ref.file_path || 'Tài liệu liên quan'}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="msg-bubble-user">
                      <div className="msg-user-header">
                        <span className="msg-user-avatar">U</span>
                        Bạn
                      </div>
                      <div className="msg-user-content">{msg.content}</div>
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="chat-input-area">
          <form onSubmit={handleSubmit} className="chat-input-form">
            <textarea
              className="chat-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Nhập câu hỏi pháp lý của bạn..."
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              rows={2}
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={!input.trim() || isStreaming || (user && user.credits <= 0)}
            >
              {isStreaming ? 'Đang trả lời...' : 'Gửi'}
            </button>
          </form>
          <div className="chat-input-footer">
            AI có thể mắc sai lầm. Hãy kiểm tra lại thông tin quan trọng trước khi áp dụng.
          </div>
        </div>
      </main>
    </div>
  );
}
