-- Presentation Factory OS v3.2.4 PostgreSQL 16 schema
-- Required extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Phase enum synchronization requirement: this enum must match 08_StateMachine_Spec.yaml phases, generated code enums, API validators, and UI phase labels.
DO $$ BEGIN
  CREATE TYPE phase_name AS ENUM (
    'created',
    'intake',
    'strategy',
    'research',
    'financial_model',
    'narrative',
    'visual_design',
    'review',
    'approved',
    'exported',
    'rejected'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE approval_decision AS ENUM ('approved', 'rejected', 'changes_requested', 'abstained');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE lifecycle_event_type AS ENUM ('created', 'updated', 'retracted', 'classification_changed', 'superseded');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE routing_mode AS ENUM ('semantic', 'graph', 'structured', 'hybrid');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  client_name TEXT,
  audience TEXT NOT NULL,
  audience_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  decision_required TEXT,
  objection_preemption_map JSONB NOT NULL DEFAULT '{}'::jsonb,
  current_phase phase_name NOT NULL DEFAULT 'created',
  blocked BOOLEAN NOT NULL DEFAULT FALSE,
  blocked_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((blocked = FALSE AND blocked_reason IS NULL) OR (blocked = TRUE AND blocked_reason IS NOT NULL)),
  CHECK (jsonb_typeof(audience_profile) = 'object'),
  CHECK (jsonb_typeof(objection_preemption_map) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_projects_current_phase ON projects(current_phase);
CREATE INDEX IF NOT EXISTS idx_projects_blocked ON projects(blocked);
CREATE INDEX IF NOT EXISTS idx_projects_audience_profile_gin ON projects USING GIN (audience_profile);
CREATE INDEX IF NOT EXISTS idx_projects_objection_preemption_map_gin ON projects USING GIN (objection_preemption_map);

CREATE TABLE IF NOT EXISTS phase_transitions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  from_phase phase_name NOT NULL,
  to_phase phase_name NOT NULL,
  transition_kind TEXT NOT NULL CHECK (transition_kind IN ('forward', 'retreat', 'reject', 'initial')),
  guard_results JSONB NOT NULL DEFAULT '{}'::jsonb,
  hard_gate_results JSONB NOT NULL DEFAULT '{}'::jsonb,
  state_machine_version TEXT NOT NULL DEFAULT '3.2.4',
  reason TEXT,
  actor_email TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (from_phase <> to_phase OR transition_kind = 'initial')
);
-- Transition legality is loaded from 08_StateMachine_Spec.yaml and enforced by system/state_machine.py.
-- SQL constrains only basic phase identity and transition kind to avoid migration-heavy tuple drift.

CREATE INDEX IF NOT EXISTS idx_phase_transitions_project_created ON phase_transitions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase_transitions_to_phase ON phase_transitions(to_phase);

CREATE TABLE IF NOT EXISTS approval_ledger (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase phase_name NOT NULL,
  actor_email TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('analyst', 'partner', 'senior_partner', 'ic_member', 'admin')),
  decision approval_decision NOT NULL,
  rubric_score_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (phase IN ('intake', 'strategy', 'financial_model', 'review'))
);

CREATE INDEX IF NOT EXISTS idx_approval_project_phase ON approval_ledger(project_id, phase, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_actor ON approval_ledger(actor_email);
CREATE INDEX IF NOT EXISTS idx_approval_role_decision ON approval_ledger(role, decision);

CREATE TABLE IF NOT EXISTS rubric_scores (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase phase_name NOT NULL,
  dimension TEXT NOT NULL,
  score_version INTEGER NOT NULL DEFAULT 1 CHECK (score_version >= 1),
  score NUMERIC(4,2) NOT NULL CHECK (score >= 1.00 AND score <= 5.00),
  weight NUMERIC(5,4) NOT NULL CHECK (weight > 0 AND weight <= 1),
  evaluator_type TEXT NOT NULL CHECK (evaluator_type IN ('heuristic', 'llm_judge', 'deterministic', 'graph_query')),
  evaluator_model TEXT,
  blocking BOOLEAN NOT NULL DEFAULT FALSE,
  threshold NUMERIC(4,2) CHECK (threshold IS NULL OR (threshold >= 1.00 AND threshold <= 5.00)),
  trace_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, phase, dimension, score_version)
);

CREATE INDEX IF NOT EXISTS idx_rubric_project_phase ON rubric_scores(project_id, phase);
CREATE INDEX IF NOT EXISTS idx_rubric_blocking ON rubric_scores(project_id, blocking) WHERE blocking = TRUE;

CREATE TABLE IF NOT EXISTS financial_cells (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  scenario TEXT NOT NULL DEFAULT 'base',
  cell_ref TEXT NOT NULL,
  label TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT,
  formula TEXT NOT NULL,
  source_refs TEXT[] NOT NULL DEFAULT '{}',
  validation_status TEXT NOT NULL DEFAULT 'pending' CHECK (validation_status IN ('pending', 'validated', 'failed')),
  ingestion_source_type TEXT NOT NULL DEFAULT 'manual_entry' CHECK (ingestion_source_type IN ('excel_xlsx', 'csv', 'manual_entry', 'api')),
  parser_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  phase_scope_version INTEGER NOT NULL DEFAULT 1 CHECK (phase_scope_version >= 1),
  artifact_status TEXT NOT NULL DEFAULT 'active' CHECK (artifact_status IN ('active', 'stale_due_to_retreat', 'archived', 'blocked')),
  staled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, scenario, cell_ref),
  CHECK (length(trim(formula)) > 0),
  CHECK (array_length(source_refs, 1) IS NULL OR array_length(source_refs, 1) >= 0),
  CHECK (jsonb_typeof(parser_provenance) = 'object'),
  CHECK (ingestion_source_type <> 'excel_xlsx' OR (parser_provenance ? 'parser_name' AND parser_provenance ? 'parser_version')),
  CHECK ((artifact_status <> 'stale_due_to_retreat' AND staled_at IS NULL) OR (artifact_status = 'stale_due_to_retreat' AND staled_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_financial_cells_project_scenario ON financial_cells(project_id, scenario);
CREATE INDEX IF NOT EXISTS idx_financial_cells_validation ON financial_cells(validation_status);
CREATE INDEX IF NOT EXISTS idx_financial_cells_artifact_status ON financial_cells(project_id, artifact_status);
CREATE INDEX IF NOT EXISTS idx_financial_cells_parser ON financial_cells(ingestion_source_type);

CREATE TABLE IF NOT EXISTS thesis_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
  version_number INTEGER NOT NULL CHECK (version_number >= 1),
  thesis_statement TEXT NOT NULL,
  convergence_score NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, version_number)
);

CREATE TABLE IF NOT EXISTS thesis_pillars (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  thesis_version_id UUID NOT NULL REFERENCES thesis_versions(id) ON DELETE CASCADE,
  pillar_index INTEGER NOT NULL,
  pillar_type TEXT NOT NULL CHECK (pillar_type IN ('claim', 'data', 'objection', 'narrative', 'financial')),
  statement TEXT NOT NULL,
  stress_status TEXT NOT NULL DEFAULT 'stable' CHECK (stress_status IN ('stable', 'stressed')),
  UNIQUE(thesis_version_id, pillar_index)
);

CREATE TABLE IF NOT EXISTS research_loops (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  loop_number INTEGER NOT NULL CHECK (loop_number >= 1),
  convergence_delta NUMERIC,
  sources_discovered_count INTEGER NOT NULL DEFAULT 0 CHECK (sources_discovered_count >= 0),
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'converged', 'failed', 'force_stopped', 'max_loops_reached')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  UNIQUE(project_id, loop_number)
);

ALTER TABLE financial_cells
  ADD COLUMN IF NOT EXISTS thesis_pillar_id UUID REFERENCES thesis_pillars(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS promoted_from_spec UUID;

CREATE INDEX IF NOT EXISTS idx_thesis_versions_project ON thesis_versions(project_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_thesis_pillars_version ON thesis_pillars(thesis_version_id, pillar_index);
CREATE INDEX IF NOT EXISTS idx_research_loops_project ON research_loops(project_id, loop_number);
CREATE INDEX IF NOT EXISTS idx_financial_cells_pillar ON financial_cells(thesis_pillar_id);

CREATE TABLE IF NOT EXISTS design_tokens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  token_namespace TEXT NOT NULL,
  token_name TEXT NOT NULL,
  token_value JSONB NOT NULL,
  schema_id TEXT NOT NULL DEFAULT 'https://presentation-factory-os.local/schemas/DesignTokens.schema.json',
  phase_scope_version INTEGER NOT NULL DEFAULT 1 CHECK (phase_scope_version >= 1),
  artifact_status TEXT NOT NULL DEFAULT 'active' CHECK (artifact_status IN ('active', 'stale_due_to_retreat', 'archived', 'blocked')),
  staled_at TIMESTAMPTZ,
  source TEXT NOT NULL CHECK (source IN ('system_default', 'brand_guideline', 'human_override', 'generated')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, token_namespace, token_name),
  CHECK (jsonb_typeof(token_value) = 'object'),
  CHECK ((artifact_status <> 'stale_due_to_retreat' AND staled_at IS NULL) OR (artifact_status = 'stale_due_to_retreat' AND staled_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_design_tokens_project_namespace ON design_tokens(project_id, token_namespace);
CREATE INDEX IF NOT EXISTS idx_design_tokens_artifact_status ON design_tokens(project_id, artifact_status);

CREATE TABLE IF NOT EXISTS provenance (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  model_name TEXT,
  prompt_hash TEXT,
  content_hash TEXT,
  input_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  output_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  actor TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (length(trim(entity_type)) > 0),
  CHECK (length(trim(entity_id)) > 0),
  CHECK (length(trim(action)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_provenance_project_entity ON provenance(project_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_provenance_created ON provenance(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_provenance_hashes ON provenance(prompt_hash, content_hash);

CREATE TABLE IF NOT EXISTS phase_traces (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase phase_name NOT NULL,
  trace_id UUID NOT NULL DEFAULT uuid_generate_v4(),
  span_name TEXT NOT NULL,
  service_name TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ,
  duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed', 'blocked')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_phase_traces_project_phase ON phase_traces(project_id, phase, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase_traces_trace_id ON phase_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_phase_traces_status ON phase_traces(status);

CREATE TABLE IF NOT EXISTS source_lifecycle_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL,
  event_type lifecycle_event_type NOT NULL,
  source_version TEXT,
  classification TEXT,
  event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  hmac_validated BOOLEAN NOT NULL DEFAULT FALSE,
  provenance_id UUID REFERENCES provenance(id),
  processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'processed', 'failed', 'blocked')),
  batch_cursor TEXT,
  batch_size INTEGER NOT NULL DEFAULT 50 CHECK (batch_size > 0 AND batch_size <= 50),
  error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count <= 5),
  last_error TEXT,
  processed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (length(trim(source_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_source_lifecycle_source ON source_lifecycle_events(source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_event_type ON source_lifecycle_events(event_type);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_project ON source_lifecycle_events(project_id);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_processing ON source_lifecycle_events(processing_status, event_type, created_at) WHERE processing_status IN ('pending', 'processing', 'failed');


CREATE TABLE IF NOT EXISTS outbox (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  target_store TEXT NOT NULL CHECK (target_store IN ('neo4j')),
  operation_type TEXT NOT NULL CHECK (operation_type IN ('source_retracted', 'claim_updated', 'phase_transition_side_effect', 'retreat_archive_downstream')),
  payload JSONB NOT NULL,
  processed BOOLEAN NOT NULL DEFAULT FALSE,
  error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count <= 5),
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  CHECK (jsonb_typeof(payload) = 'object'),
  CHECK ((processed = FALSE AND processed_at IS NULL) OR (processed = TRUE AND processed_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_outbox_project_created ON outbox(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_unprocessed ON outbox(processed, error_count, created_at) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_outbox_failed ON outbox(project_id, error_count) WHERE processed = FALSE AND error_count > 0;

CREATE TABLE IF NOT EXISTS retrieval_routing_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  request_id UUID NOT NULL,
  query TEXT NOT NULL,
  query_classification TEXT NOT NULL CHECK (query_classification IN ('financial', 'strategic', 'narrative', 'visual', 'unknown')),
  mode routing_mode NOT NULL,
  forced_hybrid BOOLEAN NOT NULL DEFAULT FALSE,
  escalation_reason TEXT,
  confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  item_count INTEGER NOT NULL CHECK (item_count >= 0),
  gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_routing_project ON retrieval_routing_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retrieval_routing_request ON retrieval_routing_log(request_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_routing_class_mode ON retrieval_routing_log(query_classification, mode);
CREATE INDEX IF NOT EXISTS idx_retrieval_routing_low_conf ON retrieval_routing_log(confidence) WHERE confidence < 0.50;

CREATE INDEX IF NOT EXISTS idx_rubric_scores_latest ON rubric_scores(project_id, phase, dimension, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_design_tokens_schema_id ON design_tokens(schema_id);
