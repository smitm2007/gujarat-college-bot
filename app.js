document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const messagesFeed = document.getElementById('messagesFeed');
  const welcomeCard = document.getElementById('welcomeCard');
  const queryInput = document.getElementById('queryInput');
  const sendBtn = document.getElementById('sendBtn');
  const voiceBtn = document.getElementById('voiceBtn');
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const helpBtn = document.getElementById('helpBtn');
  const aboutModal = document.getElementById('aboutModal');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const openSidebarBtn = document.getElementById('openSidebarBtn');
  const closeSidebarBtn = document.getElementById('closeSidebarBtn');
  const sidebar = document.getElementById('sidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const serverPillBadge = document.getElementById('serverPillBadge');

  // History & PDF DOM Elements
  const newChatBtn = document.getElementById('newChatBtn');
  const historyList = document.getElementById('historyList');
  const historyCount = document.getElementById('historyCount');
  const clearAllHistoryBtn = document.getElementById('clearAllHistoryBtn');
  const exportPdfBtn = document.getElementById('exportPdfBtn');
  const topbarExportPdfBtn = document.getElementById('topbarExportPdfBtn');
  const printDate = document.getElementById('printDate');

  // Supabase DOM Elements
  const supabaseBtn = document.getElementById('supabaseBtn');
  const supabaseStatusDot = document.getElementById('supabaseStatusDot');
  const supabaseBtnText = document.getElementById('supabaseBtnText');
  const sidebarDbIndicator = document.getElementById('sidebarDbIndicator');
  const sidebarDbDot = document.getElementById('sidebarDbDot');
  const sidebarDbText = document.getElementById('sidebarDbText');
  const supabaseModal = document.getElementById('supabaseModal');
  const closeSupabaseModalBtn = document.getElementById('closeSupabaseModalBtn');
  const modalDbStatusBanner = document.getElementById('modalDbStatusBanner');
  const modalDbPulseDot = document.getElementById('modalDbPulseDot');
  const modalDbStatusTitle = document.getElementById('modalDbStatusTitle');
  const modalDbStatusSub = document.getElementById('modalDbStatusSub');
  const supabaseUrlInput = document.getElementById('supabaseUrlInput');
  const supabaseKeyInput = document.getElementById('supabaseKeyInput');
  const saveSupabaseBtn = document.getElementById('saveSupabaseBtn');
  const syncToCloudBtn = document.getElementById('syncToCloudBtn');
  const pullFromCloudBtn = document.getElementById('pullFromCloudBtn');
  const supabaseFeedback = document.getElementById('supabaseFeedback');
  const copySqlBtn = document.getElementById('copySqlBtn');
  const schemaCodePreview = document.getElementById('schemaCodePreview');

  // State
  let sessions = [];
  let currentSessionId = null;
  let currentMessages = [];
  let isGenerating = false;
  let recognition = null;
  let isListening = false;
  let currentUtterance = null;
  let isBackendOnline = false;

  // Supabase Database State
  let supabaseState = {
    configured: false,
    url: '',
    key: ''
  };

  const isFileProtocol = window.location.protocol === 'file:';
  const API_BASE_URL = isFileProtocol ? 'http://127.0.0.1:8000' : '';

  function updateBackendBadge(online, text) {
    if (serverPillBadge) {
      serverPillBadge.textContent = text || (online ? 'Python Connected' : 'Browser Engine');
    }
  }

  // Theme Management
  const savedTheme = localStorage.getItem('gujaratedu_theme') || 
    (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', savedTheme);

  themeToggleBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('gujaratedu_theme', next);
  });

  // Check Backend Status silently
  function pingBackend() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);

    fetch(`${API_BASE_URL}/api/status`, { signal: controller.signal })
      .then(res => {
        clearTimeout(timeoutId);
        isBackendOnline = res.ok;
      })
      .catch(() => {
        clearTimeout(timeoutId);
        isBackendOnline = false;
      });
  }

  pingBackend();
  setInterval(pingBackend, 12000);

  // Mobile Sidebar Drawer with Backdrop Overlay
  function openMobileSidebar() {
    if (sidebar) sidebar.classList.add('open');
    if (sidebarOverlay) sidebarOverlay.classList.add('active');
  }

  function closeMobileSidebar() {
    if (sidebar) sidebar.classList.remove('open');
    if (sidebarOverlay) sidebarOverlay.classList.remove('active');
  }

  if (openSidebarBtn) {
    openSidebarBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openMobileSidebar();
    });
  }
  if (closeSidebarBtn) {
    closeSidebarBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeMobileSidebar();
    });
  }
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', () => {
      closeMobileSidebar();
    });
  }

  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 900 && sidebar && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && !openSidebarBtn.contains(e.target)) {
        closeMobileSidebar();
      }
    }
  });

  // Help Modal
  if (helpBtn) helpBtn.addEventListener('click', () => aboutModal.classList.add('open'));
  if (closeModalBtn) closeModalBtn.addEventListener('click', () => aboutModal.classList.remove('open'));
  aboutModal.addEventListener('click', (e) => {
    if (e.target === aboutModal) aboutModal.classList.remove('open');
  });

  // ==============================================================================
  // CHAT HISTORY & SESSION MANAGEMENT
  // ==============================================================================

  function loadSessions() {
    try {
      const data = localStorage.getItem('gujaratedu_chat_sessions');
      if (data) {
        sessions = JSON.parse(data);
      } else {
        sessions = [];
      }
    } catch (e) {
      sessions = [];
    }

    if (!Array.isArray(sessions)) {
      sessions = [];
    }

    sessions = sessions.filter(s => s && s.id && Array.isArray(s.messages));

    // Render History in Left Panel
    renderHistorySidebar();

    // Load active session or start a fresh session
    const lastActiveId = localStorage.getItem('gujaratedu_active_session_id');
    const existing = sessions.find(s => s.id === lastActiveId);
    if (existing) {
      switchSession(existing.id);
    } else if (sessions.length > 0) {
      switchSession(sessions[0].id);
    } else {
      startNewChat();
    }
  }

  function saveSessions() {
    try {
      if (sessions.length > 0) {
        localStorage.setItem('gujaratedu_chat_sessions', JSON.stringify(sessions));
        if (currentSessionId) {
          localStorage.setItem('gujaratedu_active_session_id', currentSessionId);
        }
      } else {
        localStorage.removeItem('gujaratedu_chat_sessions');
        localStorage.removeItem('gujaratedu_active_session_id');
      }
    } catch (e) {
      console.warn('Could not save sessions:', e);
    }
  }

  function renderHistorySidebar() {
    if (!historyList) return;
    historyList.innerHTML = '';
    historyCount.textContent = sessions.length;

    if (sessions.length === 0) {
      historyList.innerHTML = `
        <div class="history-empty">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin: 0 auto 8px auto; opacity: 0.5;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <p>No chat history yet.<br>Ask a question to save your consultation.</p>
        </div>
      `;
      return;
    }

    sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = `history-item ${sess.id === currentSessionId ? 'active' : ''}`;
      item.dataset.sessionId = sess.id;

      const dateStr = formatRelativeTime(sess.timestamp);

      item.innerHTML = `
        <div class="history-item-icon">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div class="history-item-content">
          <span class="history-item-title" title="${escapeHtml(sess.title)}">${escapeHtml(sess.title)}</span>
          <span class="history-item-time">${dateStr}</span>
        </div>
        <button class="history-delete-btn" title="Delete chat">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      `;

      item.addEventListener('click', (e) => {
        if (e.target.closest('.history-delete-btn')) {
          e.stopPropagation();
          deleteSession(sess.id);
          return;
        }
        switchSession(sess.id);
        if (window.innerWidth <= 900) {
          closeMobileSidebar();
        }
      });

      historyList.appendChild(item);
    });
  }

  function startNewChat() {
    currentSessionId = 'chat_' + Date.now();
    currentMessages = [];

    // Clear feed & show welcome card
    messagesFeed.innerHTML = '';
    const printHeader = document.getElementById('printHeader');
    if (printHeader) messagesFeed.appendChild(printHeader);

    if (welcomeCard) {
      messagesFeed.appendChild(welcomeCard);
      welcomeCard.style.display = 'flex';
    }

    if (sessions.length > 0) {
      localStorage.setItem('gujaratedu_active_session_id', currentSessionId);
    } else {
      localStorage.removeItem('gujaratedu_active_session_id');
    }
    renderHistorySidebar();
    if (window.innerWidth <= 900) {
      closeMobileSidebar();
    }
    queryInput.focus();
  }

  function switchSession(sessionId) {
    const sess = sessions.find(s => s.id === sessionId);
    if (!sess) return;

    currentSessionId = sess.id;
    currentMessages = sess.messages || [];

    // Update messages view
    messagesFeed.innerHTML = '';
    const printHeader = document.getElementById('printHeader');
    if (printHeader) messagesFeed.appendChild(printHeader);

    if (currentMessages.length === 0) {
      if (welcomeCard) {
        messagesFeed.appendChild(welcomeCard);
        welcomeCard.style.display = 'flex';
      }
    } else {
      if (welcomeCard) welcomeCard.style.display = 'none';
      currentMessages.forEach(msg => {
        renderMessageBubble(msg.role, msg.text, false, msg.date_str || (msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null));
      });
      scrollToBottom();
    }

    saveSessions();
    renderHistorySidebar();
  }

  // ==============================================================================
  // CENTERED CONFIRMATION DIALOG (APPEARS IN MIDDLE OF PAGE)
  // ==============================================================================
  function showCustomConfirm({
    title = 'Delete Chat Session?',
    message = 'Are you sure you want to delete this chat? This action cannot be undone.',
    confirmText = 'Delete'
  } = {}) {
    return new Promise((resolve) => {
      const modal = document.getElementById('deleteConfirmModal');
      const titleEl = document.getElementById('confirmModalTitle');
      const msgEl = document.getElementById('confirmModalMessage');
      const cancelBtn = document.getElementById('confirmCancelBtn');
      const deleteBtn = document.getElementById('confirmDeleteBtn');

      if (!modal || !cancelBtn || !deleteBtn) {
        resolve(window.confirm(message));
        return;
      }

      if (titleEl) titleEl.textContent = title;
      if (msgEl) msgEl.textContent = message;
      if (deleteBtn) deleteBtn.textContent = confirmText;

      let settled = false;

      function cleanup(res) {
        if (settled) return;
        settled = true;
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
        cancelBtn.removeEventListener('click', handleCancel);
        deleteBtn.removeEventListener('click', handleDelete);
        modal.removeEventListener('click', handleBackdrop);
        document.removeEventListener('keydown', handleKey);
        resolve(res);
      }

      function handleCancel(e) {
        if (e) e.preventDefault();
        cleanup(false);
      }

      function handleDelete(e) {
        if (e) e.preventDefault();
        cleanup(true);
      }

      function handleBackdrop(e) {
        if (e.target === modal) cleanup(false);
      }

      function handleKey(e) {
        if (e.key === 'Escape') cleanup(false);
        if (e.key === 'Enter') cleanup(true);
      }

      cancelBtn.addEventListener('click', handleCancel);
      deleteBtn.addEventListener('click', handleDelete);
      modal.addEventListener('click', handleBackdrop);
      document.addEventListener('keydown', handleKey);

      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      deleteBtn.focus();
    });
  }

  async function deleteSession(sessionId) {
    const sess = sessions.find(s => s.id === sessionId);
    const sessionTitle = sess && sess.title ? `"${sess.title}"` : 'this chat';

    // Show centered confirmation modal on page in middle
    const confirmed = await showCustomConfirm({
      title: 'Delete Chat Session?',
      message: `Are you sure you want to delete ${sessionTitle}? This will permanently remove it from your history.`,
      confirmText: 'Delete'
    });

    if (!confirmed) {
      return;
    }

    // 1. Remove from in-memory array
    sessions = sessions.filter(s => s.id !== sessionId);

    // 2. Immediately persist removal to localStorage
    try {
      localStorage.setItem('gujaratedu_chat_sessions', JSON.stringify(sessions));
      if (sessions.length === 0) {
        localStorage.removeItem('gujaratedu_chat_sessions');
        localStorage.removeItem('gujaratedu_active_session_id');
      }
    } catch (e) {
      console.warn('Could not update localStorage upon deletion:', e);
    }

    // 3. Delete from Supabase
    deleteSessionFromSupabase(sessionId);

    // 4. Update UI and active chat state
    if (currentSessionId === sessionId) {
      if (sessions.length > 0) {
        switchSession(sessions[0].id);
      } else {
        startNewChat();
      }
    } else {
      renderHistorySidebar();
    }
  }

  function formatRelativeTime(ts) {
    if (!ts) return 'Recent';
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24 && date.getDate() === now.getDate()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  // Button Listeners for History
  newChatBtn.addEventListener('click', startNewChat);

  clearAllHistoryBtn.addEventListener('click', async () => {
    if (sessions.length === 0) return;

    const confirmed = await showCustomConfirm({
      title: 'Delete All History?',
      message: 'Are you sure you want to delete ALL chat history? This will permanently delete all consultations.',
      confirmText: 'Delete All'
    });

    if (!confirmed) return;

    sessions = [];
    localStorage.removeItem('gujaratedu_chat_sessions');
    localStorage.removeItem('gujaratedu_active_session_id');
    clearAllFromSupabase();
    startNewChat();
  });

  // ==============================================================================
  // EXPORT TO PDF
  // ==============================================================================

  function exportChatAsPdf() {
    if (currentMessages.length === 0) {
      alert("Please ask at least one question before exporting a PDF advisory report.");
      return;
    }

    // Set printed date
    if (printDate) {
      printDate.textContent = `Generated on: ${new Date().toLocaleString()}`;
    }

    // Trigger browser PDF printing
    window.print();
  }

  if (exportPdfBtn) exportPdfBtn.addEventListener('click', exportChatAsPdf);
  if (topbarExportPdfBtn) topbarExportPdfBtn.addEventListener('click', exportChatAsPdf);

  // ==============================================================================
  // SUPABASE DATABASE SYNC & PERSISTENCE
  // ==============================================================================

  function updateSupabaseUiStatus(isConfigured, customMsg = null) {
    supabaseState.configured = isConfigured;
    if (isConfigured) {
      if (supabaseStatusDot) supabaseStatusDot.classList.add('connected');
      if (sidebarDbDot) sidebarDbDot.classList.add('connected');
      if (sidebarDbText) sidebarDbText.textContent = 'Supabase: Cloud Sync Active';
      if (modalDbPulseDot) modalDbPulseDot.style.background = '#10b981';
      if (modalDbStatusTitle) modalDbStatusTitle.textContent = customMsg || 'Supabase Cloud Database: Connected';
      if (modalDbStatusBanner) modalDbStatusBanner.classList.add('connected');
    } else {
      if (supabaseStatusDot) supabaseStatusDot.classList.remove('connected');
      if (sidebarDbDot) sidebarDbDot.classList.remove('connected');
      if (sidebarDbText) sidebarDbText.textContent = 'Supabase: Local Cache (Click to Connect)';
      if (modalDbPulseDot) modalDbPulseDot.style.background = '#94a3b8';
      if (modalDbStatusTitle) modalDbStatusTitle.textContent = customMsg || 'Supabase Cloud Database: Not Configured';
      if (modalDbStatusBanner) modalDbStatusBanner.classList.remove('connected');
    }
  }

  function showSupabaseFeedback(msg, type = 'success') {
    if (!supabaseFeedback) return;
    supabaseFeedback.textContent = msg;
    supabaseFeedback.className = `form-feedback ${type}`;
    supabaseFeedback.style.display = 'block';
  }

  function fetchSupabaseConfig() {
    fetch(`${API_BASE_URL}/api/supabase/config`)
      .then(res => res.json())
      .then(data => {
        if (data.configured) {
          supabaseState.configured = true;
          supabaseState.url = data.supabase_url;
          if (supabaseUrlInput) supabaseUrlInput.value = data.supabase_url;
          if (supabaseKeyInput && data.masked_key) supabaseKeyInput.placeholder = `Key Saved (${data.masked_key})`;
          updateSupabaseUiStatus(true);
          try {
            const curLocal = JSON.parse(localStorage.getItem('gujaratedu_supabase_config') || '{}');
            if (curLocal.key) supabaseState.key = curLocal.key;
          } catch(e){}
        } else {
          try {
            const localCfg = JSON.parse(localStorage.getItem('gujaratedu_supabase_config') || '{}');
            if (localCfg.url && localCfg.key) {
              supabaseState.url = localCfg.url;
              supabaseState.key = localCfg.key;
              supabaseState.configured = true;
              if (supabaseUrlInput) supabaseUrlInput.value = localCfg.url;
              if (supabaseKeyInput) supabaseKeyInput.value = localCfg.key;
              updateSupabaseUiStatus(true);
              // Auto-sync client credentials to backend
              fetch(`${API_BASE_URL}/api/supabase/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ supabase_url: localCfg.url, supabase_key: localCfg.key })
              }).catch(() => {});
            } else {
              updateSupabaseUiStatus(false);
            }
          } catch (e) {
            updateSupabaseUiStatus(false);
          }
        }
      })
      .catch(() => {
        try {
          const localCfg = JSON.parse(localStorage.getItem('gujaratedu_supabase_config') || '{}');
          if (localCfg.url && localCfg.key) {
            supabaseState.url = localCfg.url;
            supabaseState.key = localCfg.key;
            supabaseState.configured = true;
            if (supabaseUrlInput) supabaseUrlInput.value = localCfg.url;
            if (supabaseKeyInput) supabaseKeyInput.value = localCfg.key;
            updateSupabaseUiStatus(true);
          } else {
            updateSupabaseUiStatus(false);
          }
        } catch (e) {
          updateSupabaseUiStatus(false);
        }
      });
  }

  function persistMessageToSupabase(sessionId, sessionTitle, role, text, createdAt, dateStr) {
    if (!supabaseState.configured && !supabaseState.url) return;

    const payload = {
      session_id: sessionId,
      session_title: sessionTitle || 'Consultation',
      role: role,
      message_text: text,
      created_at: createdAt || new Date().toISOString(),
      date_str: dateStr || new Date().toLocaleString(),
      supabase_url: supabaseState.url,
      supabase_key: supabaseState.key
    };

    if (isBackendOnline) {
      fetch(`${API_BASE_URL}/api/supabase/save_message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(res => res.json())
      .then(data => {
        if (data.status !== 'success') {
          console.warn('[Supabase Backend Save Warning]:', data.error);
          saveDirectlyToSupabase(payload);
        } else {
          console.log(`[Supabase] Persisted ${role} message successfully via backend`);
        }
      })
      .catch(err => {
        console.warn('Backend save error, attempting direct save:', err);
        saveDirectlyToSupabase(payload);
      });
    } else {
      saveDirectlyToSupabase(payload);
    }
  }

  function saveDirectlyToSupabase(payload) {
    const url = (supabaseState.url || '').replace(/\/+$/, '');
    const key = supabaseState.key;
    if (!url || !key) return;

    const postgrestPayload = {
      session_id: payload.session_id,
      session_title: payload.session_title,
      role: payload.role,
      message_text: payload.message_text,
      created_at: payload.created_at,
      date_str: payload.date_str
    };

    fetch(`${url}/rest/v1/chat_history`, {
      method: 'POST',
      headers: {
        'apikey': key,
        'Authorization': `Bearer ${key}`,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
      },
      body: JSON.stringify(postgrestPayload)
    })
    .then(async res => {
      if (!res.ok) {
        const errText = await res.text();
        console.error(`[Supabase Direct Insert Error HTTP ${res.status}]:`, errText);
        if (errText.includes('42501') || errText.toLowerCase().includes('row-level security') || res.status === 403) {
          showSupabaseFeedback('⚠️ RLS Error: Run "ALTER TABLE public.chat_history DISABLE ROW LEVEL SECURITY;" in Supabase SQL Editor.', 'error');
        } else if (res.status === 404 || errText.includes('PGRST205')) {
          showSupabaseFeedback('⚠️ Table "chat_history" was not found in Supabase! Run the SQL schema to create it.', 'error');
        }
      } else {
        console.log(`[Supabase] Persisted ${payload.role} message successfully via direct client fetch`);
      }
    })
    .catch(err => console.error('[Supabase Network Error]:', err));
  }

  function deleteSessionFromSupabase(sessionId) {
    if (isBackendOnline) {
      fetch(`${API_BASE_URL}/api/supabase/delete_session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          supabase_url: supabaseState.url,
          supabase_key: supabaseState.key
        })
      }).catch(() => {});
    }
    if (supabaseState.url && supabaseState.key) {
      fetch(`${supabaseState.url.replace(/\/+$/, '')}/rest/v1/chat_history?session_id=eq.${encodeURIComponent(sessionId)}`, {
        method: 'DELETE',
        headers: {
          'apikey': supabaseState.key,
          'Authorization': `Bearer ${supabaseState.key}`
        }
      }).catch(() => {});
    }
  }

  function clearAllFromSupabase() {
    if (isBackendOnline) {
      fetch(`${API_BASE_URL}/api/supabase/clear_all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supabase_url: supabaseState.url,
          supabase_key: supabaseState.key
        })
      }).catch(() => {});
    }
    if (supabaseState.url && supabaseState.key) {
      fetch(`${supabaseState.url.replace(/\/+$/, '')}/rest/v1/chat_history?id=neq.00000000-0000-0000-0000-000000000000`, {
        method: 'DELETE',
        headers: {
          'apikey': supabaseState.key,
          'Authorization': `Bearer ${supabaseState.key}`
        }
      }).catch(() => {});
    }
  }

  async function syncLocalToCloud() {
    if (sessions.length === 0) {
      showSupabaseFeedback('No local chat sessions found to sync.', 'error');
      return;
    }

    showSupabaseFeedback('Syncing chats and dates to Supabase...', 'success');

    const allMessages = [];
    sessions.forEach(sess => {
      (sess.messages || []).forEach(m => {
        allMessages.push({
          session_id: sess.id,
          session_title: sess.title,
          role: m.role,
          message_text: m.text,
          created_at: m.created_at || (m.timestamp ? new Date(m.timestamp).toISOString() : new Date().toISOString()),
          date_str: m.date_str || (m.timestamp ? new Date(m.timestamp).toLocaleString() : '')
        });
      });
    });

    if (isBackendOnline) {
      try {
        const res = await fetch(`${API_BASE_URL}/api/supabase/sync_batch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: allMessages,
            supabase_url: supabaseState.url,
            supabase_key: supabaseState.key
          })
        });
        const data = await res.json();
        if (data.status === 'success') {
          showSupabaseFeedback(`✅ Successfully synced ${data.saved_count} messages across ${sessions.length} sessions to Supabase!`, 'success');
        } else {
          showSupabaseFeedback(`Sync error: ${data.error || 'Check Supabase table'}`, 'error');
        }
      } catch (err) {
        showSupabaseFeedback(`Sync error: ${err.message}`, 'error');
      }
    } else if (supabaseState.url && supabaseState.key) {
      try {
        const res = await fetch(`${supabaseState.url.replace(/\/+$/, '')}/rest/v1/chat_history`, {
          method: 'POST',
          headers: {
            'apikey': supabaseState.key,
            'Authorization': `Bearer ${supabaseState.key}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(allMessages)
        });
        if (res.ok) {
          showSupabaseFeedback(`✅ Successfully uploaded ${allMessages.length} messages to Supabase!`, 'success');
        } else {
          const errTxt = await res.text();
          showSupabaseFeedback(`Supabase error: ${errTxt}`, 'error');
        }
      } catch (err) {
        showSupabaseFeedback(`Sync failed: ${err.message}`, 'error');
      }
    } else {
      showSupabaseFeedback('Please enter and save Supabase credentials first.', 'error');
    }
  }

  async function pullFromCloud() {
    showSupabaseFeedback('Fetching chat history from Supabase...', 'success');

    let rows = [];
    if (isBackendOnline) {
      try {
        const res = await fetch(`${API_BASE_URL}/api/supabase/history`);
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.data)) {
          rows = data.data;
        } else {
          showSupabaseFeedback(`Failed to load history: ${data.error || 'Empty response'}`, 'error');
          return;
        }
      } catch (err) {
        showSupabaseFeedback(`Load error: ${err.message}`, 'error');
        return;
      }
    } else if (supabaseState.url && supabaseState.key) {
      try {
        const res = await fetch(`${supabaseState.url.replace(/\/+$/, '')}/rest/v1/chat_history?order=created_at.asc`, {
          headers: {
            'apikey': supabaseState.key,
            'Authorization': `Bearer ${supabaseState.key}`
          }
        });
        if (res.ok) {
          rows = await res.json();
        } else {
          const errTxt = await res.text();
          showSupabaseFeedback(`Supabase error: ${errTxt}`, 'error');
          return;
        }
      } catch (err) {
        showSupabaseFeedback(`Fetch failed: ${err.message}`, 'error');
        return;
      }
    } else {
      showSupabaseFeedback('Please enter and save Supabase credentials first.', 'error');
      return;
    }

    if (!Array.isArray(rows) || rows.length === 0) {
      showSupabaseFeedback('Connected to Supabase! No past chat history rows found in table.', 'success');
      return;
    }

    const sessionMap = new Map();
    rows.forEach(r => {
      const sId = r.session_id || 'chat_cloud';
      if (!sessionMap.has(sId)) {
        sessionMap.set(sId, {
          id: sId,
          title: r.session_title || (r.message_text ? r.message_text.slice(0, 48) : 'Consultation'),
          timestamp: r.created_at ? new Date(r.created_at).getTime() : Date.now(),
          messages: []
        });
      }
      const sess = sessionMap.get(sId);
      sess.messages.push({
        role: r.role,
        text: r.message_text,
        created_at: r.created_at,
        date_str: r.date_str || (r.created_at ? new Date(r.created_at).toLocaleString() : ''),
        timestamp: r.created_at ? new Date(r.created_at).getTime() : Date.now()
      });
      if (r.created_at) {
        sess.timestamp = Math.max(sess.timestamp, new Date(r.created_at).getTime());
      }
    });

    sessions = Array.from(sessionMap.values()).sort((a, b) => b.timestamp - a.timestamp);
    saveSessions();
    renderHistorySidebar();
    if (sessions.length > 0) {
      switchSession(sessions[0].id);
    }
    showSupabaseFeedback(`✅ Successfully loaded ${rows.length} messages across ${sessions.length} sessions from Supabase!`, 'success');
  }

  // Supabase Modal & Buttons Event Listeners
  if (supabaseBtn) {
    supabaseBtn.addEventListener('click', () => {
      if (supabaseModal) supabaseModal.classList.add('open');
    });
  }
  if (sidebarDbIndicator) {
    sidebarDbIndicator.addEventListener('click', () => {
      if (supabaseModal) supabaseModal.classList.add('open');
    });
  }
  if (closeSupabaseModalBtn) {
    closeSupabaseModalBtn.addEventListener('click', () => {
      if (supabaseModal) supabaseModal.classList.remove('open');
    });
  }
  if (supabaseModal) {
    supabaseModal.addEventListener('click', (e) => {
      if (e.target === supabaseModal) supabaseModal.classList.remove('open');
    });
  }

  if (saveSupabaseBtn) {
    saveSupabaseBtn.addEventListener('click', async () => {
      const url = (supabaseUrlInput ? supabaseUrlInput.value : '').trim();
      const key = (supabaseKeyInput ? supabaseKeyInput.value : '').trim();

      if (!url || !key) {
        showSupabaseFeedback('Please enter both Supabase Project URL and Anon API Key.', 'error');
        return;
      }

      showSupabaseFeedback('Verifying Read & Write access to table public.chat_history...', 'success');

      // Save to localStorage immediately
      supabaseState.url = url;
      supabaseState.key = key;
      localStorage.setItem('gujaratedu_supabase_config', JSON.stringify({ url, key }));

      if (isBackendOnline) {
        try {
          const testRes = await fetch(`${API_BASE_URL}/api/supabase/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ supabase_url: url, supabase_key: key })
          });
          const testData = await testRes.json();
          if (testData.status === 'success') {
            await fetch(`${API_BASE_URL}/api/supabase/config`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ supabase_url: url, supabase_key: key })
            });
            supabaseState.configured = true;
            updateSupabaseUiStatus(true, 'Supabase Cloud Database: Connected & Verified');
            showSupabaseFeedback('✅ Connected! Read & Write access verified on public.chat_history.', 'success');
          } else {
            supabaseState.configured = false;
            updateSupabaseUiStatus(false, 'Supabase Configuration Error');
            if (testData.rls_blocked) {
              showSupabaseFeedback('⚠️ Row-Level Security (RLS) is blocking inserts!\n\nRun this in Supabase SQL Editor:\nALTER TABLE public.chat_history DISABLE ROW LEVEL SECURITY;', 'error');
            } else if (testData.table_missing) {
              showSupabaseFeedback('⚠️ Table "public.chat_history" was NOT found! Click "Copy SQL" below and run it in Supabase SQL Editor.', 'error');
            } else {
              showSupabaseFeedback(`Connection error: ${testData.error || 'Check URL and Key'}`, 'error');
            }
          }
        } catch (e) {
          testDirectlyFromClient(url, key);
        }
      } else {
        testDirectlyFromClient(url, key);
      }
    });
  }

  async function testDirectlyFromClient(url, key) {
    const cleanUrl = url.replace(/\/+$/, '');
    try {
      // 1. Test Read Access
      const readRes = await fetch(`${cleanUrl}/rest/v1/chat_history?limit=1`, {
        headers: {
          'apikey': key,
          'Authorization': `Bearer ${key}`
        }
      });

      if (!readRes.ok) {
        const errText = await readRes.text();
        supabaseState.configured = false;
        updateSupabaseUiStatus(false);
        if (readRes.status === 404 || errText.includes('PGRST205') || errText.includes('does not exist')) {
          showSupabaseFeedback('⚠️ Table "public.chat_history" was NOT found! Please run the SQL schema in Supabase SQL Editor.', 'error');
        } else {
          showSupabaseFeedback(`Read test failed (HTTP ${readRes.status}): ${errText}`, 'error');
        }
        return;
      }

      // 2. Test Write / Insert Access
      const pingPayload = {
        session_id: '_ping_test_',
        session_title: 'Connection Test',
        role: 'system',
        message_text: 'Ping verify write permission',
        created_at: new Date().toISOString(),
        date_str: 'Test Ping'
      };

      const writeRes = await fetch(`${cleanUrl}/rest/v1/chat_history`, {
        method: 'POST',
        headers: {
          'apikey': key,
          'Authorization': `Bearer ${key}`,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal'
        },
        body: JSON.stringify(pingPayload)
      });

      if (!writeRes.ok) {
        const writeErr = await writeRes.text();
        supabaseState.configured = false;
        updateSupabaseUiStatus(false);
        if (writeRes.status === 401 || writeRes.status === 403 || writeErr.includes('42501') || writeErr.toLowerCase().includes('row-level security')) {
          showSupabaseFeedback('⚠️ Row-Level Security (RLS) is blocking inserts! Run this in Supabase SQL Editor:\n\nALTER TABLE public.chat_history DISABLE ROW LEVEL SECURITY;', 'error');
        } else {
          showSupabaseFeedback(`Write test failed (HTTP ${writeRes.status}): ${writeErr}`, 'error');
        }
        return;
      }

      // 3. Clean up test row
      fetch(`${cleanUrl}/rest/v1/chat_history?session_id=eq._ping_test_`, {
        method: 'DELETE',
        headers: {
          'apikey': key,
          'Authorization': `Bearer ${key}`
        }
      }).catch(() => {});

      supabaseState.configured = true;
      updateSupabaseUiStatus(true, 'Supabase Cloud Database: Connected & Verified');
      showSupabaseFeedback('✅ Full Read & Write access to table public.chat_history verified successfully!', 'success');
    } catch (netErr) {
      showSupabaseFeedback(`Network test error: ${netErr.message}. Verify that URL starts with https://`, 'error');
    }
  }

  if (syncToCloudBtn) syncToCloudBtn.addEventListener('click', syncLocalToCloud);
  if (pullFromCloudBtn) pullFromCloudBtn.addEventListener('click', pullFromCloud);

  if (copySqlBtn && schemaCodePreview) {
    copySqlBtn.addEventListener('click', () => {
      const sqlText = schemaCodePreview.textContent;
      navigator.clipboard.writeText(sqlText).then(() => {
        copySqlBtn.classList.add('copied');
        copySqlBtn.querySelector('span').textContent = 'Copied!';
        setTimeout(() => {
          copySqlBtn.classList.remove('copied');
          copySqlBtn.querySelector('span').textContent = 'Copy SQL';
        }, 2000);
      });
    });
  }

  // ==============================================================================
  // INPUT & SUBMISSION
  // ==============================================================================

  queryInput.addEventListener('input', () => {
    queryInput.style.height = 'auto';
    queryInput.style.height = Math.min(queryInput.scrollHeight, 140) + 'px';
    sendBtn.disabled = !queryInput.value.trim() || isGenerating;
  });

  queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) {
        handleSubmit();
      }
    }
  });

  sendBtn.addEventListener('click', () => {
    if (!sendBtn.disabled) {
      handleSubmit();
    }
  });

  // Voice Input (Web Speech API)
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-IN';

    recognition.onstart = () => {
      isListening = true;
      voiceBtn.classList.add('listening');
      queryInput.placeholder = 'Listening... Speak your question now';
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      queryInput.value = transcript;
      queryInput.dispatchEvent(new Event('input'));
      queryInput.focus();
    };

    recognition.onerror = () => stopListening();
    recognition.onend = () => stopListening();

    voiceBtn.addEventListener('click', () => {
      if (!isListening) {
        try {
          recognition.start();
        } catch (e) {
          stopListening();
        }
      } else {
        recognition.stop();
        stopListening();
      }
    });
  } else {
    voiceBtn.style.display = 'none';
  }

  function stopListening() {
    isListening = false;
    voiceBtn.classList.remove('listening');
    queryInput.placeholder = "Ask anything about 12th Science in Gujarat (e.g., 'DA-IICT vs Nirma', 'MBBS cutoffs')...";
  }

  // Global Chip / Prompt Button Clicks
  document.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-query]');
    if (chip) {
      const query = chip.getAttribute('data-query');
      if (query) {
        submitDirectQuery(query);
      }
    }
  });

  function handleSubmit() {
    const query = queryInput.value.trim();
    if (!query || isGenerating) return;

    queryInput.value = '';
    queryInput.style.height = 'auto';
    sendBtn.disabled = true;

    submitDirectQuery(query);
  }

  function submitDirectQuery(query) {
    if (isGenerating) return;

    if (welcomeCard) {
      welcomeCard.style.display = 'none';
    }

    const now = new Date();
    const createdAt = now.toISOString();
    const dateStr = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) + ', ' +
                    now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Append to current session
    renderMessageBubble('user', query, true, dateStr);
    currentMessages.push({
      role: 'user',
      text: query,
      created_at: createdAt,
      date_str: dateStr,
      timestamp: now.getTime()
    });

    // Update session title & timestamp in history
    let activeSess = sessions.find(s => s.id === currentSessionId);
    if (!activeSess) {
      activeSess = {
        id: currentSessionId,
        title: query.slice(0, 48),
        timestamp: now.getTime(),
        messages: currentMessages
      };
      sessions.unshift(activeSess);
    } else {
      activeSess.timestamp = now.getTime();
      activeSess.messages = currentMessages;
      if (activeSess.messages.length === 1) {
        activeSess.title = query.slice(0, 48);
      }
    }
    saveSessions();
    renderHistorySidebar();

    // Show Typing Indicator
    isGenerating = true;
    sendBtn.disabled = true;
    const typingRow = showTypingIndicator();
    scrollToBottom();

    // Try Backend API First with a 3.5s timeout; fall back to client engine seamlessly
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query,
        session_id: currentSessionId,
        session_title: activeSess.title,
        supabase_url: supabaseState.url,
        supabase_key: supabaseState.key
      }),
      signal: controller.signal
    })
      .then(res => {
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        removeTypingIndicator(typingRow);
        updateBackendBadge(true, 'Python Server Connected');
        const answer = data.answer || resolveClientQuery(query);
        const botNow = new Date();
        const botCreatedAt = data.created_at || botNow.toISOString();
        const botDateStr = data.date_str || (botNow.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) + ', ' + botNow.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

        renderMessageBubble('bot', answer, true, botDateStr);
        currentMessages.push({
          role: 'bot',
          text: answer,
          created_at: botCreatedAt,
          date_str: botDateStr,
          timestamp: botNow.getTime()
        });
        activeSess.messages = currentMessages;
        saveSessions();

        // If backend did not save to Supabase, persist via client
        if (!data.supabase_saved) {
          persistMessageToSupabase(currentSessionId, activeSess.title, 'user', query, createdAt, dateStr);
          persistMessageToSupabase(currentSessionId, activeSess.title, 'bot', answer, botCreatedAt, botDateStr);
        }
      })
      .catch(() => {
        clearTimeout(timeoutId);
        removeTypingIndicator(typingRow);
        isBackendOnline = false;

        const fallbackAnswer = resolveClientQuery(query);
        const botNow = new Date();
        const botCreatedAt = botNow.toISOString();
        const botDateStr = botNow.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) + ', ' + botNow.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        renderMessageBubble('bot', fallbackAnswer, true, botDateStr);
        currentMessages.push({
          role: 'bot',
          text: fallbackAnswer,
          created_at: botCreatedAt,
          date_str: botDateStr,
          timestamp: botNow.getTime()
        });
        activeSess.messages = currentMessages;
        saveSessions();

        // Persist directly to Supabase
        persistMessageToSupabase(currentSessionId, activeSess.title, 'user', query, createdAt, dateStr);
        persistMessageToSupabase(currentSessionId, activeSess.title, 'bot', fallbackAnswer, botCreatedAt, botDateStr);
      })
      .finally(() => {
        isGenerating = false;
        sendBtn.disabled = !queryInput.value.trim();
        queryInput.focus();
        scrollToBottom();
      });
  }

  // Render Message Bubble
  function renderMessageBubble(role, text, animate = true, dateStr = null) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    if (!animate) row.style.animation = 'none';

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    if (role === 'user') {
      avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    } else {
      avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>`;
    }

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    if (role === 'user') {
      bubble.textContent = text;
    } else {
      bubble.innerHTML = renderMarkdown(text);

      const toolbar = document.createElement('div');
      toolbar.className = 'bot-actions-toolbar';

      const copyBtn = document.createElement('button');
      copyBtn.className = 'action-pill-btn';
      copyBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg><span>Copy</span>`;
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.classList.add('copied');
          copyBtn.querySelector('span').textContent = 'Copied!';
          setTimeout(() => {
            copyBtn.classList.remove('copied');
            copyBtn.querySelector('span').textContent = 'Copy';
          }, 2000);
        });
      });

      toolbar.appendChild(copyBtn);

      if ('speechSynthesis' in window) {
        const speakBtn = document.createElement('button');
        speakBtn.className = 'action-pill-btn';
        speakBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg><span>Listen</span>`;
        speakBtn.addEventListener('click', () => {
          if (window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
            speakBtn.querySelector('span').textContent = 'Listen';
          } else {
            const cleanSpoken = text.replace(/[#*`_\[\]()]/g, ' ').replace(/>\s*\[!.*?\]/g, 'Note:');
            currentUtterance = new SpeechSynthesisUtterance(cleanSpoken);
            currentUtterance.rate = 1.05;
            currentUtterance.onend = () => {
              speakBtn.querySelector('span').textContent = 'Listen';
            };
            speakBtn.querySelector('span').textContent = 'Stop';
            window.speechSynthesis.speak(currentUtterance);
          }
        });
        toolbar.appendChild(speakBtn);
      }

      bubble.appendChild(toolbar);
    }

    // Attach timestamp below message content
    const timeDisplay = document.createElement('div');
    timeDisplay.className = 'message-timestamp';
    timeDisplay.textContent = dateStr || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    bubble.appendChild(timeDisplay);

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesFeed.appendChild(row);
    scrollToBottom();
  }

  function showTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'message-row bot typing-row';

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble typing-bubble';
    bubble.innerHTML = `
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    `;

    row.appendChild(avatar);
    row.appendChild(bubble);
    messagesFeed.appendChild(row);
    return row;
  }

  function removeTypingIndicator(row) {
    if (row && row.parentNode) {
      row.parentNode.removeChild(row);
    }
  }

  function scrollToBottom() {
    messagesFeed.scrollTop = messagesFeed.scrollHeight;
  }

  // ==============================================================================
  // ACCURATE CLIENT-SIDE DETERMINISTIC QA ROUTER
  // ==============================================================================

  function resolveClientQuery(query) {
    const k = window.GUJARATEDU_KNOWLEDGE || {};
    const insts = k.institutions || [];
    const qLower = query.toLowerCase().trim();

    // 1. Dynamic Multi-Criteria Listing (Checked FIRST, except for pure fee/cutoff/jee queries)
    const listResult = parseAndFilterOffline(qLower, insts);
    if (listResult) {
      return listResult;
    }

    // 2. Colleges Accepting JEE Main
    if (/\b(jee main.*colleges?|colleges?.*jee main|accept.*jee main|jee main seats?)\b/.test(qLower)) {
      return k.jee_main_colleges || "Colleges in Gujarat accepting JEE Main scores include SVNIT Surat, IIIT Vadodara, IIIT Surat, DA-IICT, Nirma University, PDEU, Ahmedabad University, and the 5% All India quota in Government Engineering Colleges.";
    }

    // 3. Is GUJCET Compulsory?
    if (/\b(is gujcet (?:compulsory|mandatory|required)|without gujcet|admission without gujcet|can i get.*without gujcet)\b/.test(qLower)) {
      return k.gujcet_compulsory || "GUJCET is compulsory for 95% State Quota seats in Government Colleges and 50% seats in Private colleges under ACPC.";
    }

    // 4. Low Marks / Low Percentile Options
    if (/\b(low marks?|low percentile|less marks?|average marks?|bad marks?|poor marks?|failed in neet|low rank)\b/.test(qLower)) {
      return k.low_marks || "Career pathways for low marks in 12th science in Gujarat.";
    }

    // 5. Specific College Lookup
    const college = findCollegeOffline(qLower, insts);

    // 6. Fees & Scholarships
    if (/\b(fees?|fee structure|costs?|tuitions?|scholarships?|mysy|tfws|kanya kelavani|free education)\b/.test(qLower)) {
      if (college) {
        return `### Fee Structure & Scholarships: ${college.name}

- **Institution Type:** ${college.type}
- **Annual Fees:** ${college.fees || 'Refer to official ACPC brochure.'}
- **Average Placement Package:** ${college.avg_package || 'N/A'}

#### Applicable Gujarat Government Scholarships:
1. **MYSY (Mukhyamantri Yuva Swavalamban Yojana):**
   - **50% tuition subsidy up to ₹50,000/year** for Engineering/Pharmacy; **up to ₹2,00,000/year** for Medical (MBBS).
   - Eligibility: Class 12 Science Board percentile 80 or above, family annual income below ₹6 Lakh.
2. **Kanya Kelavani Policy:**
   - **100% FREE Tuition Fees for all female students** in State Government Engineering and Polytechnic Colleges!
3. **TFWS (Tuition Fee Waiver Scheme):**
   - **100% Tuition Fee Exemption** for 5% supernumerary seats in every branch under ACPC counseling on merit.`;
      }
      if (/\b(medical|mbbs|bds|doctor)\b/.test(qLower)) {
        return k.medical_fees || "Medical tuition fees in Gujarat: Govt colleges are ₹25,000/year; GMERS colleges are ₹3,30,000/year (MYSY reimburses up to ₹2,00,000); Private colleges are ₹6,00,000 - ₹8,50,000/year.";
      }
      if (/\b(engineering|b\.?tech|b\.?e)\b/.test(qLower)) {
        return k.engineering_fees || "Engineering tuition fees in Gujarat: Government colleges charge ₹1,500/year for boys and 100% FREE for girls under Kanya Kelavani; Grant-in-aid are ₹3k-₹5k; Private universities range from ₹78k to ₹2.6L/year.";
      }
      return k.scholarships || "Gujarat Science scholarships: MYSY, Kanya Kelavani, TFWS.";
    }

    // 7. Placements & Packages
    if (/\b(placements?|packages?|highest package|average package|salaries|salary|recruiters?)\b/.test(qLower)) {
      if (college) {
        return `### Placements & Packages: ${college.name}

- **Average Placement CTC:** **${college.avg_package || 'N/A'}**
- **Highest Placement CTC:** **${college.highest_package || 'N/A'}**
- **Top Recruiters:** ${(college.top_recruiters || ['Leading technology & healthcare recruiters']).join(', ')}
- **Cutoff & Admission Route:** ${college.cutoffs || 'Admissions via ACPC / National Entrance'}

#### Overview & Highlights:
${college.overview || ''}`;
      }
      return k.placements_general || "Placement statistics across Gujarat institutions.";
    }

    // 8. Cutoffs & Merit
    if (/\b(cutoffs?|cut off|closing ranks?|merit ranks?|percentile needed|how many marks)\b/.test(qLower)) {
      if (college) {
        return `### Admission Cutoffs & Merit Ranks: ${college.name}

- **Entrance Exams:** ${(college.exams || ['GUJCET', 'JEE Main']).join(', ')}
- **Cutoff / Closing Rank Trends:** ${college.cutoffs || 'Refer to ACPC portal.'}
- **Annual Fees:** ${college.fees || 'N/A'}

#### Gujarat ACPC Merit Formula (Engineering):
- **50% Weightage:** Class 12 Board theory percentile in PCM.
- **50% Weightage:** GUJCET Examination percentile.`;
      }
      if (/\b(medical|mbbs|bds|neet)\b/.test(qLower)) {
        return `### Medical (MBBS / BDS) NEET-UG Cutoffs in Gujarat (85% State Quota)

#### 1. State Government Medical Colleges (NEET-UG Closing Score Trends):
1. **B.J. Medical College (BJMC), Ahmedabad:** NEET Score **645 - 670+** (General Merit Rank Top 150)
2. **Government Medical College (GMC), Baroda:** NEET Score **625 - 650+**
3. **Government Medical College (GMC), Surat:** NEET Score **615 - 640+**
4. **PDU Government Medical College, Rajkot:** NEET Score **605 - 630+**
5. **Government Medical College, Bhavnagar:** NEET Score **595 - 620+**
6. **M.P. Shah Government Medical College, Jamnagar:** NEET Score **590 - 615+**

#### 2. GMERS Medical Colleges (Government Quota in Society Colleges):
- **GMERS Sola, Gandhinagar, Gotri, Himmatnagar, etc.:** NEET Score **560 - 610+** (Eligible for MYSY scholarship up to ₹2 Lakh/year!).

#### 3. Municipal & Trust Medical Colleges (NHL Municipal, SMIMER):
- **Government Quota:** NEET Score **550 - 595+**
- **Management Quota:** NEET Score **480 - 540+**`;
      }
      return k.cutoffs_general || "Cutoff benchmarks for Engineering & Medical admissions in Gujarat.";
    }

    // 9. College Comparisons
    if (/\b(vs\.?|versus|compare|comparison)\b/.test(qLower)) {
      if ((qLower.includes('daiict') || qLower.includes('da-iict')) && qLower.includes('nirma')) {
        return `### Comprehensive Comparison: DA-IICT Gandhinagar vs. Nirma University

| Metric | DA-IICT Gandhinagar | Nirma University (ITNU) |
| :--- | :--- | :--- |
| **Location** | Gandhinagar | Ahmedabad (SG Highway) |
| **Type** | Private University (Autonomous) | Private University |
| **Average Package** | **₹16.5 LPA** | **B.Tech CSE: ₹8.5 - ₹9.5 LPA** |
| **Highest Package** | **₹54+ LPA (International ~₹1.2 Cr)** | **₹46 LPA** |
| **Annual Fees** | Tuition: Approx ₹2,20,000 - ₹2,40,000/yr | B.Tech: Approx ₹2,15,000 - ₹2,30,000/yr |
| **ACPC Cutoff** | Rank ~150 - 250 for ICT/MnC | Rank ~350 - 550 for CSE |
| **Exams** | JEE Main, GUJCET / ACPC | GUJCET / ACPC, JEE Main |

#### Analysis & Recommendation:
- **Choose DA-IICT if:** You prioritize specialized ICT/Computer Science education and ₹16.5 LPA placement packages.
- **Choose Nirma if:** You seek diverse branch options, modern 115-acre campus on SG Highway Ahmedabad, and deep alumni connections.`;
      }
    }

    // 10. Direct College Profile
    if (college && (qLower.includes('tell me about') || qLower.includes('about') || qLower.includes('overview') || qLower.includes('details') || qLower.includes('who is') || qLower.includes('profile'))) {
      return formatCollegeProfileOffline(college);
    }

    // 11. D2D Lateral Entry
    if (/\b(d2d|diploma to degree|lateral entry|polytechnic to degree)\b/.test(qLower)) {
      return k.d2d || "Information on D2D lateral entry in Gujarat.";
    }

    // 12. Paramedical / Physiotherapy / Nursing
    if (/\b(paramedical|physiotherapy|bpt|nursings?|b\.sc nursing|gnm)\b/.test(qLower)) {
      return k.paramedical || "Information on Physiotherapy and Paramedical in Gujarat.";
    }

    // 13. Medical / MBBS / BDS / ACPUGMEC
    if (/\b(acpugmec|medadmgujarat|mbbs|bds|bams|bhms|ayush|medical colleges?|doctor.*after 12)\b/.test(qLower)) {
      if (qLower.includes('list') || qLower.includes('top')) {
        return k.top_medical || "List of Medical colleges in Gujarat.";
      }
      return k.acpugmec || "Medical admission procedure through ACPUGMEC in Gujarat.";
    }

    // 14. Agriculture & Veterinary
    if (/\b(gsauca|agriculture|agricultural|kamdhenu|veterinary|b\.v\.sc|dairy)\b/.test(qLower)) {
      return k.agriculture || "Agriculture and Veterinary admissions in Gujarat.";
    }

    // 15. Entrance Exams
    if (/\b(entrance exams?|which entrance exam|exams?.*after 12)\b/.test(qLower)) {
      return k.entrance_exams || "Key entrance exams for Gujarat 12th science students.";
    }

    // 16. Groups: AB, A, B
    if (/\b(group ab|group-ab|group a&b|pcmb)\b/.test(qLower)) {
      return k.group_ab || "Group AB options in Gujarat.";
    }
    if (/\b(group a|group-a|pcm\b|maths.*science)\b/.test(qLower)) {
      return k.group_a || "Group A options in Gujarat.";
    }
    if (/\b(group b|group-b|pcb\b|biology.*science)\b/.test(qLower)) {
      return k.group_b || "Group B options in Gujarat.";
    }

    // 17. Best Engineering Branches
    if (/\bbran?ch(?:es)?\b/.test(qLower) && /\b(best|good|scope|top|which|choose|recommend)\b/.test(qLower)) {
      return k.best_branches || "Branch recommendation for Gujarat.";
    }

    // 18. GUJCET Pattern & Syllabus
    if (/\b(gujcet syllabus|gujcet pattern|marking scheme|exam pattern)\b/.test(qLower)) {
      return k.gujcet || "GUJCET pattern & syllabus.";
    }

    // 19. ACPC Admissions
    if (qLower.includes('acpc') || (qLower.includes('admission') && qLower.includes('process'))) {
      return k.acpc || "ACPC engineering counseling procedure.";
    }

    // 20. Fallback College Profile if college matched
    if (college) {
      return formatCollegeProfileOffline(college);
    }

    // 21. Overview
    if (/\b(after 12|courses? after 12|options? after 12|what after 12|science field)\b/.test(qLower)) {
      return k.overview || "12th Science higher education overview.";
    }

    return `### Gujarat Higher Education Guidance (12th Science)

I could not find a specific match for: **"${query}"**.

Here are some topics you can ask me about:
- **Science Pathways:** Group A (PCM), Group B (PCB), or Group AB (PCMB)
- **Centralized Admissions:** ACPC (Engineering/Pharmacy/D2D), ACPUGMEC (MBBS/BDS), GSAUCA (Agri)
- **Financial Aid:** MYSY Scholarship (up to ₹2 Lakh for MBBS, ₹50k for Engg), Kanya Kelavani (100% Free for girls in Govt colleges)
- **City Directory:** Private universities in Ahmedabad for B.Tech, Govt colleges in Surat/Vadodara
- **Colleges:** DA-IICT, BJMC, LDCE, Nirma, IITGN, SVNIT, VGEC, PDEU, Adani, LJ`;
  }

  function findCollegeOffline(qLower, insts) {
    const genericBlocks = [
      "government engineering", "govt engineering", "private university", "private universities",
      "medical college", "medical colleges", "pharmacy college", "pharmacy colleges",
      "top engineering", "top medical", "best engineering", "best medical", "best branch",
      "colleges in", "universities in", "colleges for", "universities for"
    ];
    if (genericBlocks.some(gb => qLower.includes(gb)) && !['bjmc', 'ldce', 'vgec', 'daiict', 'da-iict', 'nirma', 'pdeu', 'svnit', 'iitgn', 'bvm', 'msu', 'cept', 'ddu', 'parul', 'adani', 'silver oak', 'indus', 'lj'].some(k => qLower.includes(k))) {
      return null;
    }

    const aliasMap = {
      "iit gandhinagar": "iitgn", "iitgn": "iitgn",
      "svnit": "svnit", "svnit surat": "svnit",
      "da-iict": "daiict", "daiict": "daiict", "dhirubhai ambani": "daiict", "dau": "daiict",
      "nirma": "nirma", "nirma university": "nirma",
      "pdeu": "pdeu", "pdpu": "pdeu", "pandit deendayal": "pdeu",
      "ldce": "ldce", "ld college": "ldce", "l.d. college": "ldce",
      "vgec": "vgec", "vishwakarma": "vgec",
      "bvm": "bvm", "birla vishvakarma": "bvm",
      "msu": "msu", "msu baroda": "msu",
      "cept": "cept", "cept university": "cept",
      "ddu": "ddu", "dharmsinh desai": "ddu",
      "parul": "parul", "parul university": "parul",
      "bjmc": "bjmc", "b.j. medical": "bjmc", "bj medical": "bjmc",
      "gmc baroda": "gmc_baroda", "gmc surat": "gmc_surat", "gmc rajkot": "gmc_rajkot",
      "gmers sola": "gmers_sola", "nhl medical": "nhl_medical",
      "lmcp": "lmcp", "lm college of pharmacy": "lmcp",
      "aau": "aau", "kamdhenu": "kamdhenu", "gtu": "gtu", "gbu": "gbu",
      "lj": "lj_university", "lj university": "lj_university",
      "adani": "adani_university", "adani university": "adani_university",
      "silver oak": "silver_oak_u", "indus": "indus_univer"
    };

    for (const [phrase, cid] of Object.entries(aliasMap)) {
      const regex = new RegExp(`\\b${phrase}\\b`);
      if (regex.test(qLower)) {
        return insts.find(c => c.id === cid || (c.name && c.name.toLowerCase().includes(cid)));
      }
    }

    for (const c of insts) {
      const base = (c.name || '').toLowerCase().replace(/\(.*?\)/g, '').trim();
      if (base === "government engineering college" || base === "government medical college" || base === "private university") {
        continue;
      }
      if (base.length > 6 && qLower.includes(base)) {
        return c;
      }
    }
    return null;
  }

  function formatCollegeProfileOffline(c) {
    return `### ${c.name}

- **Location:** ${c.city || 'Gujarat'}
- **Institution Type:** ${c.type}
- **Category:** ${(c.category || 'Science & Technology').toUpperCase()}
- **NIRF / Recognition:** ${c.nirf_rank || 'Recognized Gujarat Institution'}
- **Annual Fees:** ${c.fees || 'Refer to ACPC portal.'}
- **Placement Stats:** Average ${c.avg_package || 'N/A'} | Highest ${c.highest_package || 'N/A'}
- **Entrance Exams Accepted:** ${(c.exams || []).join(', ') || 'GUJCET / ACPC'}

#### Overview & Highlights:
${c.overview || ''}`;
  }

  function parseAndFilterOffline(qLower, insts) {
    if (/\b(fees?|fee structure|costs?|tuitions?|cutoffs?|cut off|closing ranks?|syllabus|jee main)\b/.test(qLower)) {
      return null;
    }

    const cityMap = {
      "ahmedabad": ["ahmedabad", "ahemdabad", "ahmadabad", "amdavad"],
      "gandhinagar": ["gandhinagar", "gandhi nagar"],
      "vadodara": ["vadodara", "baroda"],
      "surat": ["surat"],
      "rajkot": ["rajkot"],
      "anand": ["anand", "vallabh vidyanagar", "vvn"]
    };

    let matchedCity = null;
    let matchedCityLabel = null;
    for (const [canonical, aliases] of Object.entries(cityMap)) {
      if (aliases.some(a => new RegExp(`\\b${a}\\b`).test(qLower))) {
        matchedCity = canonical;
        matchedCityLabel = canonical.charAt(0).toUpperCase() + canonical.slice(1);
        break;
      }
    }

    const isPvt = /\b(private|pvt|self[\s-]?financed|sfi)\b/.test(qLower);
    const isGov = /\b(government|govt|public|grant[\s-]?in[\s-]?aid|gmers)\b/.test(qLower);
    const onlyUniv = /\b(universit(?:y|ies)|deemed)\b/.test(qLower);

    let discipline = null;
    let discLabel = '';
    if (/\b(b\.?tech|b\.?e\.?|engineerings?|technolog(?:y|ical))\b/.test(qLower)) {
      discipline = 'engineering';
      discLabel = 'B.Tech / Engineering';
    } else if (/\b(medicals?|mbbs|bds|doctors?)\b/.test(qLower)) {
      discipline = 'medical';
      discLabel = 'Medical (MBBS/BDS)';
    } else if (/\b(pharmac(?:y|ies)|b\.?pharm)\b/.test(qLower)) {
      discipline = 'pharmacy';
      discLabel = 'Pharmacy (B.Pharm)';
    }

    const listingKeywords = ['give me', 'names of', 'name of', 'list of', 'list', 'show me', 'which colleges', 'colleges in', 'universities in', 'colleges of', 'universities of'];
    const hasIntent = listingKeywords.some(k => qLower.includes(k)) || 
                      (matchedCity && (discipline || isPvt || isGov || onlyUniv)) ||
                      (isPvt && (discipline || onlyUniv)) ||
                      (isGov && (discipline || onlyUniv));

    if (!hasIntent) return null;

    const filtered = insts.filter(c => {
      const cCity = (c.city || '').toLowerCase();
      const cName = (c.name || '').toLowerCase();
      const cType = (c.type || '').toLowerCase();
      const cCat = (c.category || '').toLowerCase();
      const cDiscs = (c.disciplines || []).map(d => d.toLowerCase());
      const cIsGov = !!c.is_government;

      if (matchedCity && (!cCity.includes(matchedCity) && !cName.includes(matchedCity))) return false;
      if (isGov && !cIsGov) return false;
      if (isPvt && cIsGov) return false;
      if (onlyUniv && !cType.includes('university') && !cName.includes('university')) return false;

      if (discipline) {
        if (discipline === 'engineering' && cCat !== 'engineering' && !cDiscs.includes('engineering')) return false;
        if (discipline === 'medical' && cCat !== 'medical' && !cDiscs.includes('medical')) return false;
        if (discipline === 'pharmacy' && cCat !== 'pharmacy' && !cDiscs.includes('pharmacy')) return false;
      }
      return true;
    });

    if (filtered.length === 0) return null;

    const parts = [];
    if (isPvt) parts.push("Private");
    else if (isGov) parts.push("Government");

    if (onlyUniv) parts.push("Universities");
    else parts.push("Colleges & Universities");

    if (matchedCityLabel) parts.push(`in ${matchedCityLabel}`);
    else parts.push("in Gujarat");

    if (discLabel) parts.push(`for ${discLabel}`);

    let out = `### ${parts.join(' ')}\n\nHere are the **${filtered.length}** verified institutions matching your criteria in Gujarat:\n\n`;

    filtered.forEach((c, idx) => {
      out += `#### ${idx + 1}. ${c.name}\n`;
      out += `- **Location:** ${c.city}\n`;
      out += `- **Institution Type:** ${c.type}\n`;
      if (c.fees && c.fees !== 'N/A') out += `- **Annual Fees:** ${c.fees}\n`;
      if (c.avg_package && c.avg_package !== 'N/A') out += `- **Placements:** Average ${c.avg_package} | Highest ${c.highest_package || 'N/A'}\n`;
      if (c.exams && c.exams.length) out += `- **Entrance Exams:** ${c.exams.join(', ')}\n`;
      if (c.cutoffs) out += `- **Cutoff Trends:** ${c.cutoffs}\n`;
      if (c.overview) out += `- **Overview:** ${c.overview}\n`;
      out += '\n';
    });

    if (matchedCity === 'ahmedabad' && discipline === 'engineering') {
      out += `> [!NOTE]\n> **Gandhinagar / Twin-City Regional Options:** Located just adjacent to Ahmedabad along the SG Highway and Gandhinagar knowledge corridor are top premier universities including **DA-IICT (Dhirubhai Ambani University)** and **PDEU (Pandit Deendayal Energy University)**.`;
    }

    return out;
  }

  // ==============================================================================
  // MARKDOWN RENDERER
  // ==============================================================================

  function renderMarkdown(md) {
    if (!md) return '';

    let text = md.replace(/\r\n/g, '\n');
    text = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');

    text = text.replace(/&gt;\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n((?:&gt;.*?\n?)+)/gi, (match, type, content) => {
      const cleanContent = content.replace(/^&gt;\s?/gm, '').trim();
      return `<div class="callout-note"><div class="callout-title">ℹ️ ${type.toUpperCase()}</div><p>${cleanContent}</p></div>`;
    });

    const lines = text.split('\n');
    let inTable = false;
    let tableHtml = '';
    const processedLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith('|') && line.endsWith('|')) {
        const cells = line.split('|').slice(1, -1).map(c => c.trim());
        const isSeparator = cells.every(c => /^:?-+:?$/.test(c));

        if (!inTable) {
          inTable = true;
          tableHtml = '<div class="table-responsive"><table><thead><tr>';
          cells.forEach(c => {
            tableHtml += `<th>${formatInline(c)}</th>`;
          });
          tableHtml += '</tr></thead><tbody>';
        } else if (isSeparator) {
          continue;
        } else {
          tableHtml += '<tr>';
          cells.forEach(c => {
            tableHtml += `<td>${formatInline(c)}</td>`;
          });
          tableHtml += '</tr>';
        }
      } else {
        if (inTable) {
          inTable = false;
          tableHtml += '</tbody></table></div>';
          processedLines.push(tableHtml);
          tableHtml = '';
        }
        processedLines.push(lines[i]);
      }
    }
    if (inTable) {
      tableHtml += '</tbody></table></div>';
      processedLines.push(tableHtml);
    }

    text = processedLines.join('\n');

    text = text.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.*?)$/gm, '<h3>$1</h3>');
    text = text.replace(/^# (.*?)$/gm, '<h3>$1</h3>');

    text = text.replace(/^---$/gm, '<hr>');

    text = text.replace(/^(\s*)-\s+(.*?)$/gm, '<li>$2</li>');
    text = text.replace(/(<li>.*?<\/li>\n?)+/g, '<ul>$&</ul>');

    text = text.replace(/^(\s*)\d+\.\s+(.*?)$/gm, '<li>$2</li>');
    text = text.replace(/(?<!<ul>)(<li>.*?<\/li>\n?)+(?!<\/ul>)/g, '<ol>$&</ol>');

    text = formatInline(text);

    const blocks = text.split(/\n{2,}/);
    return blocks.map(block => {
      block = block.trim();
      if (!block) return '';
      if (/^<(h[1-6]|div|table|ul|ol|hr|li)/.test(block)) {
        return block;
      }
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');
  }

  function formatInline(str) {
    if (!str) return '';
    return str
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code style="font-family:var(--font-mono);background:var(--bg-chip);padding:2px 6px;border-radius:4px;font-size:12px;">$1</code>');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Initialize
  loadSessions();
  fetchSupabaseConfig();
});
