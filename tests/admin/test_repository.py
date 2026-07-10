from unittest.mock import Mock

from app.admin.repository import AdminRepository
from app.models.entities import AuditLog


def test_admin_audit_uses_admin_actor() -> None:
    session = Mock()
    repository = AdminRepository(session)

    repository.add_audit("settings.updated", "Settings updated", {"mode": "OFF"})

    audit = session.add.call_args.args[0]
    assert isinstance(audit, AuditLog)
    assert audit.actor == "admin"
