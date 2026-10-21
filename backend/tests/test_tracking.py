import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.connection import Connection, SharingPermission
from app.models.tracking import (
    AppActivityEvent,
    LocationUpdate,
    RestrictedApp,
    RestrictionAlert,
)
from app.models.user import User
from app.routers.tracking import (
    create_activity,
    create_location,
    create_restriction_alert,
    get_my_activities,
    get_my_locations,
    get_my_restricted_apps,
    get_shared_activities,
    get_shared_locations,
    get_shared_restriction_alerts,
    update_my_restricted_apps,
)
from app.schemas.tracking import (
    ActivityCreate,
    LocationCreate,
    RestrictedAppEntry,
    RestrictedAppsUpdate,
    RestrictionAlertCreate,
)


class TrackingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
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
        self.connection = Connection(
            first_user_id=self.owner.id,
            second_user_id=self.viewer.id,
            requester_id=self.owner.id,
            recipient_id=self.viewer.id,
            status="accepted",
        )
        self.db.add(self.connection)
        self.db.commit()
        self.db.refresh(self.connection)
        self.owner_permission = SharingPermission(
            connection_id=self.connection.id,
            owner_id=self.owner.id,
            share_location=False,
            share_app_usage=False,
            share_restriction_alerts=False,
            paused=False,
        )
        self.db.add(self.owner_permission)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_location_create_and_owner_history(self) -> None:
        record = create_location(
            LocationCreate(
                latitude=37.4219983,
                longitude=-122.084,
                accuracy_meters=8,
                recorded_at=datetime.now(timezone.utc),
            ),
            current_user=self.owner,
            db=self.db,
        )

        rows = get_my_locations(limit=50, current_user=self.owner, db=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, record.id)
        self.assertEqual(rows[0].latitude, 37.4219983)
        self.assertEqual(
            get_my_locations(limit=50, current_user=self.viewer, db=self.db),
            [],
        )

    def test_location_share_requires_owner_consent_and_revokes_immediately(self) -> None:
        create_location(
            LocationCreate(latitude=37.4, longitude=-122.0),
            current_user=self.owner,
            db=self.db,
        )

        with self.assertRaises(HTTPException) as denied:
            get_shared_locations(
                self.connection.id,
                limit=50,
                current_user=self.viewer,
                db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)

        self.owner_permission.share_location = True
        self.db.commit()
        self.assertEqual(
            len(
                get_shared_locations(
                    self.connection.id,
                    limit=50,
                    current_user=self.viewer,
                    db=self.db,
                )
            ),
            1,
        )

        self.owner_permission.paused = True
        self.db.commit()
        with self.assertRaises(HTTPException) as paused:
            get_shared_locations(
                self.connection.id,
                limit=50,
                current_user=self.viewer,
                db=self.db,
            )
        self.assertEqual(paused.exception.status_code, 403)

    def test_unrelated_user_cannot_read_shared_location(self) -> None:
        with self.assertRaises(HTTPException) as denied:
            get_shared_locations(
                self.connection.id,
                current_user=self.other,
                db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 404)

    def test_activity_round_trip_is_owner_scoped_and_consent_gated(self) -> None:
        create_activity(
            ActivityCreate(
                package_name="org.example.reader",
                app_name="Reader",
                event_type="opened",
            ),
            current_user=self.owner,
            db=self.db,
        )
        self.assertEqual(
            len(get_my_activities(limit=50, current_user=self.owner, db=self.db)),
            1,
        )

        with self.assertRaises(HTTPException) as denied:
            get_shared_activities(
                self.connection.id,
                limit=50,
                current_user=self.viewer,
                db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)

        self.owner_permission.share_app_usage = True
        self.db.commit()
        self.assertEqual(
            len(
                get_shared_activities(
                    self.connection.id,
                    limit=50,
                    current_user=self.viewer,
                    db=self.db,
                )
            ),
            1,
        )

    def test_restricted_apps_replace_owner_selection(self) -> None:
        update_my_restricted_apps(
            RestrictedAppsUpdate(
                apps=[
                    RestrictedAppEntry(
                        package_name="org.example.game",
                        app_name="Game",
                    )
                ]
            ),
            current_user=self.owner,
            db=self.db,
        )
        self.assertEqual(
            [app.package_name for app in get_my_restricted_apps(
                current_user=self.owner,
                db=self.db,
            )],
            ["org.example.game"],
        )
        self.assertEqual(
            get_my_restricted_apps(current_user=self.viewer, db=self.db),
            [],
        )

    def test_restriction_alert_sharing_requires_consent(self) -> None:
        create_restriction_alert(
            RestrictionAlertCreate(
                package_name="org.example.game",
                app_name="Game",
                details="Owner-reported alert",
            ),
            current_user=self.owner,
            db=self.db,
        )
        self.assertEqual(
            self.db.query(RestrictionAlert).count(),
            1,
        )
        with self.assertRaises(HTTPException) as denied:
            get_shared_restriction_alerts(
                self.connection.id,
                limit=50,
                current_user=self.viewer,
                db=self.db,
            )
        self.assertEqual(denied.exception.status_code, 403)

        self.owner_permission.share_restriction_alerts = True
        self.db.commit()
        self.assertEqual(
            len(
                get_shared_restriction_alerts(
                    self.connection.id,
                    limit=50,
                    current_user=self.viewer,
                    db=self.db,
                )
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
