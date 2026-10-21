import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.connection import Connection, SharingPermission
from app.models.user import User
from app.schemas.connections import ConnectionRequestCreate, SharingPermissionUpdate
from app.routers.connections import (
    accept_connection_request,
    disconnect,
    get_sharing_permissions,
    reject_connection_request,
    send_connection_request,
    sharing_is_allowed,
    update_sharing_permissions,
)
from app.database import Base


class ConnectionFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.owner = User(
            username="owner",
            email="owner@example.com",
            password_hash="test-hash",
        )
        self.viewer = User(
            username="viewer",
            email="viewer@example.com",
            password_hash="test-hash",
        )
        self.other = User(
            username="other",
            email="other@example.com",
            password_hash="test-hash",
        )
        self.db.add_all([self.owner, self.viewer, self.other])
        self.db.commit()
        self.db.refresh(self.owner)
        self.db.refresh(self.viewer)
        self.db.refresh(self.other)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def accept_connection(self) -> int:
        request = send_connection_request(
            ConnectionRequestCreate(username=self.viewer.username),
            current_user=self.owner,
            db=self.db,
        )
        accept_connection_request(
            request.id,
            current_user=self.viewer,
            db=self.db,
        )
        return request.id

    def test_duplicate_request_and_self_connection_are_rejected(self) -> None:
        send_connection_request(
            ConnectionRequestCreate(username=self.viewer.username),
            current_user=self.owner,
            db=self.db,
        )
        with self.assertRaises(HTTPException) as duplicate:
            send_connection_request(
                ConnectionRequestCreate(username=self.owner.username),
                current_user=self.viewer,
                db=self.db,
            )
        self.assertEqual(duplicate.exception.status_code, 409)

        with self.assertRaises(HTTPException) as self_request:
            send_connection_request(
                ConnectionRequestCreate(username=self.owner.username),
                current_user=self.owner,
                db=self.db,
            )
        self.assertEqual(self_request.exception.status_code, 400)

    def test_accept_creates_two_independent_default_off_permissions(self) -> None:
        connection_id = self.accept_connection()
        permissions = self.db.scalars(
            select(SharingPermission).where(
                SharingPermission.connection_id == connection_id
            )
        ).all()

        self.assertEqual(len(permissions), 2)
        self.assertFalse(any(permission.share_location for permission in permissions))
        self.assertFalse(any(permission.share_app_usage for permission in permissions))
        self.assertFalse(
            any(permission.share_restriction_alerts for permission in permissions)
        )
        self.assertFalse(
            sharing_is_allowed(self.db, connection_id, self.owner.id, "location")
        )

    def test_each_owner_controls_only_their_own_sharing(self) -> None:
        connection_id = self.accept_connection()
        permissions = update_sharing_permissions(
            connection_id,
            SharingPermissionUpdate(share_location=True, share_app_usage=True),
            current_user=self.owner,
            db=self.db,
        )
        self.assertTrue(permissions.share_location)
        self.assertTrue(
            sharing_is_allowed(self.db, connection_id, self.owner.id, "location")
        )
        self.assertFalse(
            sharing_is_allowed(self.db, connection_id, self.viewer.id, "location")
        )

        update_sharing_permissions(
            connection_id,
            SharingPermissionUpdate(paused=True),
            current_user=self.owner,
            db=self.db,
        )
        self.assertFalse(
            sharing_is_allowed(self.db, connection_id, self.owner.id, "location")
        )

        update_sharing_permissions(
            connection_id,
            SharingPermissionUpdate(paused=False, share_location=False),
            current_user=self.owner,
            db=self.db,
        )
        self.assertFalse(
            sharing_is_allowed(self.db, connection_id, self.owner.id, "location")
        )

    def test_nonparticipant_cannot_read_or_change_permissions(self) -> None:
        connection_id = self.accept_connection()
        with self.assertRaises(HTTPException) as read_error:
            get_sharing_permissions(
                connection_id,
                current_user=self.other,
                db=self.db,
            )
        self.assertEqual(read_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as update_error:
            update_sharing_permissions(
                connection_id,
                SharingPermissionUpdate(share_location=True),
                current_user=self.other,
                db=self.db,
            )
        self.assertEqual(update_error.exception.status_code, 404)

    def test_only_recipient_can_accept_and_reject(self) -> None:
        request = send_connection_request(
            ConnectionRequestCreate(username=self.viewer.username),
            current_user=self.owner,
            db=self.db,
        )
        with self.assertRaises(HTTPException) as error:
            accept_connection_request(
                request.id,
                current_user=self.owner,
                db=self.db,
            )
        self.assertEqual(error.exception.status_code, 404)
        rejected = reject_connection_request(
            request.id,
            current_user=self.viewer,
            db=self.db,
        )
        self.assertEqual(rejected.status, "rejected")

    def test_disconnect_immediately_revokes_all_categories(self) -> None:
        connection_id = self.accept_connection()
        update_sharing_permissions(
            connection_id,
            SharingPermissionUpdate(
                share_location=True,
                share_app_usage=True,
                share_restriction_alerts=True,
            ),
            current_user=self.owner,
            db=self.db,
        )
        disconnect(connection_id, current_user=self.viewer, db=self.db)

        connection = self.db.get(Connection, connection_id)
        self.assertEqual(connection.status, "disconnected")
        for category in ("location", "app_usage", "restriction_alerts"):
            self.assertFalse(
                sharing_is_allowed(self.db, connection_id, self.owner.id, category)
            )


if __name__ == "__main__":
    unittest.main()
