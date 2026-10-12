"""Backfill F1/F2/F3 fields and import legacy submissions.

Migration strategy for existing rows:

* ``type`` / ``priority`` use the model defaults (``Task`` / ``P2``) added in 0003.
* ``reviewer`` is backfilled with the mission creator (the old acceptance rule).
* Every ``Submitted`` / ``Done`` mission gets one ``is_legacy`` submission so the
  historical ``result`` text is preserved without fabricating source/build
  evidence or a reviewer identity / review time.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Mission = apps.get_model("missions", "Mission")
    MissionSubmission = apps.get_model("missions", "MissionSubmission")

    for mission in Mission.objects.all().iterator():
        changed = []
        if mission.reviewer_id is None:
            mission.reviewer_id = mission.creator_id
            changed.append("reviewer")
        if mission.status in ("Submitted", "Done") and mission.current_submission_id is None:
            submission = MissionSubmission.objects.create(
                mission_id=mission.id,
                submitted_by_id=mission.assignee_id or mission.creator_id,
                description=mission.result or "",
                verification_description="",
                is_legacy=True,
                reviewer_snapshot_id=mission.creator_id,
                outcome="Accepted" if mission.status == "Done" else "Pending",
                reviewed_by_id=None,
                reviewed_at=None,
                review_comment="",
            )
            mission.current_submission_id = submission.id
            changed.append("current_submission")
        if changed:
            mission.save(update_fields=changed)


def unbackfill(apps, schema_editor):
    Mission = apps.get_model("missions", "Mission")
    MissionSubmission = apps.get_model("missions", "MissionSubmission")
    MissionSubmission.objects.filter(is_legacy=True).delete()
    Mission.objects.update(reviewer=None, current_submission=None)


class Migration(migrations.Migration):

    dependencies = [
        ("missions", "0003_submissionbuildreference_submissionsourcereference_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
