export const PFOS_API_MEDIA_TYPE = "application/vnd.pfos.v3.2.4+json";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonObject = { [key: string]: JsonValue };

export type PfosPhase =
  | "created"
  | "intake"
  | "strategy"
  | "research"
  | "financial_model"
  | "narrative"
  | "visual_design"
  | "review"
  | "approved"
  | "exported"
  | "rejected";

export type PfosTransitionKind = "forward" | "retreat" | "reject";

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export interface StakeholderProfile {
  role: string;
  concern: string;
  influence_level?: string;
}

export interface AudienceProfilePayload {
  decision_maker_type: string;
  risk_tolerance: string;
  familiarity_with_topic: string;
  known_objections: string[];
  stakeholder_map: StakeholderProfile[];
}

export interface CreateProjectPayload {
  name: string;
  audience: string;
  audience_profile: AudienceProfilePayload;
  client_name?: string | null;
  decision_required?: string | null;
  objection_preemption_map?: JsonObject;
}

export interface CreateProjectResponse {
  project_id: string;
  phase: PfosPhase | string;
  audience_profile_valid: boolean;
}

export interface IntakeChatMessage {
  message_id?: string;
  project_id: string;
  turn_index: number;
  role: "user" | "assistant" | string;
  content: string;
  actor_email?: string | null;
  metadata: JsonObject;
  created_at?: string | null;
}

export interface IntakeChatTurnResponse {
  project_id: string;
  status: string;
  user_message: IntakeChatMessage;
  assistant_message: IntakeChatMessage | null;
  source_turn_count: number;
  proposal: JsonObject;
}

export interface IntakeChatMessagesResponse {
  project_id: string;
  message_count: number;
  messages: IntakeChatMessage[];
}

export interface ServiceProbeStatus {
  service: string;
  status: string;
}

export interface ProjectOutboxStatus {
  project_id: string;
  blocked: boolean;
  unprocessed_count: number;
  failed_count: number;
  oldest_unprocessed_age_seconds: number | null;
  pending_rows?: OutboxQueueRow[];
  failed_rows?: OutboxQueueRow[];
}

export interface SourceRetractionStatus {
  project_id: string;
  blocked: boolean;
  pending_count: number;
  processing_count: number;
  failed_count: number;
  oldest_open_age_seconds: number | null;
  pending_events?: SourceLifecycleEventStatus[];
  failed_events?: SourceLifecycleEventStatus[];
  blocked_events?: SourceLifecycleEventStatus[];
}

export interface OutboxQueueRow {
  outbox_id?: string;
  id?: string;
  project_id?: string;
  target_store?: string;
  operation_type?: string;
  error_count?: number;
  last_error?: string | null;
  created_at?: string | null;
}

export interface SourceLifecycleEventStatus {
  event_id?: string;
  id?: string;
  project_id?: string;
  source_id?: string;
  event_type?: string;
  processing_status?: string;
  error_count?: number;
  last_error?: string | null;
  created_at?: string | null;
}

export interface HardGateCheck {
  name: string;
  passed?: boolean;
  reason?: string | null;
  metadata?: JsonObject;
}

export interface HardGateStatus {
  project_id: string;
  name: string;
  passed: boolean;
  checks: HardGateCheck[];
  failed_checks: HardGateCheck[];
}

export interface ApprovalStatus {
  project_id: string;
  phase: PfosPhase | string;
  quorum_met: boolean;
  decision_rule: string;
  required_count: number;
  approved_count: number;
  rejected_count: number;
  abstained_count: number;
  changes_requested_count: number;
  missing_roles: Record<string, number>;
  blocking_rejection: boolean;
  escalation_status: string;
  escalation_reason: string | null;
}

export interface PhaseTransitionRequest {
  from_phase: PfosPhase;
  to_phase: PfosPhase;
  transition_kind: PfosTransitionKind;
  requested_by: string;
  reason?: string | null;
  guard_context?: JsonObject;
}

export interface PhaseTransitionGuardResult {
  name: string;
  status: "pass" | "fail" | string;
  reason: string | null;
}

export interface PhaseTransitionResponse {
  transition_id: string;
  project_id: string;
  from_phase: PfosPhase | string;
  to_phase: PfosPhase | string;
  status: "applied" | string;
  guards: PhaseTransitionGuardResult[];
}

export interface ProjectControlPlaneHealth {
  outbox: ProjectOutboxStatus;
  sourceRetractions: SourceRetractionStatus;
  hardGates: HardGateStatus;
}

export interface ApiErrorPayload {
  detail?: unknown;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

export interface PfosApiClient {
  createProject(payload: CreateProjectPayload): Promise<CreateProjectResponse>;
  appendIntakeChatMessage(
    projectId: string,
    payload: { content: string; actor_email?: string | null; metadata?: JsonObject },
  ): Promise<IntakeChatTurnResponse>;
  listIntakeChatMessages(
    projectId: string,
    options?: { limit?: number; afterTurnIndex?: number },
  ): Promise<IntakeChatMessagesResponse>;
  getServiceHealth(): Promise<ServiceProbeStatus>;
  getServiceReadiness(): Promise<ServiceProbeStatus>;
  getProjectOutboxStatus(projectId: string): Promise<ProjectOutboxStatus>;
  getProjectSourceRetractionStatus(projectId: string): Promise<SourceRetractionStatus>;
  getProjectHardGateStatus(projectId: string): Promise<HardGateStatus>;
  getProjectControlPlaneHealth(projectId: string): Promise<ProjectControlPlaneHealth>;
  getApprovalStatus(projectId: string, phase: PfosPhase | string): Promise<ApprovalStatus>;
  requestPhaseTransition(
    projectId: string,
    payload: PhaseTransitionRequest,
  ): Promise<PhaseTransitionResponse>;
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}

function buildUrl(baseUrl: string, path: string): string {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  return `${normalizedBaseUrl}${path}`;
}

function errorMessageForStatus(status: number, payload: unknown): string {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof (payload as ApiErrorPayload).detail === "object"
  ) {
    const detail = (payload as ApiErrorPayload).detail as Record<string, unknown> | null;
    if (detail && typeof detail.error === "string") {
      return `PFOS API request failed with ${status}: ${detail.error}`;
    }
  }

  return `PFOS API request failed with ${status}`;
}

async function parseResponsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function createPfosApiClient(options: ApiClientOptions = {}): PfosApiClient {
  const baseUrl = options.baseUrl ?? "";
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;

  if (!fetchImpl) {
    throw new Error("createPfosApiClient requires a fetch implementation");
  }

  async function request<TResponse>(
    path: string,
    init: RequestInit = {},
  ): Promise<TResponse> {
    const headers = new Headers(init.headers);
    headers.set("accept", PFOS_API_MEDIA_TYPE);

    if (init.body !== undefined && !headers.has("content-type")) {
      headers.set("content-type", PFOS_API_MEDIA_TYPE);
    }

    const response = await fetchImpl(buildUrl(baseUrl, path), {
      ...init,
      headers,
    });
    const payload = await parseResponsePayload(response);

    if (!response.ok) {
      throw new ApiClientError(
        errorMessageForStatus(response.status, payload),
        response.status,
        payload,
      );
    }

    return payload as TResponse;
  }

  return {
    createProject(payload: CreateProjectPayload): Promise<CreateProjectResponse> {
      return request<CreateProjectResponse>("/projects", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          client_name: payload.client_name ?? null,
          decision_required: payload.decision_required ?? null,
          objection_preemption_map: payload.objection_preemption_map ?? {},
        }),
      });
    },

    appendIntakeChatMessage(
      projectId: string,
      payload: { content: string; actor_email?: string | null; metadata?: JsonObject },
    ): Promise<IntakeChatTurnResponse> {
      return request<IntakeChatTurnResponse>(
        `/projects/${encodePathSegment(projectId)}/intake-chat/messages`,
        {
          method: "POST",
          body: JSON.stringify({
            content: payload.content,
            actor_email: payload.actor_email ?? null,
            metadata: payload.metadata ?? {},
          }),
        },
      );
    },

    listIntakeChatMessages(
      projectId: string,
      options: { limit?: number; afterTurnIndex?: number } = {},
    ): Promise<IntakeChatMessagesResponse> {
      const params = new URLSearchParams();
      if (options.limit !== undefined) {
        params.set("limit", String(options.limit));
      }
      if (options.afterTurnIndex !== undefined) {
        params.set("after_turn_index", String(options.afterTurnIndex));
      }
      const query = params.toString();
      return request<IntakeChatMessagesResponse>(
        `/projects/${encodePathSegment(projectId)}/intake-chat/messages${query ? `?${query}` : ""}`,
      );
    },

    getServiceHealth(): Promise<ServiceProbeStatus> {
      return request<ServiceProbeStatus>("/health");
    },

    getServiceReadiness(): Promise<ServiceProbeStatus> {
      return request<ServiceProbeStatus>("/ready");
    },

    getProjectOutboxStatus(projectId: string): Promise<ProjectOutboxStatus> {
      return request<ProjectOutboxStatus>(
        `/health/projects/${encodePathSegment(projectId)}/outbox`,
      );
    },

    getProjectSourceRetractionStatus(projectId: string): Promise<SourceRetractionStatus> {
      return request<SourceRetractionStatus>(
        `/health/projects/${encodePathSegment(projectId)}/source-retractions`,
      );
    },

    getProjectHardGateStatus(projectId: string): Promise<HardGateStatus> {
      return request<HardGateStatus>(
        `/health/projects/${encodePathSegment(projectId)}/hard-gates`,
      );
    },

    async getProjectControlPlaneHealth(projectId: string): Promise<ProjectControlPlaneHealth> {
      const encodedProjectId = encodePathSegment(projectId);
      const [outbox, sourceRetractions, hardGates] = await Promise.all([
        request<ProjectOutboxStatus>(`/health/projects/${encodedProjectId}/outbox`),
        request<SourceRetractionStatus>(
          `/health/projects/${encodedProjectId}/source-retractions`,
        ),
        request<HardGateStatus>(`/health/projects/${encodedProjectId}/hard-gates`),
      ]);

      return {
        outbox,
        sourceRetractions,
        hardGates,
      };
    },

    getApprovalStatus(projectId: string, phase: PfosPhase | string): Promise<ApprovalStatus> {
      return request<ApprovalStatus>(
        `/projects/${encodePathSegment(projectId)}/approvals/status/${encodePathSegment(phase)}`,
      );
    },

    requestPhaseTransition(
      projectId: string,
      payload: PhaseTransitionRequest,
    ): Promise<PhaseTransitionResponse> {
      return request<PhaseTransitionResponse>(
        `/projects/${encodePathSegment(projectId)}/phase-transitions`,
        {
          method: "POST",
          body: JSON.stringify({
            ...payload,
            reason: payload.reason ?? null,
            guard_context: payload.guard_context ?? {},
          }),
        },
      );
    },
  };
}
