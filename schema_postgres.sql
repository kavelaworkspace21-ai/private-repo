CREATE TYPE userrole AS ENUM ('citizen', 'advocate', 'judge', 'firm_admin', 'business', 'associate', 'clerk');

CREATE TYPE casestatus AS ENUM ('open', 'in_progress', 'closed', 'archived');

CREATE TYPE hearingstatus AS ENUM ('scheduled', 'completed', 'adjourned', 'cancelled');

CREATE TYPE paymentmode AS ENUM ('cash', 'bank_transfer', 'cheque', 'upi', 'other');

CREATE TYPE feetype AS ENUM ('retainer', 'appearance', 'consultation', 'documentation', 'misc');

CREATE TYPE hearingstage AS ENUM ('first_hearing', 'arguments', 'final_arguments', 'judgment', 'other');

CREATE TYPE hearingoutcome AS ENUM ('pending', 'heard', 'adjourned', 'part_heard', 'decided');

CREATE TABLE tenants (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_tenants_id ON tenants (id);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity VARCHAR(80) NOT NULL, 
	entity_id INTEGER, 
	detail VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_id ON audit_logs (id);

CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);

CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	full_name VARCHAR(200) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	phone VARCHAR(50), 
	hashed_password VARCHAR(255) NOT NULL, 
	role userrole NOT NULL, 
	is_verified BOOLEAN NOT NULL, 
	totp_secret VARCHAR(64), 
	is_2fa_enabled BOOLEAN NOT NULL, 
	professional_id VARCHAR(100), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_users_tenant_id ON users (tenant_id);

CREATE INDEX ix_users_id ON users (id);

CREATE TABLE clients (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	phone VARCHAR(50), 
	address VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_clients_email ON clients (email);

CREATE INDEX ix_clients_tenant_id ON clients (tenant_id);

CREATE INDEX ix_clients_id ON clients (id);

CREATE TABLE generated_drafts (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	created_by INTEGER NOT NULL, 
	case_id INTEGER, 
	document_type VARCHAR(80) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	content TEXT NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	approved_by INTEGER, 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_generated_drafts_tenant_id ON generated_drafts (tenant_id);

CREATE INDEX ix_generated_drafts_case_id ON generated_drafts (case_id);

CREATE INDEX ix_generated_drafts_id ON generated_drafts (id);

CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	user_id INTEGER, 
	type VARCHAR(40) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	body VARCHAR(1000), 
	link VARCHAR(200), 
	dedupe_key VARCHAR(200), 
	is_read BOOLEAN NOT NULL, 
	emailed BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_notifications_id ON notifications (id);

CREATE INDEX ix_notifications_tenant_id ON notifications (tenant_id);

CREATE INDEX ix_notifications_dedupe_key ON notifications (dedupe_key);

CREATE INDEX ix_notifications_user_id ON notifications (user_id);

CREATE TABLE consent_records (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	user_id INTEGER NOT NULL, 
	consent_type VARCHAR(40) NOT NULL, 
	policy_version VARCHAR(20) NOT NULL, 
	granted BOOLEAN NOT NULL, 
	source_ip VARCHAR(64), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_consent_records_user_id ON consent_records (user_id);

CREATE INDEX ix_consent_records_id ON consent_records (id);

CREATE INDEX ix_consent_records_tenant_id ON consent_records (tenant_id);

CREATE TABLE backup_runs (
	id SERIAL NOT NULL, 
	engine VARCHAR(20) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	location VARCHAR(500), 
	size_bytes INTEGER NOT NULL, 
	trigger VARCHAR(20) NOT NULL, 
	detail VARCHAR(500), 
	started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_backup_runs_id ON backup_runs (id);

CREATE TABLE cases (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	description TEXT, 
	status casestatus NOT NULL, 
	client_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(client_id) REFERENCES clients (id)
);

CREATE INDEX ix_cases_tenant_id ON cases (tenant_id);

CREATE INDEX ix_cases_id ON cases (id);

CREATE TABLE conversations (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_conversations_user_id ON conversations (user_id);

CREATE INDEX ix_conversations_id ON conversations (id);

CREATE TABLE user_activities (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	action_type VARCHAR(60) NOT NULL, 
	entity_type VARCHAR(60), 
	entity_id INTEGER, 
	entity_label VARCHAR(300), 
	meta JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_user_activities_created_at ON user_activities (created_at);

CREATE INDEX ix_user_activities_action_type ON user_activities (action_type);

CREATE INDEX ix_user_activities_user_id ON user_activities (user_id);

CREATE INDEX ix_user_activities_id ON user_activities (id);

CREATE TABLE generated_draft_versions (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	draft_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	content TEXT NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(draft_id) REFERENCES generated_drafts (id)
);

CREATE INDEX ix_generated_draft_versions_id ON generated_draft_versions (id);

CREATE INDEX ix_generated_draft_versions_tenant_id ON generated_draft_versions (tenant_id);

CREATE INDEX ix_generated_draft_versions_draft_id ON generated_draft_versions (draft_id);

CREATE TABLE documents (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	filename VARCHAR(300) NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	notes TEXT, 
	case_id INTEGER NOT NULL, 
	uploaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_documents_id ON documents (id);

CREATE INDEX ix_documents_tenant_id ON documents (tenant_id);

CREATE TABLE hearings (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	hearing_date DATE NOT NULL, 
	court_name VARCHAR(300) NOT NULL, 
	judge_name VARCHAR(200), 
	status hearingstatus NOT NULL, 
	notes TEXT, 
	next_hearing_date DATE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_hearings_id ON hearings (id);

CREATE INDEX ix_hearings_tenant_id ON hearings (tenant_id);

CREATE TABLE fees_collected (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	payment_date DATE NOT NULL, 
	payment_mode paymentmode NOT NULL, 
	reference_number VARCHAR(200), 
	notes VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_fees_collected_id ON fees_collected (id);

CREATE INDEX ix_fees_collected_tenant_id ON fees_collected (tenant_id);

CREATE TABLE fees_due (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	fee_type feetype NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	due_date DATE NOT NULL, 
	is_paid BOOLEAN NOT NULL, 
	description VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_fees_due_tenant_id ON fees_due (tenant_id);

CREATE INDEX ix_fees_due_id ON fees_due (id);

CREATE TABLE diary_entries (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	hearing_date DATE NOT NULL, 
	hearing_time TIME WITHOUT TIME ZONE, 
	court_name VARCHAR(300) NOT NULL, 
	court_room VARCHAR(100), 
	stage hearingstage NOT NULL, 
	outcome hearingoutcome NOT NULL, 
	adjournment_reason VARCHAR(500), 
	next_date DATE, 
	order_notes TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_diary_entries_id ON diary_entries (id);

CREATE INDEX ix_diary_entries_tenant_id ON diary_entries (tenant_id);

CREATE TABLE diary_tasks (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	description TEXT, 
	due_date DATE, 
	is_completed BOOLEAN NOT NULL, 
	is_overdue BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_diary_tasks_tenant_id ON diary_tasks (tenant_id);

CREATE INDEX ix_diary_tasks_id ON diary_tasks (id);

CREATE TABLE filing_deadlines (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	deadline_date DATE NOT NULL, 
	is_filed BOOLEAN NOT NULL, 
	is_overdue BOOLEAN NOT NULL, 
	notes VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_filing_deadlines_tenant_id ON filing_deadlines (tenant_id);

CREATE INDEX ix_filing_deadlines_id ON filing_deadlines (id);

CREATE TABLE opposing_counsel (
	id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	case_id INTEGER NOT NULL, 
	advocate_name VARCHAR(200) NOT NULL, 
	bar_registration_number VARCHAR(100), 
	firm_name VARCHAR(200), 
	contact VARCHAR(100), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_opposing_counsel_tenant_id ON opposing_counsel (tenant_id);

CREATE INDEX ix_opposing_counsel_id ON opposing_counsel (id);

CREATE TABLE ai_messages (
	id SERIAL NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_messages_id ON ai_messages (id);

CREATE INDEX ix_ai_messages_conversation_id ON ai_messages (conversation_id);

CREATE TABLE document_versions (
	id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	original_filename VARCHAR(300) NOT NULL, 
	storage_path VARCHAR(500) NOT NULL, 
	content_type VARCHAR(120), 
	size_bytes INTEGER NOT NULL, 
	sha256 VARCHAR(64), 
	uploaded_by INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id)
);

CREATE INDEX ix_document_versions_tenant_id ON document_versions (tenant_id);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE INDEX ix_document_versions_id ON document_versions (id);
