"""Project data models (SQLAlchemy 2.0 style).

Database configuration comes from the environment (see .env.example at the
repo root — values are loaded from .env automatically):

    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
    POSTGRES_HOST, POSTGRES_PORT

A fully explicit DATABASE_URL takes precedence over the POSTGRES_* parts.

Table reference: docs/entities/ (one page per table). Add new models in this
file, subclassing :class:`Base`, then generate a migration with::

    uv run alembic revision --autogenerate -m "<description>"
    uv run alembic upgrade head
"""

from __future__ import annotations

import datetime
import enum
import os

from dotenv import load_dotenv
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    REAL,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

load_dotenv()  # finds .env here or in a parent dir (repo root)


def _database_url() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("POSTGRES_USER", "evolvingclass")
    password = os.environ.get("POSTGRES_PASSWORD", "evolvingclass")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "evolvingclass")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL = _database_url()


class Base(DeclarativeBase):
    """Declarative base for all project models."""

    type_annotation_map = {
        datetime.datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Adds created_at / updated_at columns to a model."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Enums, helpers
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"
    guardian = "guardian"


class VersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    retired = "retired"


class AssetKind(str, enum.Enum):
    environment = "environment"
    prop = "prop"
    media = "media"
    text = "text"
    script = "script"
    character = "character"
    challenge = "challenge"


class TagTaxonomy(str, enum.Enum):
    subject = "subject"
    objective = "objective"
    age_band = "age_band"
    role = "role"
    style = "style"


class DirectiveKind(str, enum.Enum):
    brief = "brief"
    steer = "steer"


class Decision(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"


class GoalEvaluation(str, enum.Enum):
    deterministic = "deterministic"
    teacher = "teacher"


class GenerationStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class GuardianStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class PreviewKind(str, enum.Enum):
    poster = "poster"
    turntable = "turntable"


class EventOrigin(str, enum.Enum):
    client = "client"
    server = "server"


class AssetVisibility(str, enum.Enum):
    school = "school"
    shared = "shared"


class MembershipStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class PublishAction(str, enum.Enum):
    published = "published"
    rolled_back = "rolled_back"
    retired = "retired"


def _py_enum(values: type[enum.Enum]) -> SAEnum:
    """Portable enum storage (VARCHAR). Pair with _enum_check for a real CHECK."""
    return SAEnum(values, native_enum=False, validate_strings=True)


def _enum_check(table: str, column: str, values: type[enum.Enum]) -> CheckConstraint:
    """Explicit value CHECK, since str-mixin enums render none themselves."""
    allowed = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"ck_{table}_{column}_enum")


JSON_VARIANT = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True), "postgresql"
)


def _exactly_one_of(table: str, *columns: str) -> CheckConstraint:
    """Exactly one of the given nullable columns must be set."""
    clauses = []
    for col in columns:
        others = " AND ".join(f"{o} IS NULL" for o in columns if o != col)
        clauses.append(f"({col} IS NOT NULL AND {others})")
    return CheckConstraint(" OR ".join(clauses), name=f"ck_{table}_one_target")


# ---------------------------------------------------------------------------
# People and rosters
# ---------------------------------------------------------------------------


class School(Base, TimestampMixin):
    __tablename__ = "school"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    classrooms: Mapped[list["Classroom"]] = relationship(back_populates="school")
    memberships: Mapped[list["Membership"]] = relationship(back_populates="school")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="school")


class Classroom(Base, TimestampMixin):
    __tablename__ = "classroom"

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    school: Mapped["School"] = relationship(back_populates="classrooms")
    memberships: Mapped[list["Membership"]] = relationship(back_populates="classroom")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="classroom")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="classroom")


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_user"
    __table_args__ = (
        UniqueConstraint("login_ref", name="uq_app_user_login"),
        _enum_check("app_user", "role", UserRole),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[UserRole] = mapped_column(_py_enum(UserRole), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    login_ref: Mapped[str] = mapped_column(String(200), nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", foreign_keys="Membership.user_id"
    )
    authored_directives: Mapped[list["Directive"]] = relationship(
        back_populates="author", foreign_keys="Directive.author_id"
    )
    targeted_directives: Mapped[list["Directive"]] = relationship(
        back_populates="student", foreign_keys="Directive.student_id"
    )
    approvals: Mapped[list["Approval"]] = relationship(back_populates="actor")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="author")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="student", foreign_keys="Attempt.student_id"
    )
    student_assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="student", foreign_keys="Assignment.student_id"
    )
    given_assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="assigned_by", foreign_keys="Assignment.assigned_by_id"
    )
    verdict_overrides: Mapped[list["VerdictOverride"]] = relationship(back_populates="teacher")
    scoped_lesson_versions: Mapped[list["LessonVersion"]] = relationship(
        back_populates="scope_student", foreign_keys="LessonVersion.student_scope_id"
    )
    created_assets: Mapped[list["Asset"]] = relationship(back_populates="creator")
    devices: Mapped[list["Device"]] = relationship(back_populates="student")
    guardianships: Mapped[list["StudentGuardian"]] = relationship(
        back_populates="student", foreign_keys="StudentGuardian.student_id"
    )
    ward_links: Mapped[list["StudentGuardian"]] = relationship(
        back_populates="guardian", foreign_keys="StudentGuardian.guardian_id"
    )
    consent_records: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="student", foreign_keys="ConsentRecord.student_id"
    )
    warded_consents: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="guardian", foreign_keys="ConsentRecord.guardian_id"
    )
    mastery_records: Mapped[list["MasteryRecord"]] = relationship(back_populates="student")
    publish_events: Mapped[list["PublishEvent"]] = relationship(back_populates="actor")


class Membership(Base):
    __tablename__ = "membership"
    __table_args__ = (
        _exactly_one_of("membership", "classroom_id", "school_id"),
        _enum_check("membership", "status", MembershipStatus),
        Index(
            "uq_membership_user_classroom", "user_id", "classroom_id", unique=True,
            postgresql_where=text("classroom_id IS NOT NULL"),
            sqlite_where=text("classroom_id IS NOT NULL"),
        ),
        Index(
            "uq_membership_user_school", "user_id", "school_id", unique=True,
            postgresql_where=text("school_id IS NOT NULL"),
            sqlite_where=text("school_id IS NOT NULL"),
        ),
        Index("ix_membership_user", "user_id"),
        Index("ix_membership_classroom", "classroom_id"),
        Index("ix_membership_school", "school_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classroom.id"))
    school_id: Mapped[int | None] = mapped_column(ForeignKey("school.id"))
    status: Mapped[MembershipStatus] = mapped_column(
        _py_enum(MembershipStatus), nullable=False, default=MembershipStatus.active
    )
    joined_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    left_at: Mapped[datetime.datetime | None] = mapped_column()

    user: Mapped["AppUser"] = relationship(back_populates="memberships")
    classroom: Mapped["Classroom | None"] = relationship(back_populates="memberships")
    school: Mapped["School | None"] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# Lessons and stages
# ---------------------------------------------------------------------------


class Lesson(Base, TimestampMixin):
    __tablename__ = "lesson"
    __table_args__ = (
        Index("ix_lesson_school", "school_id"),
        Index("ix_lesson_classroom", "classroom_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"), nullable=False)
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classroom.id"))
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    school: Mapped["School"] = relationship(back_populates="lessons")
    classroom: Mapped["Classroom | None"] = relationship(back_populates="lessons")
    versions: Mapped[list["LessonVersion"]] = relationship(back_populates="lesson")
    stages: Mapped[list["Stage"]] = relationship(back_populates="lesson")
    directives: Mapped[list["Directive"]] = relationship(back_populates="lesson")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="lesson")


class LessonVersion(Base, TimestampMixin):
    __tablename__ = "lesson_version"
    __table_args__ = (
        UniqueConstraint("lesson_id", "version_no", name="uq_lesson_version_no"),
        _enum_check("lesson_version", "status", VersionStatus),
        Index("ix_lesson_version_lesson_status", "lesson_id", "status"),
        Index("ix_lesson_version_scope", "student_scope_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(_py_enum(VersionStatus), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    objective_refs: Mapped[list] = mapped_column(JSON_VARIANT, nullable=False)
    student_scope_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    published_at: Mapped[datetime.datetime | None] = mapped_column()
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_run.id"))
    directive_snapshot: Mapped[dict | None] = mapped_column(JSON_VARIANT)

    lesson: Mapped["Lesson"] = relationship(back_populates="versions")
    scope_student: Mapped["AppUser | None"] = relationship(back_populates="scoped_lesson_versions")
    generation_run: Mapped["GenerationRun | None"] = relationship(back_populates="lesson_versions")
    asset_uses: Mapped[list["AssetUse"]] = relationship(back_populates="lesson_version")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="lesson_version")
    comments: Mapped[list["Comment"]] = relationship(back_populates="lesson_version")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="lesson_version")
    pinned_attempts: Mapped[list["Attempt"]] = relationship(back_populates="pinned_lesson_version")
    composition: Mapped[list["LessonVersionStage"]] = relationship(
        back_populates="lesson_version", order_by="LessonVersionStage.position"
    )
    publish_events: Mapped[list["PublishEvent"]] = relationship(
        back_populates="lesson_version"
    )
    mental_models: Mapped[list["MentalModel"]] = relationship(back_populates="lesson_version")


class Stage(Base, TimestampMixin):
    __tablename__ = "stage"
    __table_args__ = (Index("ix_stage_lesson", "lesson_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    lesson: Mapped["Lesson"] = relationship(back_populates="stages")
    versions: Mapped[list["StageVersion"]] = relationship(back_populates="stage")


class StageVersion(Base, TimestampMixin):
    __tablename__ = "stage_version"
    __table_args__ = (
        UniqueConstraint("stage_id", "version_no", name="uq_stage_version_no"),
        _enum_check("stage_version", "status", VersionStatus),
        Index("ix_stage_version_stage_status", "stage_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stage.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(_py_enum(VersionStatus), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_run.id"))
    directive_snapshot: Mapped[dict | None] = mapped_column(JSON_VARIANT)

    stage: Mapped["Stage"] = relationship(back_populates="versions")
    generation_run: Mapped["GenerationRun | None"] = relationship(back_populates="stage_versions")
    asset_uses: Mapped[list["AssetUse"]] = relationship(back_populates="stage_version")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="stage_version")
    comments: Mapped[list["Comment"]] = relationship(back_populates="stage_version")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="stage_version")
    previews: Mapped[list["PreviewArtifact"]] = relationship(back_populates="stage_version")
    attempt_pins: Mapped[list["AttemptPin"]] = relationship(back_populates="stage_version")
    scene_requirements: Mapped[list["SceneRequirement"]] = relationship(
        back_populates="stage_version"
    )
    checkpoints: Mapped[list["SessionCheckpoint"]] = relationship(back_populates="stage_version")
    lesson_links: Mapped[list["LessonVersionStage"]] = relationship(
        back_populates="stage_version"
    )
    publish_events: Mapped[list["PublishEvent"]] = relationship(
        back_populates="stage_version"
    )
    events: Mapped[list["ExperienceEvent"]] = relationship(back_populates="stage_version")


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class Asset(Base, TimestampMixin):
    __tablename__ = "asset"
    __table_args__ = (
        _enum_check("asset", "kind", AssetKind),
        _enum_check("asset", "visibility", AssetVisibility),
        Index("ix_asset_school", "school_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[AssetKind] = mapped_column(_py_enum(AssetKind), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("school.id"))
    visibility: Mapped[AssetVisibility] = mapped_column(
        _py_enum(AssetVisibility), nullable=False, default=AssetVisibility.school
    )

    creator: Mapped["AppUser"] = relationship(back_populates="created_assets")
    school: Mapped["School | None"] = relationship()
    versions: Mapped[list["AssetVersion"]] = relationship(back_populates="asset")


class AssetVersion(Base, TimestampMixin):
    __tablename__ = "asset_version"
    __table_args__ = (
        UniqueConstraint("asset_id", "version_no", name="uq_asset_version_no"),
        _enum_check("asset_version", "status", VersionStatus),
        Index("ix_asset_version_asset_status", "asset_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[VersionStatus] = mapped_column(_py_enum(VersionStatus), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    objective_refs: Mapped[list] = mapped_column(JSON_VARIANT, nullable=False)
    content_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    param_schema: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    generation_run_id: Mapped[int | None] = mapped_column(ForeignKey("generation_run.id"))
    directive_snapshot: Mapped[dict | None] = mapped_column(JSON_VARIANT)

    asset: Mapped["Asset"] = relationship(back_populates="versions")
    generation_run: Mapped["GenerationRun | None"] = relationship(back_populates="asset_versions")
    tags: Mapped[list["AssetTag"]] = relationship(back_populates="asset_version")
    uses: Mapped[list["AssetUse"]] = relationship(
        back_populates="asset_version", foreign_keys="AssetUse.asset_version_id"
    )
    challenge_uses: Mapped[list["AssetUse"]] = relationship(
        back_populates="challenge_version", foreign_keys="AssetUse.challenge_version_id"
    )
    goals: Mapped[list["Goal"]] = relationship(back_populates="challenge_version")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="asset_version")
    comments: Mapped[list["Comment"]] = relationship(back_populates="asset_version")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="asset_version")
    rollups: Mapped[list["ImpactRollup"]] = relationship(back_populates="asset_version")
    previews: Mapped[list["PreviewArtifact"]] = relationship(back_populates="asset_version")
    used_events: Mapped[list["ExperienceEvent"]] = relationship(
        back_populates="asset_version", foreign_keys="ExperienceEvent.asset_version_id"
    )
    challenge_events: Mapped[list["ExperienceEvent"]] = relationship(
        back_populates="challenge_version", foreign_keys="ExperienceEvent.challenge_version_id"
    )
    publish_events: Mapped[list["PublishEvent"]] = relationship(
        back_populates="asset_version"
    )


class AssetTag(Base):
    __tablename__ = "asset_tag"
    __table_args__ = (
        UniqueConstraint(
            "asset_version_id", "taxonomy", "value", name="uq_asset_tag_value"
        ),
        _enum_check("asset_tag", "taxonomy", TagTaxonomy),
        Index("ix_asset_tag_version", "asset_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int] = mapped_column(
        ForeignKey("asset_version.id"), nullable=False
    )
    taxonomy: Mapped[TagTaxonomy] = mapped_column(_py_enum(TagTaxonomy), nullable=False)
    value: Mapped[str] = mapped_column(String(200), nullable=False)

    asset_version: Mapped["AssetVersion"] = relationship(back_populates="tags")


class AssetUse(Base):
    __tablename__ = "asset_use"
    __table_args__ = (
        _exactly_one_of(
            "asset_use", "lesson_version_id", "stage_version_id", "challenge_version_id"
        ),
        Index("ix_asset_use_asset", "asset_version_id"),
        Index("ix_asset_use_lesson", "lesson_version_id"),
        Index("ix_asset_use_stage", "stage_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int] = mapped_column(
        ForeignKey("asset_version.id"), nullable=False
    )
    lesson_version_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    challenge_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    param_overrides: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)

    asset_version: Mapped["AssetVersion"] = relationship(
        back_populates="uses", foreign_keys=[asset_version_id]
    )
    lesson_version: Mapped["LessonVersion | None"] = relationship(back_populates="asset_uses")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="asset_uses")
    challenge_version: Mapped["AssetVersion | None"] = relationship(
        back_populates="challenge_uses", foreign_keys=[challenge_version_id]
    )
    events: Mapped[list["ExperienceEvent"]] = relationship(back_populates="asset_use")


class LessonVersionStage(Base):
    """Pins stage versions into a lesson version, in order (finding 1)."""

    __tablename__ = "lesson_version_stage"
    __table_args__ = (
        UniqueConstraint(
            "lesson_version_id", "position", name="uq_lvs_position"
        ),
        UniqueConstraint(
            "lesson_version_id", "stage_version_id", name="uq_lvs_stage"
        ),
        Index("ix_lvs_stage_version", "stage_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_version_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_version.id"), nullable=False
    )
    stage_version_id: Mapped[int] = mapped_column(
        ForeignKey("stage_version.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    lesson_version: Mapped["LessonVersion"] = relationship(back_populates="composition")
    stage_version: Mapped["StageVersion"] = relationship(back_populates="lesson_links")


class PublishEvent(Base):
    """Audit log for publish / rollback / retire actions (finding 2)."""

    __tablename__ = "publish_event"
    __table_args__ = (
        _exactly_one_of(
            "publish_event", "asset_version_id", "stage_version_id", "lesson_version_id"
        ),
        _enum_check("publish_event", "action", PublishAction),
        Index("ix_publish_event_asset", "asset_version_id"),
        Index("ix_publish_event_stage", "stage_version_id"),
        Index("ix_publish_event_lesson", "lesson_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    lesson_version_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_version.id"))
    action: Mapped[PublishAction] = mapped_column(_py_enum(PublishAction), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion | None"] = relationship(
        back_populates="publish_events"
    )
    stage_version: Mapped["StageVersion | None"] = relationship(
        back_populates="publish_events"
    )
    lesson_version: Mapped["LessonVersion | None"] = relationship(
        back_populates="publish_events"
    )
    actor: Mapped["AppUser"] = relationship(back_populates="publish_events")


class GoalMisconception(Base):
    """Which misconceptions each goal probes (finding 7)."""

    __tablename__ = "goal_misconception"
    __table_args__ = (
        Index("ix_goal_misconception_model", "misconception_id"),
    )

    goal_id: Mapped[int] = mapped_column(ForeignKey("goal.id"), primary_key=True)
    misconception_id: Mapped[int] = mapped_column(
        ForeignKey("misconception.id"), primary_key=True
    )


# ---------------------------------------------------------------------------
# Goals and mental models
# ---------------------------------------------------------------------------


class Goal(Base, TimestampMixin):
    __tablename__ = "goal"
    __table_args__ = (
        UniqueConstraint(
            "challenge_version_id", "key", name="uq_goal_challenge_key"
        ),
        _enum_check("goal", "evaluation", GoalEvaluation),
        CheckConstraint(
            "(evaluation <> 'teacher') OR (rubric IS NOT NULL)",
            name="ck_goal_rubric_required",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_version_id: Mapped[int] = mapped_column(
        ForeignKey("asset_version.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    rule: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    evaluation: Mapped[GoalEvaluation] = mapped_column(
        _py_enum(GoalEvaluation), nullable=False
    )
    rubric: Mapped[dict | None] = mapped_column(JSON_VARIANT)
    template_ref: Mapped[str] = mapped_column(String(200), nullable=False)

    challenge_version: Mapped["AssetVersion"] = relationship(back_populates="goals")
    mental_models: Mapped[list["MentalModel"]] = relationship(
        secondary="goal_mental_model", back_populates="goals"
    )
    verdict_events: Mapped[list["ExperienceEvent"]] = relationship(back_populates="goal")
    probed_misconceptions: Mapped[list["Misconception"]] = relationship(
        secondary="goal_misconception", back_populates="probing_goals"
    )


class GoalMentalModel(Base):
    __tablename__ = "goal_mental_model"
    __table_args__ = (
        Index("ix_goal_mental_model_model", "mental_model_id"),
    )

    goal_id: Mapped[int] = mapped_column(ForeignKey("goal.id"), primary_key=True)
    mental_model_id: Mapped[int] = mapped_column(
        ForeignKey("mental_model.id"), primary_key=True
    )


class MentalModel(Base):
    __tablename__ = "mental_model"
    __table_args__ = (
        Index("ix_mental_model_lesson_version", "lesson_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_version_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_version.id"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    lesson_version: Mapped["LessonVersion"] = relationship(back_populates="mental_models")
    misconceptions: Mapped[list["Misconception"]] = relationship(back_populates="mental_model")
    goals: Mapped[list["Goal"]] = relationship(
        secondary="goal_mental_model", back_populates="mental_models"
    )
    mastery_records: Mapped[list["MasteryRecord"]] = relationship(back_populates="mental_model")


class Misconception(Base):
    __tablename__ = "misconception"

    id: Mapped[int] = mapped_column(primary_key=True)
    mental_model_id: Mapped[int] = mapped_column(
        ForeignKey("mental_model.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    probe_notes: Mapped[str] = mapped_column(Text, nullable=False)

    mental_model: Mapped["MentalModel"] = relationship(back_populates="misconceptions")
    probing_goals: Mapped[list["Goal"]] = relationship(
        secondary="goal_misconception", back_populates="probed_misconceptions"
    )


# ---------------------------------------------------------------------------
# Direction and gates
# ---------------------------------------------------------------------------


class Directive(Base, TimestampMixin):
    __tablename__ = "directive"
    __table_args__ = (
        _enum_check("directive", "kind", DirectiveKind),
        Index("ix_directive_lesson_active", "lesson_id", "active"),
        Index("ix_directive_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    kind: Mapped[DirectiveKind] = mapped_column(_py_enum(DirectiveKind), nullable=False)
    focus: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    lesson: Mapped["Lesson"] = relationship(back_populates="directives")
    student: Mapped["AppUser | None"] = relationship(
        back_populates="targeted_directives", foreign_keys=[student_id]
    )
    author: Mapped["AppUser"] = relationship(
        back_populates="authored_directives", foreign_keys=[author_id]
    )


class Approval(Base):
    __tablename__ = "approval"
    __table_args__ = (
        _exactly_one_of(
            "approval", "asset_version_id", "stage_version_id", "lesson_version_id"
        ),
        _enum_check("approval", "decision", Decision),
        Index("ix_approval_asset", "asset_version_id"),
        Index("ix_approval_stage", "stage_version_id"),
        Index("ix_approval_lesson", "lesson_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    lesson_version_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_version.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    decision: Mapped[Decision] = mapped_column(_py_enum(Decision), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion | None"] = relationship(back_populates="approvals")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="approvals")
    lesson_version: Mapped["LessonVersion | None"] = relationship(back_populates="approvals")
    actor: Mapped["AppUser"] = relationship(back_populates="approvals")


class Comment(Base):
    __tablename__ = "comment"
    __table_args__ = (
        _exactly_one_of(
            "comment", "asset_version_id", "stage_version_id", "lesson_version_id"
        ),
        Index("ix_comment_asset", "asset_version_id"),
        Index("ix_comment_stage", "stage_version_id"),
        Index("ix_comment_lesson", "lesson_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    lesson_version_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_version.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion | None"] = relationship(back_populates="comments")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="comments")
    lesson_version: Mapped["LessonVersion | None"] = relationship(back_populates="comments")
    author: Mapped["AppUser"] = relationship(back_populates="comments")


class Rating(Base):
    __tablename__ = "rating"
    __table_args__ = (
        _exactly_one_of(
            "rating", "asset_version_id", "stage_version_id", "lesson_version_id"
        ),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_rating_score_bounds"),
        Index("ix_rating_asset", "asset_version_id"),
        Index("ix_rating_stage", "stage_version_id"),
        Index("ix_rating_lesson", "lesson_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    lesson_version_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_version.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion | None"] = relationship(back_populates="ratings")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="ratings")
    lesson_version: Mapped["LessonVersion | None"] = relationship(back_populates="ratings")
    author: Mapped["AppUser"] = relationship(back_populates="ratings")


# ---------------------------------------------------------------------------
# Assignment and play
# ---------------------------------------------------------------------------


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignment"
    __table_args__ = (
        _exactly_one_of("assignment", "classroom_id", "student_id"),
        Index("ix_assignment_lesson", "lesson_id"),
        Index("ix_assignment_classroom", "classroom_id"),
        Index("ix_assignment_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id"), nullable=False)
    classroom_id: Mapped[int | None] = mapped_column(ForeignKey("classroom.id"))
    student_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    due_at: Mapped[datetime.datetime | None] = mapped_column()

    lesson: Mapped["Lesson"] = relationship(back_populates="assignments")
    classroom: Mapped["Classroom | None"] = relationship(back_populates="assignments")
    student: Mapped["AppUser | None"] = relationship(
        back_populates="student_assignments", foreign_keys=[student_id]
    )
    assigned_by: Mapped["AppUser"] = relationship(
        back_populates="given_assignments", foreign_keys=[assigned_by_id]
    )
    attempts: Mapped[list["Attempt"]] = relationship(back_populates="assignment")


class Attempt(Base):
    __tablename__ = "attempt"
    __table_args__ = (
        Index("ix_attempt_assignment", "assignment_id"),
        Index("ix_attempt_student", "student_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignment.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    pinned_lesson_version_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_version.id"), nullable=False
    )
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("attempt.id"))
    started_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime.datetime | None] = mapped_column()

    assignment: Mapped["Assignment"] = relationship(back_populates="attempts")
    retry_of: Mapped["Attempt | None"] = relationship(
        back_populates="retries", foreign_keys=[retry_of_id], remote_side="Attempt.id"
    )
    retries: Mapped[list["Attempt"]] = relationship(
        back_populates="retry_of", foreign_keys=[retry_of_id]
    )
    student: Mapped["AppUser"] = relationship(back_populates="attempts")
    pinned_lesson_version: Mapped["LessonVersion"] = relationship(
        back_populates="pinned_attempts"
    )
    pins: Mapped[list["AttemptPin"]] = relationship(back_populates="attempt")
    events: Mapped[list["ExperienceEvent"]] = relationship(back_populates="attempt")
    checkpoints: Mapped[list["SessionCheckpoint"]] = relationship(back_populates="attempt")


class AttemptPin(Base):
    __tablename__ = "attempt_pin"
    __table_args__ = (
        UniqueConstraint("attempt_id", "stage_version_id", name="uq_attempt_pin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.id"), nullable=False)
    stage_version_id: Mapped[int] = mapped_column(
        ForeignKey("stage_version.id"), nullable=False
    )

    attempt: Mapped["Attempt"] = relationship(back_populates="pins")
    stage_version: Mapped["StageVersion"] = relationship(back_populates="attempt_pins")


class ExperienceEvent(Base):
    __tablename__ = "experience_event"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "client_event_id", name="uq_event_attempt_client_id"
        ),
        UniqueConstraint(
            "attempt_id", "sequence_no", name="uq_event_attempt_sequence"
        ),
        _enum_check("experience_event", "origin", EventOrigin),
        CheckConstraint(
            "(origin = 'server') OR "
            "(origin = 'client' AND verb NOT IN ('goal-verdict', 'teacher-evaluation'))",
            name="ck_event_server_verbs",
        ),
        Index("ix_event_attempt_verb", "attempt_id", "verb"),
        Index("ix_event_goal", "goal_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.id"), nullable=False)
    client_event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    origin: Mapped[EventOrigin] = mapped_column(_py_enum(EventOrigin), nullable=False)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    verb: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goal.id"))
    challenge_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    asset_use_id: Mapped[int | None] = mapped_column(ForeignKey("asset_use.id"))
    evaluator_version: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    occurred_at: Mapped[datetime.datetime | None] = mapped_column()
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    attempt: Mapped["Attempt"] = relationship(back_populates="events")
    device: Mapped["Device | None"] = relationship(back_populates="events")
    actor: Mapped["AppUser"] = relationship()
    goal: Mapped["Goal | None"] = relationship(back_populates="verdict_events")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="events")
    asset_use: Mapped["AssetUse | None"] = relationship(back_populates="events")
    challenge_version: Mapped["AssetVersion | None"] = relationship(
        back_populates="challenge_events", foreign_keys=[challenge_version_id]
    )
    asset_version: Mapped["AssetVersion | None"] = relationship(
        back_populates="used_events", foreign_keys=[asset_version_id]
    )
    override: Mapped["VerdictOverride | None"] = relationship(back_populates="verdict_event")
    mastery_evidence: Mapped[list["MasteryEvidence"]] = relationship(
        back_populates="experience_event"
    )


# ---------------------------------------------------------------------------
# Derived, rendered, and runtime
# ---------------------------------------------------------------------------


class VerdictOverride(Base):
    """Append-only correction history; latest row per verdict wins (finding 3)."""

    __tablename__ = "verdict_override"
    __table_args__ = (Index("ix_override_verdict", "verdict_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    verdict_event_id: Mapped[int] = mapped_column(
        ForeignKey("experience_event.id"), nullable=False
    )
    teacher_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    corrected_score: Mapped[float | None] = mapped_column(REAL)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    verdict_event: Mapped["ExperienceEvent"] = relationship(back_populates="override")
    teacher: Mapped["AppUser"] = relationship(back_populates="verdict_overrides")


class ImpactRollup(Base):
    __tablename__ = "impact_rollup"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int] = mapped_column(
        ForeignKey("asset_version.id"), nullable=False
    )
    window: Mapped[str] = mapped_column(String(16), nullable=False)
    mastery: Mapped[float] = mapped_column(REAL, nullable=False)
    completion: Mapped[float] = mapped_column(REAL, nullable=False)
    enjoyment: Mapped[float] = mapped_column(REAL, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(32), nullable=False)
    cohort: Mapped[str | None] = mapped_column(String(200))
    uncertainty: Mapped[float | None] = mapped_column(REAL)
    baseline: Mapped[dict | None] = mapped_column(JSON_VARIANT)
    computed_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion"] = relationship(back_populates="rollups")


class PreviewArtifact(Base):
    __tablename__ = "preview_artifact"
    __table_args__ = (
        _exactly_one_of("preview_artifact", "asset_version_id", "stage_version_id"),
        _enum_check("preview_artifact", "kind", PreviewKind),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_version_id: Mapped[int | None] = mapped_column(ForeignKey("asset_version.id"))
    stage_version_id: Mapped[int | None] = mapped_column(ForeignKey("stage_version.id"))
    kind: Mapped[PreviewKind] = mapped_column(_py_enum(PreviewKind), nullable=False)
    storage_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    rendered_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    asset_version: Mapped["AssetVersion | None"] = relationship(back_populates="previews")
    stage_version: Mapped["StageVersion | None"] = relationship(back_populates="previews")


class SessionCheckpoint(Base):
    __tablename__ = "session_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "checkpoint_sequence", name="uq_checkpoint_sequence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.id"), nullable=False)
    stage_version_id: Mapped[int] = mapped_column(
        ForeignKey("stage_version.id"), nullable=False
    )
    checkpoint_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    attempt: Mapped["Attempt"] = relationship(back_populates="checkpoints")
    stage_version: Mapped["StageVersion"] = relationship(back_populates="checkpoints")


class MasteryRecord(Base):
    __tablename__ = "mastery_record"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "mental_model_id", name="uq_mastery_student_model"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    mental_model_id: Mapped[int] = mapped_column(
        ForeignKey("mental_model.id"), nullable=False
    )
    objective: Mapped[str | None] = mapped_column(String(200))
    score: Mapped[float] = mapped_column(REAL, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["AppUser"] = relationship(back_populates="mastery_records")
    mental_model: Mapped["MentalModel"] = relationship(back_populates="mastery_records")
    evidence: Mapped[list["MasteryEvidence"]] = relationship(back_populates="mastery_record")


class MasteryEvidence(Base):
    __tablename__ = "mastery_evidence"
    __table_args__ = (Index("ix_mastery_evidence_record", "mastery_record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mastery_record_id: Mapped[int] = mapped_column(
        ForeignKey("mastery_record.id"), nullable=False
    )
    experience_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("experience_event.id")
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(REAL, nullable=False)
    observed_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    mastery_record: Mapped["MasteryRecord"] = relationship(back_populates="evidence")
    experience_event: Mapped["ExperienceEvent | None"] = relationship(
        back_populates="mastery_evidence"
    )


class GenerationRun(Base):
    __tablename__ = "generation_run"
    __table_args__ = (_enum_check("generation_run", "status", GenerationStatus),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    model_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    params: Mapped[dict] = mapped_column(JSON_VARIANT, nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        _py_enum(GenerationStatus), nullable=False, default=GenerationStatus.queued
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    policy_version: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime.datetime | None] = mapped_column()

    asset_versions: Mapped[list["AssetVersion"]] = relationship(
        back_populates="generation_run"
    )
    stage_versions: Mapped[list["StageVersion"]] = relationship(
        back_populates="generation_run"
    )
    lesson_versions: Mapped[list["LessonVersion"]] = relationship(
        back_populates="generation_run"
    )


class Device(Base):
    __tablename__ = "device"
    __table_args__ = (Index("ix_device_student", "student_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    student: Mapped["AppUser"] = relationship(back_populates="devices")
    capabilities: Mapped[list["DeviceCapability"]] = relationship(back_populates="device")
    events: Mapped[list["ExperienceEvent"]] = relationship(back_populates="device")


class DeviceCapability(Base):
    __tablename__ = "device_capability"
    __table_args__ = (
        UniqueConstraint("device_id", "capability", name="uq_device_capability"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(200))
    reported_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    device: Mapped["Device"] = relationship(back_populates="capabilities")


class SceneRequirement(Base):
    __tablename__ = "scene_requirement"
    __table_args__ = (
        UniqueConstraint(
            "stage_version_id", "capability", name="uq_scene_requirement"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stage_version_id: Mapped[int] = mapped_column(
        ForeignKey("stage_version.id"), nullable=False
    )
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)

    stage_version: Mapped["StageVersion"] = relationship(
        back_populates="scene_requirements"
    )


class StudentGuardian(Base):
    __tablename__ = "student_guardian"
    __table_args__ = (
        UniqueConstraint("student_id", "guardian_id", name="uq_student_guardian"),
        _enum_check("student_guardian", "status", GuardianStatus),
        Index("ix_student_guardian_guardian", "guardian_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    relation: Mapped[str] = mapped_column("relationship", String(100), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[GuardianStatus] = mapped_column(_py_enum(GuardianStatus), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    student: Mapped["AppUser"] = relationship(
        back_populates="guardianships", foreign_keys=[student_id]
    )
    guardian: Mapped["AppUser"] = relationship(
        back_populates="ward_links", foreign_keys=[guardian_id]
    )


class ConsentRecord(Base):
    __tablename__ = "consent_record"
    __table_args__ = (
        Index(
            "ix_consent_student_type_policy",
            "student_id", "consent_type", "policy_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    guardian_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    granted_at: Mapped[datetime.datetime | None] = mapped_column()
    revoked_at: Mapped[datetime.datetime | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(200), nullable=False)

    student: Mapped["AppUser"] = relationship(
        back_populates="consent_records", foreign_keys=[student_id]
    )
    guardian: Mapped["AppUser | None"] = relationship(
        back_populates="warded_consents", foreign_keys=[guardian_id]
    )


def get_engine(url: str = DATABASE_URL):
    """Create a SQLAlchemy engine for the given database URL."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def get_session_factory(url: str = DATABASE_URL) -> sessionmaker[Session]:
    """Create a session factory bound to an engine for the given URL."""
    return sessionmaker(bind=get_engine(url), autoflush=False, expire_on_commit=False)


SessionLocal = get_session_factory()


__all__ = [
    "Approval",
    "Asset",
    "AssetKind",
    "AssetTag",
    "AssetUse",
    "AssetVersion",
    "AssetVisibility",
    "Assignment",
    "Attempt",
    "AttemptPin",
    "Base",
    "Classroom",
    "Comment",
    "ConsentRecord",
    "DATABASE_URL",
    "Decision",
    "Device",
    "DeviceCapability",
    "Directive",
    "DirectiveKind",
    "EventOrigin",
    "ExperienceEvent",
    "GenerationRun",
    "GenerationStatus",
    "Goal",
    "GoalEvaluation",
    "GoalMentalModel",
    "GoalMisconception",
    "GuardianStatus",
    "ImpactRollup",
    "Lesson",
    "LessonVersion",
    "LessonVersionStage",
    "MasteryEvidence",
    "MasteryRecord",
    "Membership",
    "MembershipStatus",
    "MentalModel",
    "Misconception",
    "PreviewArtifact",
    "PreviewKind",
    "PublishAction",
    "PublishEvent",
    "Rating",
    "School",
    "SceneRequirement",
    "SessionCheckpoint",
    "SessionLocal",
    "Stage",
    "StageVersion",
    "StudentGuardian",
    "TagTaxonomy",
    "TimestampMixin",
    "UserRole",
    "VerdictOverride",
    "VersionStatus",
    "AppUser",
    "get_engine",
    "get_session_factory",
]
