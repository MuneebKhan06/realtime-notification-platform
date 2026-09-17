import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Notification, ReadReceipt


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
        type_: str,
        payload: dict,
    ) -> Notification | None:
        """Insert a notification, treating a duplicate notification_id as a no-op.

        Returns the inserted row, or None if it already existed.
        """
        stmt = (
            pg_insert(Notification)
            .values(
                notification_id=notification_id,
                user_id=user_id,
                type=type_,
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=["notification_id"])
            .returning(Notification)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.scalar_one_or_none()

    async def mark_delivered_live(self, notification_id: uuid.UUID) -> None:
        stmt = (
            update(Notification)
            .where(Notification.notification_id == notification_id)
            .values(delivered_live=True)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID, read_at: datetime
    ) -> bool:
        """Marks a notification as read and records a read receipt for it.

        Scoped to the calling user_id as well as notification_id: without
        that check, any connected client could mark an arbitrary
        notification_id as read and pollute a different user's unread
        backlog, since notification_id alone is not a secret.

        Both writes happen in one transaction: the notification's read_at is
        the fast-path check used by the unread backlog query, while the
        read_receipts row is the durable, per-user audit trail of when it
        was acknowledged. The read_receipts row is only written if the
        notification actually belongs to this user.

        Returns whether a matching notification was found and marked read.
        """
        update_stmt = (
            update(Notification)
            .where(
                Notification.notification_id == notification_id,
                Notification.user_id == user_id,
            )
            .values(read_at=read_at)
        )
        result = await self._session.execute(update_stmt)

        if result.rowcount == 0:
            await self._session.commit()
            return False

        insert_stmt = pg_insert(ReadReceipt).values(
            notification_id=notification_id,
            user_id=user_id,
            read_at=read_at,
        )
        await self._session.execute(insert_stmt)

        await self._session.commit()
        return True

    async def get_unread_backlog(self, user_id: uuid.UUID, limit: int) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .order_by(Notification.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_history(
        self,
        user_id: uuid.UUID,
        limit: int,
        before: datetime | None = None,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        if before is not None:
            stmt = stmt.where(Notification.created_at < before)
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_read_receipts(self, notification_id: uuid.UUID) -> list[ReadReceipt]:
        stmt = (
            select(ReadReceipt)
            .where(ReadReceipt.notification_id == notification_id)
            .order_by(ReadReceipt.read_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
