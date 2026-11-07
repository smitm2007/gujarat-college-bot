-- ==============================================================================
-- Supabase Database Schema for GujaratEdu Higher Education Advisory Bot
-- Stores: Complete chat history, user questions, bot responses, sessions, and timestamps
-- ==============================================================================

-- 1. Create the chat_history table
CREATE TABLE IF NOT EXISTS public.chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    session_title TEXT,
    role TEXT NOT NULL CHECK (role IN ('user', 'bot', 'system')),
    message_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    date_str TEXT
);

-- 2. Create performance indexes for fast query and sorting
CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON public.chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON public.chat_history(created_at DESC);

-- 3. DISABLE ROW LEVEL SECURITY (Recommended for frictionless public chatbot logging)
-- This ensures the anon key can insert and read chat history with ZERO permission blocks:
ALTER TABLE public.chat_history DISABLE ROW LEVEL SECURITY;

-- 4. OPTIONAL: If your organization requires Row Level Security (RLS) to be ENABLED,
-- run the lines below instead to grant full anon read/write:
/*
ALTER TABLE public.chat_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "chat_history_anon_all" ON public.chat_history;
CREATE POLICY "chat_history_anon_all" 
    ON public.chat_history FOR ALL 
    TO anon, authenticated 
    USING (true) 
    WITH CHECK (true);
*/

-- 5. Summary View: Sessions Grouping
CREATE OR REPLACE VIEW public.chat_sessions_summary AS
SELECT 
    session_id,
    session_title,
    MIN(created_at) AS session_start,
    MAX(created_at) AS last_activity,
    COUNT(*) AS total_messages
FROM public.chat_history
GROUP BY session_id, session_title
ORDER BY last_activity DESC;
