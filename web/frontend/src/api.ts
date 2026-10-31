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
  version_no: number;
  status: string;
  role: string;
  mastery: string;
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

export interface Briefing {
  assignment_id: number;
  lesson: string;
  published: boolean;
  objectives?: string[];
  models?: string[];
  stages?: string[];
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

export interface Challenge {
  attempt_id: number;
  assignment_id: number;
  index: number;
  total: number;
  stage: string;
  title: string;
  challenge_version_id: number;
  goals: ChallengeGoal[];
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
}

export interface Debrief {
  attempt_id: number;
  assignment_id: number;
  lesson: string;
  finished: boolean;
  verdicts: DebriefVerdict[];
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
    payload: { rationale: string; content_ref?: string },
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
