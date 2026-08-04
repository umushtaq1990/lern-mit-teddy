-- Azure SQL schema for the Langfuse export pipeline.
-- Idempotent: safe to re-run against an existing database.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
CREATE TABLE users (
    user_id NVARCHAR(100) NOT NULL PRIMARY KEY,
    display_name NVARCHAR(200) NOT NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sessions')
CREATE TABLE sessions (
    session_id NVARCHAR(200) NOT NULL PRIMARY KEY,
    user_id NVARCHAR(100) NULL REFERENCES users(user_id),
    room NVARCHAR(200) NULL,
    language NVARCHAR(10) NULL,
    native_language NVARCHAR(10) NULL,
    started_at DATETIME2 NULL,
    ended_at DATETIME2 NULL,
    turn_count INT NULL,
    langfuse_trace_url NVARCHAR(500) NULL,
    blob_path NVARCHAR(500) NULL,
    exported_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'export_state')
CREATE TABLE export_state (
    job_name NVARCHAR(100) NOT NULL PRIMARY KEY,
    last_run_until DATETIME2 NULL
);

-- Quality/usage metrics, added after the initial schema.
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'llm_model')
    ALTER TABLE sessions ADD llm_model NVARCHAR(100) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'stt_model')
    ALTER TABLE sessions ADD stt_model NVARCHAR(100) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'tts_model')
    ALTER TABLE sessions ADD tts_model NVARCHAR(100) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'input_tokens')
    ALTER TABLE sessions ADD input_tokens INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'output_tokens')
    ALTER TABLE sessions ADD output_tokens INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'total_tokens')
    ALTER TABLE sessions ADD total_tokens INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'estimated_cost_usd')
    ALTER TABLE sessions ADD estimated_cost_usd DECIMAL(10, 6) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'duration_seconds')
    ALTER TABLE sessions ADD duration_seconds INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'feedback_rating')
    ALTER TABLE sessions ADD feedback_rating INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('sessions') AND name = 'feedback_comment')
    ALTER TABLE sessions ADD feedback_comment NVARCHAR(1000) NULL;
