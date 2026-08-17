from .model import (
    BlogRequestChat,
    BlogRequestDetail,
    BlogRequestItem,
    BlogRequestListMeta,
    BlogRequestUser,
    BlogResponse,
)
from ...database.firebase import firebase_config
from ...utils.time import to_ist
from firebase_admin import firestore
import asyncio
import logging

logger = logging.getLogger(__name__)

BLOG_REQUEST_COLLECTION = "blog_request"
USER_COLLECTION = "users"
CHAT_COLLECTION = "chats"


class BlogService:
    @staticmethod
    async def get_blog_requests(
        status: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> BlogResponse:

        def sync_get_blog_requests() -> BlogResponse:
            db = firebase_config.db
            if db is None:
                raise ValueError("Firestore is not initialized")

            query = db.collection("blog_request")
            if status:
                query = query.where("status", "==", status)
            total = query.count().get()[0][0].value

            offset = (page - 1) * limit
            page_query = (
                query.order_by("created_at", direction=firestore.Query.DESCENDING)
                .offset(offset)
                .limit(limit)
            )

            rows = [(doc.id, doc.to_dict() or {}) for doc in page_query.stream()]

            user_names = BlogService._fetch_user_names(
                {str(data.get("user_id", "")) for _, data in rows}
            )
            chat_titles = BlogService._fetch_chat_titles(
                {str(data.get("chat_id", "")) for _, data in rows}
            )

            items = []
            for doc_id, data in rows:
                chat_id = str(data.get("chat_id", ""))
                user_id = str(data.get("user_id", ""))
                items.append(
                    BlogRequestItem(
                        id=doc_id,
                        chat_id=chat_id,
                        chat_title=chat_titles.get(chat_id),
                        user_id=user_id,
                        user_name=user_names.get(user_id),
                        order_id=data.get("order_id"),
                        request_id=data.get("request_id"),
                        service_id=data.get("service_id"),
                        service_request_id=data.get("service_request_id"),
                        status=str(data.get("status", "")),
                        created_at=to_ist(data.get("created_at")),
                        updated_at=to_ist(data.get("updated_at")),
                    )
                )

            total_pages = (total + limit - 1) // limit if limit > 0 else 0

            return BlogResponse(
                data=items,
                meta=BlogRequestListMeta(
                    total=total,
                    page=page,
                    limit=limit,
                    total_pages=total_pages,
                ),
            )

        return await asyncio.to_thread(sync_get_blog_requests)

    @staticmethod
    async def get_blog_request_detail(request_id: str) -> BlogRequestDetail | None:
        """
        Return one blog request with its user and chat expanded, or None when
        no request matches. The controller turns None into a 404.
        """

        def sync_get_detail() -> BlogRequestDetail | None:
            db = firebase_config.db
            if db is None:
                raise ValueError("Firestore is not initialized")

            doc_id, data = BlogService._find_blog_request(request_id)
            if data is None:
                return None

            chat_id = str(data.get("chat_id", ""))
            user_id = str(data.get("user_id", ""))

            user = BlogService._build_user_detail(user_id)
            chat = BlogService._build_chat_detail(chat_id)

            return BlogRequestDetail(
                id=doc_id,
                chat_id=chat_id,
                chat_title=chat.title if chat else None,
                user_id=user_id,
                user_name=user.name if user else None,
                order_id=data.get("order_id"),
                request_id=data.get("request_id"),
                service_id=data.get("service_id"),
                service_request_id=data.get("service_request_id"),
                status=str(data.get("status", "")),
                created_at=to_ist(data.get("created_at")),
                updated_at=to_ist(data.get("updated_at")),
                user=user,
                chat=chat,
            )

        return await asyncio.to_thread(sync_get_detail)

    @staticmethod
    def _find_blog_request(request_id: str) -> tuple[str, dict | None]:
        """
        Look the request up by document id first, then fall back to the
        `request_id` field, since the two are not guaranteed to stay identical.
        """
        db = firebase_config.db
        collection = db.collection(BLOG_REQUEST_COLLECTION)

        doc = collection.document(request_id).get()
        if doc.exists:
            return doc.id, (doc.to_dict() or {})

        match = next(
            iter(collection.where("request_id", "==", request_id).limit(1).stream()),
            None,
        )
        if match is not None:
            return match.id, (match.to_dict() or {})

        return request_id, None

    @staticmethod
    def _build_user_detail(user_id: str) -> BlogRequestUser | None:
        if not user_id:
            return None

        try:
            doc = firebase_config.db.collection(USER_COLLECTION).document(user_id).get()
        except Exception as exc:
            logger.warning("Failed to load user %s: %s", user_id, exc)
            return None

        if not doc.exists:
            return None

        data = doc.to_dict() or {}
        return BlogRequestUser(
            id=doc.id,
            name=BlogService._build_user_name(data),
            email=(data.get("email") or "").strip() or None,
            photo_url=data.get("photoURL"),
        )

    @staticmethod
    def _build_chat_detail(chat_id: str) -> BlogRequestChat | None:
        if not chat_id:
            return None

        try:
            doc = firebase_config.db.collection(CHAT_COLLECTION).document(chat_id).get()
        except Exception as exc:
            logger.warning("Failed to load chat %s: %s", chat_id, exc)
            return None

        if not doc.exists:
            return None

        data = doc.to_dict() or {}
        return BlogRequestChat(
            id=doc.id,
            title=(data.get("chat_name") or "").strip() or None,
            location=data.get("location"),
            chat_type=data.get("chat_type"),
            created_at=to_ist(data.get("created_at")),
        )

    @staticmethod
    def _fetch_user_names(user_ids: set[str]) -> dict[str, str]:
        """Map user_id -> display name for the given ids, in one batched read."""
        return BlogService._fetch_labels(
            collection=USER_COLLECTION,
            doc_ids=user_ids,
            label_builder=BlogService._build_user_name,
        )

    @staticmethod
    def _fetch_chat_titles(chat_ids: set[str]) -> dict[str, str]:
        """Map chat_id -> chat name for the given ids, in one batched read."""
        return BlogService._fetch_labels(
            collection=CHAT_COLLECTION,
            doc_ids=chat_ids,
            label_builder=lambda data: (data.get("chat_name") or "").strip() or None,
        )

    @staticmethod
    def _fetch_labels(
        collection: str, doc_ids: set[str], label_builder
    ) -> dict[str, str]:

        ids = {doc_id for doc_id in doc_ids if doc_id}
        if not ids:
            return {}

        db = firebase_config.db
        refs = [db.collection(collection).document(doc_id) for doc_id in ids]

        labels: dict[str, str] = {}
        try:
            for snapshot in db.get_all(refs):
                if not snapshot.exists:
                    continue
                label = label_builder(snapshot.to_dict() or {})
                if label:
                    labels[snapshot.id] = label
        except Exception as exc:
            logger.warning("Failed to load labels from %s: %s", collection, exc)

        return labels

    @staticmethod
    def _build_user_name(data: dict) -> str | None:

        first = (data.get("firstName") or "").strip()
        last = (data.get("lastName") or "").strip()

        if first and last and first.lower() != last.lower():
            return f"{first} {last}"

        name = first or last
        if name:
            return name

        email = (data.get("email") or "").strip()
        return email.split("@")[0] or None
