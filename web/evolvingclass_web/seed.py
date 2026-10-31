"""Demo data for the review queues.

Builds one school with a teacher, a lesson, and proposals at every
level — drafts to review, a live version to retire, and a retired
version to roll back to. All state transitions go through the real
publication service, so the audit trail is genuine.

Usage (from the repository root)::

    cd web
    PYTHONPATH=/Users/simeon/Projects/EvolvingClass/database:/Users/simeon/Projects/EvolvingClass/service \
      ../service/.venv/bin/python -m evolvingclass_web.seed
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from DataModels import (
    AppUser,
    Asset,
    AssetKind,
    AssetTag,
    AssetUse,
    AssetVersion,
    Base,
    Classroom,
    Decision,
    Directive,
    DirectiveKind,
    GenerationRun,
    GenerationStatus,
    Goal,
    GoalEvaluation,
    ImpactRollup,
    Lesson,
    LessonVersion,
    LessonVersionStage,
    Membership,
    MembershipStatus,
    MentalModel,
    Misconception,
    School,
    Stage,
    StageVersion,
    TagTaxonomy,
    UserRole,
    VersionStatus,
)
from evolvingclass_service import (
    publish_asset_version,
    publish_lesson_version,
    publish_stage_version,
    record_approval,
    retire_lesson_version,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = f"sqlite:///{os.path.join(os.path.dirname(HERE), 'dev.db')}"


def _approve(factory, kind: str, version_id: int, actor: int,
             decision: Decision = Decision.approved) -> None:
    record_approval(factory, kind, version_id, actor, decision, "seed")


def seed(database_url: str = DEFAULT_URL) -> dict:
    """Create demo data unless the pilot school already exists."""
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        if session.scalar(select(School.id).where(
                School.name == "Pilot School")) is not None:
            print("Pilot School already present; leaving data alone.")
            return {}
        ids = _build(session, factory)
        session.commit()
    print(f"Seeded demo data into {database_url}")
    return ids


def _build(session: Session, factory: sessionmaker) -> dict:
    school = School(name="Pilot School")
    session.add(school)
    session.flush()
    room = Classroom(school_id=school.id, name="Room 1")
    teacher = AppUser(role=UserRole.teacher, display_name="Tess",
                      login_ref="tess")
    admin = AppUser(role=UserRole.admin, display_name="Ash",
                    login_ref="ash")
    student = AppUser(role=UserRole.student, display_name="Sam",
                      login_ref="sam")
    session.add_all([room, teacher, admin, student])
    session.flush()
    session.add_all([
        Membership(user_id=teacher.id, classroom_id=room.id,
                   status=MembershipStatus.active),
        Membership(user_id=admin.id, school_id=school.id,
                   status=MembershipStatus.active),
        Membership(user_id=student.id, classroom_id=room.id,
                   status=MembershipStatus.active),
    ])
    lesson = Lesson(school_id=school.id, classroom_id=room.id,
                    subject="science", title="Volcanoes")
    session.add(lesson)
    session.flush()
    brief = Directive(lesson_id=lesson.id, kind=DirectiveKind.brief,
                      focus="Cover the three eruption stages in order.",
                      constraints={}, priority=1, author_id=teacher.id,
                      active=True)
    steer = Directive(lesson_id=lesson.id, kind=DirectiveKind.steer,
                      focus="Add a labeling challenge for slow readers.",
                      constraints={"reading_level": "grade-4"},
                      priority=2, author_id=teacher.id, active=True)
    session.add_all([brief, steer])
    session.flush()
    run = GenerationRun(agent_ref="lesson-planner", model_ref="template-1",
                        prompt_ref="prompts/volcanoes", params={},
                        status=GenerationStatus.completed, attempts=1)
    session.add(run)
    session.flush()

    def snapshot(*directives: Directive, brief_text: str) -> dict:
        return {
            "brief": brief_text,
            "directives": [{"id": d.id, "focus": d.focus}
                           for d in directives],
        }

    ids: dict = {"teacher_id": teacher.id, "lesson_id": lesson.id,
                 "student_id": student.id}

    # -- assets ------------------------------------------------------
    def add_asset(title: str, kind: AssetKind, no: int, status_note: str,
                  content: str, snap: dict, run_id: int | None,
                  asset: Asset | None = None) -> AssetVersion:
        if asset is None:
            asset = Asset(kind=kind, title=title,
                          created_by_id=teacher.id, school_id=school.id)
            session.add(asset)
            session.flush()
        version = AssetVersion(
            asset_id=asset.id, version_no=no, status=VersionStatus.draft,
            rationale=status_note, objective_refs=["sci.eruptions"],
            content_ref=content, param_schema={"scale": "number"},
            generation_run_id=run_id, directive_snapshot=snap)
        session.add(version)
        session.flush()
        session.add(AssetTag(asset_version_id=version.id,
                             taxonomy=TagTaxonomy.subject, value="science"))
        return version

    volcano_v1 = add_asset(
        "Volcano Model", AssetKind.prop, 1, "Initial model from the brief.",
        "content/volcano-v1.glb", snapshot(brief, brief_text="Model Mt. Ash."),
        run.id)
    session.commit()
    _approve(factory, "asset", volcano_v1.id, teacher.id)
    publish_asset_version(factory, volcano_v1.id, teacher.id, "Looks right.")
    with factory() as session2:
        session2.add(ImpactRollup(
            asset_version_id=volcano_v1.id, window="7d", mastery=0.72,
            completion=0.91, enjoyment=0.80, sample_size=24,
            formula_version="v1", cohort="Room 1", uncertainty=0.05))
        session2.commit()
    volcano_asset = session.get(Asset, volcano_v1.asset_id)

    rocks_v1 = add_asset(
        "Rock Samples", AssetKind.prop, 1, "Companion samples set.",
        "content/rocks-v1.glb", snapshot(brief, brief_text="Samples kit."),
        run.id)
    session.commit()
    _approve(factory, "asset", rocks_v1.id, teacher.id)
    publish_asset_version(factory, rocks_v1.id, teacher.id, "Fine.")

    sediment_v1 = add_asset(
        "Sediment Tray", AssetKind.prop, 1, "Grain-size sorting tray.",
        "content/sediment-v1.glb", snapshot(brief, brief_text="Sorting tray."),
        run.id)
    session.commit()
    _approve(factory, "asset", sediment_v1.id, teacher.id)
    publish_asset_version(factory, sediment_v1.id, teacher.id, "Fine.")
    with factory() as session2:
        session2.add(ImpactRollup(
            asset_version_id=sediment_v1.id, window="30d", mastery=0.31,
            completion=0.55, enjoyment=0.40, sample_size=12,
            formula_version="v1", cohort="Room 1", uncertainty=0.09))
        session2.commit()
    ids["sediment_live_id"] = sediment_v1.id

    volcano_v2 = add_asset(
        "Volcano Model", AssetKind.prop, 2,
        "Sharper crater lip; fixes the flat shading agents reported.",
        "content/volcano-v2.glb",
        snapshot(brief, brief_text="Polish pass."), run.id,
        asset=volcano_asset)
    ids["asset_draft_id"] = volcano_v2.id

    challenge_v1 = add_asset(
        "Label the Parts", AssetKind.challenge, 1,
        "Drag labels onto the crater, vent, and chamber.",
        "content/label-v1.json",
        snapshot(brief, steer, brief_text="Labeling challenge."), run.id)
    session.add_all([
        Goal(challenge_version_id=challenge_v1.id, key="crater",
             rule={"verb": "goal-attempted", "object_ref": "crater",
                   "require": "present"},
             evaluation=GoalEvaluation.deterministic,
             template_ref="label"),
        Goal(challenge_version_id=challenge_v1.id, key="vent",
             rule={"verb": "goal-attempted", "object_ref": "vent",
                   "require": "present"},
             evaluation=GoalEvaluation.deterministic,
             template_ref="label"),
    ])
    session.flush()
    ids["challenge_draft_id"] = challenge_v1.id

    # -- stages ------------------------------------------------------
    stage = Stage(lesson_id=lesson.id, position=1, title="Eruption")
    session.add(stage)
    session.flush()
    stage_v1 = StageVersion(stage_id=stage.id, version_no=1,
                            status=VersionStatus.draft,
                            rationale="First staging of the eruption.",
                            generation_run_id=run.id,
                            directive_snapshot=snapshot(
                                brief, brief_text="Stage the eruption."))
    session.add(stage_v1)
    session.flush()
    session.add(AssetUse(asset_version_id=volcano_v1.id,
                         stage_version_id=stage_v1.id, position=1,
                         role="centerpiece", param_overrides={}))
    session.commit()
    _approve(factory, "stage", stage_v1.id, teacher.id)
    publish_stage_version(factory, stage_v1.id, teacher.id, "Staged well.")

    stage_v2 = StageVersion(
        stage_id=stage.id, version_no=2, status=VersionStatus.draft,
        rationale="Adds the labeling challenge after the eruption beat.",
        generation_run_id=run.id,
        directive_snapshot=snapshot(
            brief, steer, brief_text="Add the challenge."))
    session.add(stage_v2)
    session.flush()
    session.add_all([
        AssetUse(asset_version_id=volcano_v2.id,
                 stage_version_id=stage_v2.id, position=1,
                 role="centerpiece", param_overrides={}),
        AssetUse(asset_version_id=challenge_v1.id,
                 stage_version_id=stage_v2.id, position=2,
                 role="challenge", param_overrides={}),
    ])
    session.flush()
    ids["stage_draft_id"] = stage_v2.id

    # -- lessons -----------------------------------------------------
    def add_lesson_version(no: int, note: str, stage_v: StageVersion,
                           snap: dict) -> LessonVersion:
        version = LessonVersion(
            lesson_id=lesson.id, version_no=no, status=VersionStatus.draft,
            rationale=note, objective_refs=["sci.eruptions"],
            generation_run_id=run.id, directive_snapshot=snap)
        session.add(version)
        session.flush()
        session.add(LessonVersionStage(lesson_version_id=version.id,
                                       stage_version_id=stage_v.id,
                                       position=1))
        model = MentalModel(lesson_version_id=version.id, position=1,
                            statement="Eruptions move magma from chamber "
                                      "to surface through a vent.")
        session.add(model)
        session.flush()
        session.add(Misconception(
            mental_model_id=model.id,
            description="Lava and magma are unrelated substances.",
            probe_notes="Ask where the chamber lava goes."))
        return version

    lesson_v1 = add_lesson_version(
        1, "First full lesson.", stage_v1,
        snapshot(brief, brief_text="Volcanoes v1."))
    session.commit()
    _approve(factory, "lesson", lesson_v1.id, teacher.id)
    publish_lesson_version(factory, lesson_v1.id, teacher.id, "Ship it.")
    retire_lesson_version(factory, lesson_v1.id, teacher.id,
                          "Superseded by v2.")
    ids["lesson_retired_id"] = lesson_v1.id

    lesson_v2 = add_lesson_version(
        2, "Tighter pacing on the eruption beat.", stage_v1,
        snapshot(brief, brief_text="Volcanoes v2."))
    session.commit()
    _approve(factory, "lesson", lesson_v2.id, teacher.id)
    publish_lesson_version(factory, lesson_v2.id, teacher.id, "Live.")
    ids["lesson_live_id"] = lesson_v2.id

    lesson_v3 = add_lesson_version(
        3, "Adds the labeling challenge for slow readers.", stage_v2,
        snapshot(brief, steer, brief_text="Volcanoes v3."))
    session.flush()
    ids["lesson_draft_id"] = lesson_v3.id
    return ids


if __name__ == "__main__":
    seed(os.environ.get("DATABASE_URL", DEFAULT_URL))
