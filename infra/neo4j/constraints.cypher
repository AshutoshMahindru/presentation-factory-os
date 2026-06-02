// Presentation Factory OS v3.2.4 Neo4j 5 constraints and graph patterns

// Unique identifiers
CREATE CONSTRAINT claim_id_unique IF NOT EXISTS
FOR (c:Claim) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT source_id_unique IF NOT EXISTS
FOR (s:Source) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT slide_id_unique IF NOT EXISTS
FOR (sl:Slide) REQUIRE sl.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT pillar_id_unique IF NOT EXISTS
FOR (pl:Pillar) REQUIRE pl.id IS UNIQUE;

// Project and status indexes
CREATE INDEX claim_project_id_index IF NOT EXISTS
FOR (c:Claim) ON (c.project_id);

CREATE INDEX claim_status_index IF NOT EXISTS
FOR (c:Claim) ON (c.status);

CREATE INDEX claim_audience_relevance_index IF NOT EXISTS
FOR (c:Claim) ON (c.audience_relevance);

CREATE INDEX source_project_id_index IF NOT EXISTS
FOR (s:Source) ON (s.project_id);

CREATE INDEX source_status_index IF NOT EXISTS
FOR (s:Source) ON (s.status);

CREATE INDEX slide_project_id_index IF NOT EXISTS
FOR (sl:Slide) ON (sl.project_id);

CREATE INDEX slide_status_index IF NOT EXISTS
FOR (sl:Slide) ON (sl.status);

CREATE INDEX project_status_index IF NOT EXISTS
FOR (p:Project) ON (p.status);

CREATE INDEX pillar_project_id_index IF NOT EXISTS
FOR (pl:Pillar) ON (pl.project_id);

CREATE INDEX pillar_thesis_version_id_index IF NOT EXISTS
FOR (pl:Pillar) ON (pl.thesis_version_id);

CREATE INDEX claim_pillar_edge_index IF NOT EXISTS
FOR ()-[r:SUPPORTS_PILLAR]-() ON (r.pillar_id);

// Node structures
// (:Project {
//   id: string,
//   name: string,
//   status: 'active'|'blocked'|'exported'|'rejected',
//   current_phase: phase_name,
//   created_at: datetime
// })
//
// (:Source {
//   id: string,
//   project_id: string,
//   uri: string,
//   title: string,
//   version: string,
//   status: 'active'|'retracted'|'superseded'|'under_review',
//   classification: 'public'|'confidential'|'restricted'|'pii',
//   content_hash: string,
//   created_at: datetime,
//   updated_at: datetime
// })
//
// (:Claim {
//   id: string,
//   project_id: string,
//   text: string,
//   materiality: 'low'|'medium'|'high',
//   audience_relevance: 'core'|'supporting'|'neutral'|'misaligned',
//   status: 'supported'|'unsupported'|'retracted'|'under_review',
//   created_at: datetime
// })
//
// (:Slide {
//   id: string,
//   project_id: string,
//   slide_number: integer,
//   title: string,
//   status: 'draft'|'blocked'|'review_ready'|'approved'|'exported',
//   created_at: datetime
// })
//
// (:Pillar {
//   id: string,
//   project_id: string,
//   thesis_version_id: string,
//   pillar_index: integer,
//   statement: string,
//   pillar_type: 'claim'|'data'|'objection'|'narrative'|'financial',
//   created_at: datetime
// })

// Pattern: create_claim_enforced
// The application must MATCH Source before CREATE Claim.
// It must create the SUPPORTED_BY edge in the same write transaction.
//
// MATCH (p:Project {id: $project_id})
// MATCH (s:Source {id: $source_id, project_id: $project_id})
// WHERE s.status = 'active'
// CREATE (c:Claim {
//   id: $claim_id,
//   project_id: $project_id,
//   text: $claim_text,
//   materiality: $materiality,
//   audience_relevance: $audience_relevance,
//   status: 'supported',
//   created_at: datetime()
// })
// CREATE (c)-[:SUPPORTED_BY {
//   source_id: s.id,
//   evidence_span: $evidence_span,
//   confidence: $confidence,
//   created_at: datetime()
// }]->(s)
// CREATE (p)-[:HAS_CLAIM]->(c)
// RETURN c;

// Pattern: retract_source_cascade
// If a source is retracted, claims with fewer than two active supporting sources become unsupported.
// Affected slides and projects are blocked for revision.
//
// MATCH (s:Source {id: $source_id})
// SET s.status = 'retracted', s.retracted_at = datetime(), s.retraction_reason = $reason
// WITH s
// MATCH (c:Claim)-[r:SUPPORTED_BY]->(s)
// SET r.status = 'retracted'
// WITH c
// OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(active:Source {status: 'active'})
// WITH c, count(active) AS active_support_count
// WHERE active_support_count < 2
// SET c.status = 'unsupported'
// WITH c
// OPTIONAL MATCH (sl:Slide)-[:USES_CLAIM]->(c)
// SET sl.status = 'blocked', sl.blocked_reason = 'unsupported_claim_after_source_retraction'
// WITH collect(DISTINCT sl.project_id) AS affected_projects
// UNWIND affected_projects AS project_id
// MATCH (p:Project {id: project_id})
// SET p.status = 'blocked', p.blocked_reason = 'source_retraction_cascade'
// RETURN affected_projects;

// Pattern: assert_minimum_two_active_sources
// This should return zero rows before review and export.
//
// MATCH (c:Claim)
// OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:Source {status: 'active'})
// WITH c, count(s) AS active_support_count
// WHERE active_support_count < 2
// RETURN c.id AS under_supported_claim_id, c.project_id AS project_id, c.text AS text, active_support_count;

// Pattern: slide material claim trace
//
// MATCH (sl:Slide {id: $slide_id})-[:USES_CLAIM]->(c:Claim)-[:SUPPORTED_BY]->(s:Source)
// RETURN sl.id, c.id, c.text, s.id, s.title, s.uri, s.status;

// Business rule: minimum_two_active_sources. A claim with fewer than 2 active supporting sources is marked unsupported.


// Pattern: validate_claim_audience_relevance
// Claims tagged misaligned cannot advance past strategy. Core/supporting claims must match the project audience profile.
// The validator reads projects.audience_profile from Postgres and writes the computed audience_relevance tag when creating/updating a claim.
//
// MATCH (c:Claim {project_id: $project_id})
// WHERE c.audience_relevance = 'misaligned'
// RETURN c.id AS misaligned_claim_id, c.text AS text, c.audience_relevance AS audience_relevance;

// Business rule: audience_relevance must be core or supporting for material strategic claims.


// Pattern: retract_source_cascade_batch
// Executed by job-runner, not the synchronous API path.
// Processes max 50 claims per transaction to reduce lock contention and preserve the 30-second source-retraction SLA.
//
// MATCH (s:Source {id: $source_id, status: 'retracted'})
// MATCH (c:Claim)-[r:SUPPORTED_BY]->(s)
// WHERE c.status <> 'unsupported'
// SET r.status = 'retracted'
// WITH c LIMIT 50
// OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(active:Source {status: 'active'})
// WITH c, count(active) AS active_support_count
// WHERE active_support_count < 2
// SET c.status = 'unsupported', c.unsupported_at = datetime()
// RETURN count(c) AS processed_count;

// Pattern: retreat_archive_downstream
// When a project retreats from phase X to Y, mark all artifacts scoped to downstream phases as stale.
// Work is never deleted; stale artifacts are blocked from transition and export until revalidated.
//
// MATCH (p:Project {id: $project_id})
// SET p.current_phase = $new_phase
// WITH p
// MATCH (a:Artifact)-[:BELONGS_TO]->(p)
// WHERE a.phase_scope_order > $new_phase_order
// SET a.status = 'stale_due_to_retreat', a.staled_at = datetime()
// RETURN count(a) AS archived_count;

// Pattern: outbox_idempotent_apply
// Cross-store Neo4j writes are invoked only by the job-runner after reading Postgres outbox rows.
// Every operation must be idempotent and safe to retry up to outbox_max_retry.

// Pattern: upsert_pillar
// Step 107: project a Postgres thesis_pillar into Neo4j as a (:Pillar) node.
// Pillar is the thesis-aware anchor for evidence linkage.
// Idempotent: re-running for the same (project_id, thesis_version_id, pillar_index) updates statement/pillar_type.
// Application must MERGE Project first; the call assumes the Project node already exists.
//
MERGE (p:Project {id: $project_id})
ON CREATE SET p.created_at = datetime()
MERGE (pl:Pillar {id: $pillar_id})
ON CREATE SET pl.created_at = datetime()
SET pl.project_id = $project_id,
    pl.thesis_version_id = $thesis_version_id,
    pl.pillar_index = $pillar_index,
    pl.statement = $statement,
    pl.pillar_type = $pillar_type
WITH pl
MATCH (p:Project {id: $project_id})
MERGE (p)-[:HAS_PILLAR]->(pl)
RETURN pl.id AS pillar_id;

// Pattern: link_claim_to_pillar
// Step 107: explicit Claim → Pillar linkage. Edge carries a confidence score
// (set by the claim-generation agent out of band; the linker is read-only on this edge).
//
MATCH (c:Claim {id: $claim_id, project_id: $project_id})
MATCH (pl:Pillar {id: $pillar_id, project_id: $project_id})
MERGE (c)-[r:SUPPORTS_PILLAR {pillar_id: $pillar_id}]->(pl)
ON CREATE SET r.created_at = datetime(), r.confidence = $confidence
RETURN c.id AS claim_id, pl.id AS pillar_id;

// Pattern: list_sources_for_pillar
// Step 107: enumerate the active sources that ultimately back a Pillar.
// Traverses Pillar ←SUPPORTS_PILLAR- Claim -SUPPORTED_BY→ Source.
// Used by the deep_read step to write search_coverage back to source_register.
//
MATCH (pl:Pillar {id: $pillar_id, project_id: $project_id})
MATCH (pl)<-[sp:SUPPORTS_PILLAR]-(c:Claim)
MATCH (c)-[sb:SUPPORTED_BY]->(s:Source {status: 'active'})
RETURN DISTINCT s.id AS source_id
ORDER BY source_id;
