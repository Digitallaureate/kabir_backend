from .model import (
    BlogDraft,
    BlogRequestChat,
    BlogRequestDetail,
    BlogRequestItem,
    BlogRequestListMeta,
    BlogRequestMedia,
    BlogRequestMessage,
    BlogRequestUser,
    BlogResponse,
    CreateBlogRequest,
    CreateBlogResponse,
)
from ...config.settings import settings
from ...database.firebase import firebase_config
from ...utils.openai_client import call_chat_completions, extract_message_content
from ...utils.time import to_ist
from datetime import datetime, timezone
from firebase_admin import firestore
import asyncio
import json
import logging
import re
import secrets
import string

logger = logging.getLogger(__name__)

BLOG_REQUEST_COLLECTION = "blog_request"
USER_COLLECTION = "users"
CHAT_COLLECTION = "chats"
MESSAGE_SUBCOLLECTION = "messages"

# Messages were written by two different code paths, so the media URL lives
# under either key (see chat/service.py). Check both.
MEDIA_URL_FIELDS = ("image_url", "imageUrl")

# Firebase Storage paths / extensions that mean the asset is a video.
VIDEO_MARKERS = ("videoasset", ".mp4", ".mov", ".webm", ".m4v")

BLOG_COLLECTION = "blogs"

# Form limits, mirrored from the admin blog form.
TITLE_MAX = 100
EXCERPT_MAX = 200
SEO_TITLE_MAX = 60
META_DESCRIPTION_MAX = 160

WORDS_PER_MINUTE = 200

# Public site the blogs are published to, used to build blogUrl.
BLOG_SITE_URL = "https://www.kabir-ai.com/blogs"

# blog_request.status once a blog has been created from it.
STATUS_DRAFT = "in_progress"
STATUS_PUBLISHED = "published"

# Editor.js document settings, matching what the site's editor produces.
EDITORJS_VERSION = "2.31.0-rc.7"
BLOCK_ID_ALPHABET = string.ascii_letters + string.digits + "-_"

# Only these are asked of the model. author / category / featured stay with the
# admin, and slug / readTime are derived in code so they are correct by
# construction.
DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": f"Blog title, max {TITLE_MAX} chars"},
        "excerpt": {
            "type": "string",
            "description": f"Short summary for listings, max {EXCERPT_MAX} chars",
        },
        "blocks": {
            "type": "array",
            "description": (
                "The post body as an ordered list of blocks. Interleave images "
                "between paragraphs so the story flows."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["header", "paragraph", "image"],
                    },
                    "text": {
                        "type": ["string", "null"],
                        "description": "Text for header/paragraph blocks, null for image blocks",
                    },
                    "level": {
                        "type": ["integer", "null"],
                        "description": "Heading level 2 or 3, null unless type is header",
                    },
                    "media_index": {
                        "type": ["integer", "null"],
                        "description": "Index into the supplied media list, only for image blocks",
                    },
                },
                "required": ["type", "text", "level", "media_index"],
                "additionalProperties": False,
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "seo_title": {"type": "string", "description": f"Max {SEO_TITLE_MAX} chars"},
        "meta_description": {
            "type": "string",
            "description": f"Max {META_DESCRIPTION_MAX} chars",
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
        "hero_image_index": {
            "type": ["integer", "null"],
            "description": "Index of the best hero image from the supplied media list, or null",
        },
    },
    "required": [
        "title",
        "excerpt",
        "blocks",
        "tags",
        "seo_title",
        "meta_description",
        "keywords",
        "hero_image_index",
    ],
    "additionalProperties": False,
}


class BlogAlreadyExists(Exception):
    """Raised when a blog has already been created for a request."""


class BlogService:
    @staticmethod
    async def create_blog(
        request_id: str, body: CreateBlogRequest
    ) -> CreateBlogResponse | None:
        """
        Write the reviewed blog into the `blogs` collection and move the
        originating request forward.

        Returns None when the request does not exist, so the controller can
        answer 404. Raises BlogAlreadyExists if this request already produced a
        blog, which stops a double-clicked Publish button creating duplicates.
        """

        def sync_create_blog() -> CreateBlogResponse | None:
            db = firebase_config.db
            if db is None:
                raise ValueError("Firestore is not initialized")

            doc_id, request_data = BlogService._find_blog_request(request_id)
            if request_data is None:
                return None

            existing_blog_id = request_data.get("blog_id")
            if existing_blog_id:
                raise BlogAlreadyExists(
                    f"A blog ({existing_blog_id}) already exists for this request"
                )

            publishing = body.status == "published"
            if publishing:
                BlogService._validate_publishable(body)

            chat_id = str(request_data.get("chat_id", ""))
            chat = BlogService._build_chat_detail(chat_id)

            # The slug is the public URL, so re-check uniqueness here: the admin
            # may have edited the one suggested in the draft.
            slug = BlogService._unique_slug(body.slug or body.title)
            if not slug:
                raise ValueError("Could not build a slug from the title")

            now = BlogService._now_iso()
            blog_ref = db.collection(BLOG_COLLECTION).document()

            # The blogs collection keeps exactly these fields, nothing more.
            blog_data = {
                "uid": str(request_data.get("user_id", "")),
                "blogUrl": f"{BLOG_SITE_URL}/{slug}",
                "chatId": chat_id,
                "chatName": (chat.title if chat else None) or "",
                "excerpt": body.excerpt,
                "heroImage": body.heroImage,
                "publishDate": now if publishing else None,
                "readTime": body.readTime or BlogService._read_time_from_json(body.content),
                "slug": slug,
                "title": body.title,
            }
            blog_ref.set(blog_data)

            db.collection(BLOG_REQUEST_COLLECTION).document(doc_id).update(
                {
                    "status": STATUS_PUBLISHED if publishing else STATUS_DRAFT,
                    "blog_id": blog_ref.id,
                    "updated_at": now,
                }
            )

            return CreateBlogResponse(
                id=blog_ref.id,
                slug=slug,
                title=body.title,
                status=body.status,
                blogUrl=blog_data["blogUrl"],
                publishDate=blog_data["publishDate"],
                requestId=request_data.get("request_id") or doc_id,
            )

        return await asyncio.to_thread(sync_create_blog)

    @staticmethod
    def _validate_publishable(body: CreateBlogRequest) -> None:
        """Enforce the fields the admin form marks as required, on publish only."""
        missing = [
            name
            for name, value in (
                ("title", body.title),
                ("excerpt", body.excerpt),
                ("content", body.content),
                ("author", body.author),
                ("category", body.category),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise ValueError(
                f"Cannot publish, these fields are required: {', '.join(missing)}"
            )

    @staticmethod
    def _now_iso() -> str:
        """Timestamp in the format the blogs collection already uses."""
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _read_time_from_json(content: str | None) -> int:
        """Read time from an Editor.js document that arrives as a JSON string."""
        if not content:
            return 1
        try:
            return BlogService._read_time(json.loads(content))
        except (ValueError, TypeError):
            return 1

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
    async def get_blog_request_detail(
        request_id: str, message_limit: int = 30
    ) -> BlogRequestDetail | None:
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
            messages = BlogService._fetch_chat_messages(chat_id, limit=message_limit)
            media = BlogService._extract_media(messages)

            draft, draft_error = BlogService._generate_draft(
                messages=messages,
                media=media,
                chat=chat,
                author=user.name if user else None,
            )

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
                draft=draft,
                draft_error=draft_error,
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
    def _generate_draft(
        messages: list[BlogRequestMessage],
        media: list[BlogRequestMedia],
        chat: BlogRequestChat | None,
        author: str | None = None,
    ) -> tuple[BlogDraft | None, str | None]:
        """
        Ask OpenAI to draft the blog form fields from the conversation.

        Returns (draft, error). A failure here never breaks the endpoint — the
        admin still gets the request, the chat and the media, and can write the
        post by hand.
        """
        if not messages:
            return None, "No chat messages available to generate a draft from"

        try:
            payload = {
                "model": settings.OPENAI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a travel editor. Write a blog post from a traveller's "
                            "own chat conversation about a place they visited.\n"
                            "Rules:\n"
                            "- Use only what the conversation actually says. Never invent "
                            "facts, prices, dates or events.\n"
                            "- Write the body in first person, as the traveller.\n"
                            "- Prefer the traveller's own photos and words over the "
                            "assistant's reference material.\n"
                            f"- title <= {TITLE_MAX} chars, excerpt <= {EXCERPT_MAX}, "
                            f"seo_title <= {SEO_TITLE_MAX}, meta_description <= "
                            f"{META_DESCRIPTION_MAX}.\n"
                            "- Build the body as blocks: headers, paragraphs, and images "
                            "interleaved so the images illustrate the text next to them.\n"
                            "- Put a paragraph before an image that sets it up, the way a "
                            "travel story reads. Do not stack images with no text between.\n"
                            "- For an image block set media_index to an item from the media "
                            "list and leave text null. Never write a URL yourself.\n"
                            "- Use each image at most once, and only images, never videos. "
                            "If a video matters, describe it in a paragraph instead.\n"
                            "- Write in markdown-free plain text; the blocks carry structure."
                        ),
                    },
                    {
                        "role": "user",
                        "content": BlogService._build_generation_prompt(messages, media, chat),
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "blog_draft",
                        "strict": True,
                        "schema": DRAFT_SCHEMA,
                    },
                },
                "temperature": 0.7,
            }

            response = call_chat_completions(payload)
            raw = extract_message_content(response)
            if not raw:
                return None, "OpenAI returned an empty response"

            generated = json.loads(raw)
        except Exception as exc:
            logger.error("Blog draft generation failed: %s", exc)
            return None, f"Draft generation failed: {exc}"

        return BlogService._build_draft(generated, media, author=author), None

    @staticmethod
    def _build_generation_prompt(
        messages: list[BlogRequestMessage],
        media: list[BlogRequestMedia],
        chat: BlogRequestChat | None,
    ) -> str:
        """Render the conversation and the numbered media list for the model."""
        lines: list[str] = []

        if chat:
            lines.append(f"Chat title: {chat.title or 'unknown'}")
            lines.append(f"Location: {chat.location or 'unknown'}")
        lines.append("")
        lines.append("Conversation (oldest first):")

        for message in messages:
            role = message.role or "unknown"
            text = message.content or ""
            attachment = ""
            if message.media_url:
                attachment = f" [{message.media_type or 'image'} attached]"
            lines.append(f"- {role}{attachment}: {text}")

        lines.append("")
        lines.append(
            "Available media (choose hero_image_index from this list, or null). "
            "Photos marked 'user' were taken by the traveller and are preferred:"
        )
        for index, item in enumerate(media):
            lines.append(
                f"  [{index}] {item.type} by {item.role or 'unknown'} — "
                f"{item.caption or 'no caption'}"
            )

        return "\n".join(lines)

    @staticmethod
    def _build_draft(
        generated: dict,
        media: list[BlogRequestMedia],
        author: str | None = None,
    ) -> BlogDraft:
        """
        Turn the model's JSON into form values: trim to the form's limits,
        derive slug and read time in code, and resolve the hero image to a URL
        the conversation actually contains.
        """
        title = BlogService._trim(generated.get("title"), TITLE_MAX)
        content_doc = BlogService._build_editorjs_content(generated.get("blocks"), media)
        # Stored as a compact JSON string, matching the site's editor output.
        content = (
            json.dumps(content_doc, separators=(",", ":"), ensure_ascii=False)
            if content_doc
            else None
        )
        

        hero_image = None
        index = generated.get("hero_image_index")
        if isinstance(index, int) and 0 <= index < len(media):
            hero_image = media[index].url

        # Fall back to the traveller's own first photo rather than leaving the
        # hero empty or using assistant reference artwork.
        if hero_image is None:
            hero_image = next(
                (m.url for m in media if m.type == "image" and m.role == "user"),
                next((m.url for m in media if m.type == "image"), None),
            )

        gallery = [m.url for m in media if m.type == "image" and m.role == "user"]
        gallery += [m.url for m in media if m.type == "image" and m.role != "user"]

        return BlogDraft(
            title=title,
            slug=BlogService._unique_slug(title),
            excerpt=BlogService._trim(generated.get("excerpt"), EXCERPT_MAX),
            heroImage=hero_image,
            content=content,
            mediaGallery=gallery,
            # The traveller whose chat this blog is written from.
            author=author,
            tags=BlogService._string_list(generated.get("tags")),
            seoTitle=BlogService._trim(generated.get("seo_title"), SEO_TITLE_MAX),
            metaDescription=BlogService._trim(
                generated.get("meta_description"), META_DESCRIPTION_MAX
            ),
            keywords=BlogService._string_list(generated.get("keywords")),
            readTime=BlogService._read_time(content_doc),
        )

    @staticmethod
    def _build_editorjs_content(blocks, media: list[BlogRequestMedia]) -> dict | None:
        """
        Turn the model's block list into an Editor.js document.

        Image URLs are resolved here from `media_index`, so the post can only
        ever contain images the conversation actually has. An index that is out
        of range, points at a video, or repeats an already-used image is
        dropped rather than rendered as a broken block.
        """
        if not isinstance(blocks, list) or not blocks:
            return None

        editor_blocks: list[dict] = []
        used_indexes: set[int] = set()

        for block in blocks:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type")

            if block_type == "image":
                index = block.get("media_index")
                if not isinstance(index, int) or not 0 <= index < len(media):
                    continue
                if index in used_indexes or media[index].type != "image":
                    continue

                used_indexes.add(index)
                editor_blocks.append(
                    {
                        "id": BlogService._block_id(),
                        "type": "image",
                        "data": {
                            "caption": "",
                            "withBorder": False,
                            "withBackground": False,
                            "stretched": False,
                            "file": {"url": media[index].url},
                        },
                    }
                )
                continue

            text = (block.get("text") or "").strip()
            if not text:
                continue

            if block_type == "header":
                level = block.get("level")
                editor_blocks.append(
                    {
                        "id": BlogService._block_id(),
                        "type": "header",
                        "data": {
                            "text": text,
                            "level": level if level in (2, 3) else 2,
                        },
                    }
                )
            else:
                editor_blocks.append(
                    {
                        "id": BlogService._block_id(),
                        "type": "paragraph",
                        "data": {"text": text},
                    }
                )

        if not editor_blocks:
            return None

        return {
            "time": int(datetime.now(timezone.utc).timestamp() * 1000),
            "blocks": editor_blocks,
            "version": EDITORJS_VERSION,
        }

    @staticmethod
    def _block_id() -> str:
        """Editor.js block id: 10 chars from its own alphabet."""
        return "".join(secrets.choice(BLOCK_ID_ALPHABET) for _ in range(10))

    @staticmethod
    def _trim(value, max_length: int) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        return text if len(text) <= max_length else text[:max_length].rstrip()

    @staticmethod
    def _string_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _read_time(content: dict | None) -> int:
        """Estimate reading minutes from the text blocks only."""
        if not content:
            return 1

        words = sum(
            len((block.get("data") or {}).get("text", "").split())
            for block in content.get("blocks", [])
            if block.get("type") in ("paragraph", "header")
        )
        return max(1, round(words / WORDS_PER_MINUTE)) or 1

    @staticmethod
    def _slugify(title: str | None) -> str | None:
        if not title:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or None

    @staticmethod
    def _unique_slug(title: str | None) -> str | None:
        """
        Slugify the title and make sure no published blog already uses it,
        since the slug becomes the public URL.
        """
        base = BlogService._slugify(title)
        if not base:
            return None

        try:
            collection = firebase_config.db.collection(BLOG_COLLECTION)
            candidate = base
            suffix = 2
            while next(
                iter(collection.where("slug", "==", candidate).limit(1).stream()), None
            ):
                candidate = f"{base}-{suffix}"
                suffix += 1
            return candidate
        except Exception as exc:
            logger.warning("Slug uniqueness check failed for %r: %s", base, exc)
            return base

    @staticmethod
    def _fetch_chat_messages(chat_id: str, limit: int = 30) -> list[BlogRequestMessage]:
        """
        Return the most recent `limit` messages of a chat in chronological
        order (oldest first), which is the order a blog is written in.

        Firestore is asked for the NEWEST messages, then the page is reversed,
        so a long conversation gives back its tail rather than its start.
        """
        if not chat_id:
            return []

        try:
            query = (
                firebase_config.db.collection(CHAT_COLLECTION)
                .document(chat_id)
                .collection(MESSAGE_SUBCOLLECTION)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = list(query.stream())
        except Exception as exc:
            logger.warning("Failed to load messages for chat %s: %s", chat_id, exc)
            return []

        docs.reverse()

        messages: list[BlogRequestMessage] = []
        for doc in docs:
            data = doc.to_dict() or {}
            media_url = BlogService._media_url(data)
            content = (data.get("content") or "").strip() or None

            messages.append(
                BlogRequestMessage(
                    id=doc.id,
                    role=data.get("role"),
                    user_id=data.get("user_id"),
                    content=content,
                    media_url=media_url,
                    media_type=BlogService._media_type(media_url),
                    created_at=to_ist(data.get("created_at")),
                )
            )

        return messages

    @staticmethod
    def _media_url(data: dict) -> str | None:
        """Read the attachment URL from whichever field name it was saved under."""
        for field in MEDIA_URL_FIELDS:
            url = (data.get(field) or "").strip()
            if url:
                return url
        return None

    @staticmethod
    def _media_type(url: str | None) -> str | None:
        """Classify an attachment as video or image; some are drone footage."""
        if not url:
            return None

        lowered = url.lower()
        return "video" if any(m in lowered for m in VIDEO_MARKERS) else "image"

    @staticmethod
    def _extract_media(messages: list[BlogRequestMessage]) -> list[BlogRequestMedia]:
        """
        Flat list of the conversation's attachments, each keeping the text of
        its own message as the caption.
        """
        return [
            BlogRequestMedia(
                url=message.media_url,
                type=message.media_type or "image",
                caption=message.content,
                role=message.role,
                created_at=message.created_at,
            )
            for message in messages
            if message.media_url
        ]

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
