/** Typed client for the Flask /api/* JSON endpoints. */

export interface User {
  id: number;
  name: string;
  role: "teacher" | "admin" | "student";
}

export interface LoginChoice extends User {
  login: string;
}

export interface HomeLink {
  href: string;
  label: string;
  blurb: string;
}

export interface StudentAssignment {
  id: number;
  lesson: string;
  status: string;
  attempts: number;
  latest_attempt_id: number | null;
}

export type HomePayload =
  | { user: User; links: HomeLink[]; assignments?: undefined }
  | { user: User; assignments: StudentAssignment[]; links?: undefined };

export interface ReviewRow {
  id: number;
  title: string;
  version_no: number;
  status: string;
  rationale: string;
  decision: string;
  low_impact: boolean;
}

export interface ReviewQueues {
  asset: ReviewRow[];
  stage: ReviewRow[];
  lesson: ReviewRow[];
}

export interface LessonRow {
  id: number;
  title: string;
  subject: string;
  classroom: string;
  drafts: number;
  published: number;
}

export interface DiffRow {
  field: string;
  old: string;
  new: string;
  changed: boolean;
}

export interface SnapshotDirective {
  id: number;
  focus: string;
}

export interface LessonDirectiveRow {
  id: number;
  kind: string;
  focus: string;
  active: boolean;
  covered: boolean;
}

export interface GenerationRun {
  id: number;
  agent: string;
  model: string;
  status: string;
}

export interface DossierCoverage {
  snapshot_present: boolean;
  snapshot_directives: SnapshotDirective[];
  brief: string;
  lesson_directives: LessonDirectiveRow[];
  generation_run: GenerationRun | null;
}

export interface ReuseMatch {
  title: string;
  version_no: number;
  id: number;
  mastery: string;
}

export interface ImpactRow {
  version_no: number;
  window: string;
  mastery: string;
  completion: string;
  enjoyment: string;
  sample_size: number;
  formula: string;
  cohort: string;
  uncertainty: string;
  low: boolean;
}

export interface UsageRow {
  consumer: string;
  kind: string;
  link_kind: string;
  version_id: number;
  version_no: number;
  status: string;
  role: string;
}

export interface PreviewRow {
  kind: string;
  storage_ref: string;
  rendered_at: string;
}

export interface AssetUseRow {
  asset: string;
  kind: string;
  asset_version_id: number;
  version_no: number;
  status: string;
  role: string;
  mastery: string;
  param_overrides: Record<string, unknown>;
}

export interface EditUseInput {
  asset_version_id: number;
  role: string;
  param_overrides?: Record<string, unknown>;
}

export interface EditPinInput {
  stage_version_id: number;
  required: boolean;
}

export interface CompositionRow {
  position: number;
  stage: string;
  version_no: number;
  stage_version_id: number;
  status: string;
  required: boolean;
  uses: number;
}

export interface DossierGoal {
  key: string;
  evaluation: string;
  template_ref: string;
  rule: Record<string, unknown>;
  rubric: Record<string, unknown> | null;
  models: string[];
  probes: string[];
}

export interface DossierChallengeGoals {
  challenge: string;
  challenge_version_id: number;
  version_no: number;
  goals: DossierGoal[];
}

export interface DossierLessonContext {
  lesson: string;
  lesson_version_id: number;
  version_no: number;
  status: string;
  scope: string;
  position: number;
  required: boolean;
  models: string[];
  composition: CompositionRow[];
}

export interface ApprovalEntry {
  actor: string;
  decision: string;
  rationale: string;
  at: string;
}

export interface PublishEventEntry {
  action: string;
  actor: string;
  rationale: string;
  at: string;
}

export interface Dossier {
  kind: string;
  id: number;
  title: string;
  version_no: number;
  status: string;
  rationale: string;
  prior_version_no: number | null;
  diff: DiffRow[];
  coverage: DossierCoverage;
  decision: string;
  audit: { approvals: ApprovalEntry[]; events: PublishEventEntry[] };
  reuse: ReuseMatch[];
  impact: ImpactRow[];
  usage: UsageRow[];
  previews: PreviewRow[];
  low_impact: boolean;
  uses: AssetUseRow[];
  composition: CompositionRow[];
  goals: DossierChallengeGoals[];
  lessons: DossierLessonContext[];
  content_ref?: string;
}

export interface ActionResult {
  message: string;
  dossier: Dossier;
  version_id?: number;
}

export interface BriefDirectiveRow {
  id: number;
  kind: string;
  scope: string;
  focus: string;
  priority: number;
  active: boolean;
}

export interface BriefRosterEntry {
  id: number;
  name: string;
}

export interface BriefContext {
  id: number;
  title: string;
  subject: string;
  classroom: string;
  directives: BriefDirectiveRow[];
  roster: BriefRosterEntry[];
}

export interface BriefPayload {
  focus: string;
  objectives: string;
  mental_models: string;
  must_include: string;
  must_avoid: string;
  priority: string;
  student_id: string;
}

/** Directives panel context (same shape as the brief context). */
export type DirectivesPanel = BriefContext;

export interface DirectivePayload {
  focus: string;
  must_include: string;
  must_avoid: string;
  priority: string;
  student_id: string;
}

export interface DirectivesResult {
  message: string;
  directive_id?: number;
  panel: DirectivesPanel;
}

export interface DirectiveDetail {
  id: number;
  lesson_id: number;
  kind: string;
  scope: string;
  focus: string;
  must_include: string;
  must_avoid: string;
  priority: number;
  active: boolean;
}

export interface DirectiveEditPayload {
  focus: string;
  must_include: string;
  must_avoid: string;
  priority: string;
}

export interface DirectiveEditResult {
  message: string;
  directive: DirectiveDetail;
}

export interface AssignmentRow {
  id: number;
  lesson: string;
  target: string;
  by: string;
  attempts: number;
}

export interface AssignmentLessonOption {
  id: number;
  title: string;
  classroom: string;
}

export interface AssignmentTargetOption {
  id: number;
  name: string;
}

export interface AssignmentOptions {
  lessons: AssignmentLessonOption[];
  classrooms: AssignmentTargetOption[];
  students: AssignmentTargetOption[];
}

export interface AssignmentsPayload {
  assignments: AssignmentRow[];
  options: AssignmentOptions;
}

export interface AssignPayload {
  lesson_id: string;
  classroom_id: string;
  student_id: string;
}

export interface AssignmentsResult {
  message: string;
  assignment_id: number;
  assignments: AssignmentRow[];
  options: AssignmentOptions;
}

export interface ProgressVerdict {
  event_id: number;
  goal: string;
  passed: boolean | null;
  score: number | null;
  overridden: boolean;
  override_reason: string;
  source: "deterministic" | "teacher";
  rationale: string;
}

export interface ProgressFlag {
  id: number;
  ref: string;
  note: string;
  at: string;
}

export interface ProgressAttempt {
  id: number;
  started: string;
  finished: string | null;
  retry_of: number | null;
  verdicts: ProgressVerdict[];
  flags: ProgressFlag[];
}

export interface ProgressStudent {
  id: number;
  name: string;
  rating: number | null;
  attempts: ProgressAttempt[];
}

export interface MisconceptionOption {
  id: number;
  label: string;
}

export interface AssignmentProgress {
  id: number;
  lesson: string;
  target: string;
  students: ProgressStudent[];
  misconceptions: MisconceptionOption[];
}

export interface AssignmentProgressResult {
  message: string;
  progress: AssignmentProgress;
}

export interface OverridePayload {
  reason: string;
  corrected: string;
  score: string;
}

export interface FlagPayload {
  misconception_id: string;
  note: string;
}

export interface BriefingStageVersion {
  stage_version_id: number;
  title: string;
}

export interface Briefing {
  assignment_id: number;
  lesson: string;
  published: boolean;
  objectives?: string[];
  models?: string[];
  stages?: string[];
  stage_versions?: BriefingStageVersion[];
  open_attempt_id?: number | null;
}

export interface PlayStartResult {
  message: string;
  attempt_id: number;
  next: string;
}

export interface ChallengeGoal {
  key: string;
  answered: boolean;
}

export interface ChallengeGuide {
  name: string;
  role: string;
}

export interface Challenge {
  attempt_id: number;
  assignment_id: number;
  index: number;
  total: number;
  stage_version_id: number;
  stage: string;
  title: string;
  challenge_version_id: number;
  goals: ChallengeGoal[];
  guides: ChallengeGuide[];
  finished: boolean;
  preview: boolean;
}

export interface ChallengeAnswerPayload {
  goals: string[];
  note: string;
}

export interface ChallengeAnswerResult {
  message: string;
  next: string;
}

export interface DebriefVerdict {
  event_id: number;
  goal: string;
  passed: boolean | null;
  score: number | null;
  overridden: boolean;
  override_reason: string;
  source: "deterministic" | "teacher";
  rationale: string;
}

export interface GradingEvaluation {
  event_id: number;
  passed: boolean | null;
  rationale: string;
  by: string;
  at: string;
}

export interface GradingGoal {
  goal_id: number;
  key: string;
  challenge_version_id: number;
  challenge: string;
  rubric: Record<string, unknown>;
  evaluation: GradingEvaluation | null;
}

export interface GradingEvidence {
  id: number;
  sequence_no: number;
  verb: string;
  object_ref: string;
  goal: string | null;
  note: string;
  at: string;
}

export interface Grading {
  attempt_id: number;
  assignment_id: number;
  lesson: string;
  student: string;
  finished: boolean;
  goals: GradingGoal[];
  evidence: GradingEvidence[];
}

export interface GradePayload {
  goal_id: number;
  passed: boolean;
  rationale: string;
}

export interface GradeResult {
  message: string;
  event_id: number;
}

export interface NextStep {
  kind: "continue" | "retry_goal" | "advance";
  goal: string | null;
  text: string;
}

export interface Debrief {
  attempt_id: number;
  assignment_id: number;
  lesson: string;
  finished: boolean;
  verdicts: DebriefVerdict[];
  next_steps: NextStep[];
  rating: number | null;
  preview: boolean;
}

export interface DebriefResult {
  message: string;
  debrief: Debrief;
}

export interface RetryResult {
  message: string;
  attempt_id: number;
  next: string;
}

export interface AuditLessonStatus {
  id: number;
  title: string;
  subject: string;
  drafts: number;
  published: number;
  retired: number;
  assignments: number;
  attempts: number;
}

export interface AuditRoomStatus {
  name: string;
  lessons: AuditLessonStatus[];
}

export interface AuditTrailRow {
  at_text: string;
  actor_id: number;
  actor: string;
  kind: string;
  result: string;
  target: string;
  rationale: string;
}

export interface AuditActor {
  id: number;
  name: string;
  role: string;
}

export interface AuditFilters {
  actor: number | null;
  since: string | null;
  until: string | null;
}

export interface AuditPayload {
  status: AuditRoomStatus[];
  trail: AuditTrailRow[];
  actors: AuditActor[];
  filters: AuditFilters;
}

export interface AuditQuery {
  actor?: string;
  since?: string;
  until?: string;
}

/** Challenge telemetry event per the experience_event contract. */
export interface PlayEventInput {
  client_event_id: string;
  verb: string;
  object_type?: string;
  object_ref?: string;
  payload?: Record<string, unknown>;
}

export interface PlayEventResult {
  message: string;
  event_id: number;
  duplicate: boolean;
}

export interface CheckpointInput {
  stage_version_id: number;
  state: Record<string, unknown>;
}

export interface Checkpoint {
  id: number;
  stage_version_id: number;
  checkpoint_sequence: number;
  state: Record<string, unknown>;
  preview: boolean;
}

export interface CheckpointResult {
  message: string;
  checkpoint_id: number;
  checkpoint_sequence: number;
}

export interface LaunchInput {
  stage_version_id: number;
  capabilities?: string[];
  device_id?: number;
}

export interface LaunchDecision {
  route: "immersive" | "web";
  reason: string;
  missing_required: string[];
  missing_preferred: string[];
  stage_version_id: number;
  device_id: number | null;
  event_id: number;
  message: string;
}

export interface LaunchRecord {
  event_id: number;
  sequence_no: number;
  stage_version_id: number;
  device_id: number | null;
  route: string;
  reason: string;
  missing_required: string[];
  missing_preferred: string[];
}

const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
  };
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data.error ?? `Request failed (${res.status})`,
    );
  }
  return data as T;
}

export const api = {
  session: () => apiFetch<{ user: User | null }>("/api/session"),
  loginChoices: () =>
    apiFetch<{ users: LoginChoice[] }>("/api/login_choices"),
  login: (login_ref: string) =>
    apiFetch<{ user: User; message: string }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ login_ref }),
    }),
  logout: () =>
    apiFetch<{ ok: true; message: string }>("/api/logout", {
      method: "POST",
    }),
  testReset: () =>
    apiFetch<{ ok: true }>("/api/__test__/reset", {
      method: "POST",
    }),
  home: () => apiFetch<HomePayload>("/api/home"),
  lessons: () => apiFetch<{ lessons: LessonRow[] }>("/api/lessons"),
  review: () => apiFetch<{ queues: ReviewQueues }>("/api/review"),
  dossier: (kind: string, versionId: number) =>
    apiFetch<{ dossier: Dossier }>(`/api/review/${kind}/${versionId}`),
  approve: (kind: string, versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  reject: (kind: string, versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/reject`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  editDraft: (
    kind: string,
    versionId: number,
    payload: {
      rationale: string;
      content_ref?: string;
      uses?: EditUseInput[];
      pins?: EditPinInput[];
    },
  ) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/edit`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  publish: (kind: string, versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/publish`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  rollback: (kind: string, versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/rollback`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  retire: (kind: string, versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/${kind}/${versionId}/retire`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  revise: (versionId: number, rationale: string) =>
    apiFetch<ActionResult>(`/api/review/asset/${versionId}/revise`, {
      method: "POST",
      body: JSON.stringify({ rationale }),
    }),
  brief: (lessonId: number) =>
    apiFetch<{ brief: BriefContext }>(`/api/lessons/${lessonId}/brief`),
  submitBrief: (lessonId: number, payload: BriefPayload) =>
    apiFetch<ActionResult>(`/api/lessons/${lessonId}/brief`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  directivesPanel: (lessonId: number) =>
    apiFetch<{ panel: DirectivesPanel }>(
      `/api/lessons/${lessonId}/directives`,
    ),
  createDirective: (lessonId: number, payload: DirectivePayload) =>
    apiFetch<DirectivesResult>(`/api/lessons/${lessonId}/directives`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deactivateDirective: (directiveId: number) =>
    apiFetch<DirectivesResult>(
      `/api/directives/${directiveId}/deactivate`,
      { method: "POST" },
    ),
  directive: (directiveId: number) =>
    apiFetch<{ directive: DirectiveDetail }>(
      `/api/directives/${directiveId}`,
    ),
  updateDirective: (
    directiveId: number,
    payload: DirectiveEditPayload,
  ) =>
    apiFetch<DirectiveEditResult>(
      `/api/directives/${directiveId}/edit`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  assignments: () => apiFetch<AssignmentsPayload>("/api/assignments"),
  assign: (payload: AssignPayload) =>
    apiFetch<AssignmentsResult>("/api/assignments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  assignmentProgress: (assignmentId: number) =>
    apiFetch<{ progress: AssignmentProgress }>(
      `/api/assignments/${assignmentId}`,
    ),
  overrideVerdict: (eventId: number, payload: OverridePayload) =>
    apiFetch<AssignmentProgressResult>(
      `/api/verdicts/${eventId}/override`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  flagAttempt: (attemptId: number, payload: FlagPayload) =>
    apiFetch<AssignmentProgressResult>(`/api/attempts/${attemptId}/flag`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  grading: (attemptId: number) =>
    apiFetch<{ grading: Grading }>(`/api/attempts/${attemptId}/grading`),
  gradeGoal: (attemptId: number, payload: GradePayload) =>
    apiFetch<GradeResult>(
      `/api/attempts/${attemptId}/teacher-evaluations`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  briefing: (assignmentId: number) =>
    apiFetch<{ briefing: Briefing }>(`/api/play/${assignmentId}`),
  startAttempt: (assignmentId: number) =>
    apiFetch<PlayStartResult>(`/api/play/${assignmentId}/start`, {
      method: "POST",
    }),
  challenge: (attemptId: number, index: number) =>
    apiFetch<{ challenge: Challenge }>(
      `/api/play/attempt/${attemptId}/challenge/${index}`,
    ),
  answerChallenge: (
    attemptId: number,
    index: number,
    payload: ChallengeAnswerPayload,
  ) =>
    apiFetch<ChallengeAnswerResult>(
      `/api/play/attempt/${attemptId}/challenge/${index}/answer`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  debrief: (attemptId: number) =>
    apiFetch<{ debrief: Debrief }>(
      `/api/play/attempt/${attemptId}/debrief`,
    ),
  rateAttempt: (attemptId: number, score: number) =>
    apiFetch<DebriefResult>(`/api/play/attempt/${attemptId}/rate`, {
      method: "POST",
      body: JSON.stringify({ score }),
    }),
  finishAttempt: (attemptId: number) =>
    apiFetch<DebriefResult>(`/api/play/attempt/${attemptId}/finish`, {
      method: "POST",
    }),
  retryAttempt: (attemptId: number) =>
    apiFetch<RetryResult>(`/api/play/attempt/${attemptId}/retry`, {
      method: "POST",
    }),
  postPlayEvent: (attemptId: number, event: PlayEventInput) =>
    apiFetch<PlayEventResult>(
      `/api/play/attempt/${attemptId}/events`,
      { method: "POST", body: JSON.stringify(event) },
    ),
  saveCheckpoint: (attemptId: number, input: CheckpointInput) =>
    apiFetch<CheckpointResult>(
      `/api/play/attempt/${attemptId}/checkpoints`,
      { method: "POST", body: JSON.stringify(input) },
    ),
  latestCheckpoint: (attemptId: number) =>
    apiFetch<{ checkpoint: Checkpoint }>(
      `/api/play/attempt/${attemptId}/checkpoints/latest`,
    ),
  decideLaunch: (attemptId: number, input: LaunchInput) =>
    apiFetch<LaunchDecision>(`/api/play/attempt/${attemptId}/launch`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listLaunches: (attemptId: number) =>
    apiFetch<{ launches: LaunchRecord[]; preview: boolean }>(
      `/api/play/attempt/${attemptId}/launch`,
    ),
  audit: (query?: AuditQuery) => {
    const params = new URLSearchParams();
    if (query?.actor) {
      params.set("actor", query.actor);
    }
    if (query?.since) {
      params.set("since", query.since);
    }
    if (query?.until) {
      params.set("until", query.until);
    }
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return apiFetch<AuditPayload>(`/api/audit${suffix}`);
  },
};
