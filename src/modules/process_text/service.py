from typing import Optional, Dict, Any, List
from .model import (
    ProcessTextRequest,
    ProcessTextResponse,
    IntentDetectionResult,
    IntentType,
    ImageSearchResult,
    AudioSearchResult,
    VideoSearchResult,
    PineconeSearchResult,
    FirestoreMessage,
)
from ...config.settings import settings
import openai
import os
import time
import json
import asyncio
from datetime import datetime
from pinecone import Pinecone
from firebase_admin import firestore  # for Query.DESCENDING
from ...database.firebase import firebase_config


class ProcessTextService:
    # 🚀 CLASS-LEVEL CLIENTS FOR REUSE (MAJOR PERFORMANCE BOOST)
    _openai_client = None
    _pinecone_clients: Dict[str, Any] = {}
    _env_vars: Optional[Dict[str, str]] = None

    # ---------- SHARED CLIENTS / ENV ----------

    @classmethod
    def get_openai_client(cls):
        """Get reusable OpenAI client"""
        if cls._openai_client is None:
            cls._openai_client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY
            )
        return cls._openai_client

    @classmethod
    def get_pinecone_index(cls, index_name: str, host: str):
        """Get reusable Pinecone index"""
        key = f"{index_name}_{host}"
        if key not in cls._pinecone_clients:
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            cls._pinecone_clients[key] = pc.Index(name=index_name, host=host)
        return cls._pinecone_clients[key]

    @classmethod
    def get_env_vars(cls):
        """Cache environment variables"""
        if cls._env_vars is None:
            cls._env_vars = {
                "PINECONE_API_KEY": settings.PINECONE_API_KEY,
                "PINECONE_INDEX_NAME": settings.PINECONE_INDEX_NAME,
                "PINECONE_INDEX_HOST": settings.PINECONE_INDEX_HOST,
                "PINECONE_INDEX_NAME2": settings.PINECONE_INDEX_NAME2,
                "PINECONE_INDEX_HOST2": settings.PINECONE_INDEX_HOST2,
                "PINECONE_INDEX_NAME3": settings.PINECONE_INDEX_NAME3,
                "PINECONE_INDEX_HOST3": settings.PINECONE_INDEX_HOST3,
            }
        return cls._env_vars

    # ---------- UTIL: CHAT HISTORY ----------

    @staticmethod
    async def _get_last_messages(chat_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Fetch last N messages from Firestore for this chat (oldest → newest).

        Used for:
        - router (intent + semantic_query) → up to last 9 messages
        - caption formatter → recent context
        """

        def sync_fetch():
            messages_ref = (
                firebase_config.db.collection("chats")
                .document(chat_id)
                .collection("messages")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = messages_ref.get()

            history: List[Dict[str, str]] = []
            for doc in docs:
                data = doc.to_dict() or {}
                history.append(
                    {
                        "role": data.get("role", "user"),
                        "content": data.get("content", ""),
                    }
                )
            # Firestore returns newest first (DESCENDING), so reverse to oldest→newest
            history.reverse()
            return history

        return await asyncio.to_thread(sync_fetch)

    # ---------- MAIN ENTRY ----------

    @staticmethod
    async def process_user_content(request: ProcessTextRequest) -> ProcessTextResponse:
        """Main processing function with parallel optimizations"""
        overall_start = time.time()

        try:
            print(
                f"🚀 Starting process_user_content for: {request.content[:50]}..."
            )

            # 🚀 PARALLEL EXECUTION: Intent detection (router) + Chat verification
            intent_start = time.time()

            intent_task = ProcessTextService.detect_intent(request)
            chat_verification_task = asyncio.create_task(
                ProcessTextService._verify_chat_exists(request.chatId)
            )

            # Wait for both to complete
            intent_result, chat_exists = await asyncio.gather(
                intent_task, chat_verification_task
            )

            intent_time = int((time.time() - intent_start) * 1000)
            print(f"⏱️ Intent detection + chat verification took: {intent_time}ms")

            if not chat_exists:
                raise Exception(f"Chat ID '{request.chatId}' not found in Firestore")

            # Step 2: Route to appropriate function based on intent
            search_start = time.time()
            function_result = await ProcessTextService.route_to_function(
                intent_result, request
            )
            search_time = int((time.time() - search_start) * 1000)
            print(f"⏱️ Search function took: {search_time}ms")

            total_time = int((time.time() - overall_start) * 1000)
            print(f"⏱️ Total process_user_content took: {total_time}ms")

            return ProcessTextResponse(
                success=True,
                intent=intent_result,
                result=function_result,
                error_message=None,
                total_processing_time_ms=total_time,
            )

        except Exception as e:
            total_time = int((time.time() - overall_start) * 1000)
            print(
                f"❌ Error in process_user_content after {total_time}ms: {str(e)}"
            )

            error_result = ImageSearchResult(
                message="Error in processing",
                firestore_message=await ProcessTextService._save_error_message(
                    request, str(e)
                ),
                search_metadata=PineconeSearchResult(
                    score=0.0,
                    content=f"Sorry, I encountered an error: {str(e)}",
                    metadata={},
                ),
            )

            return ProcessTextResponse(
                success=False,
                intent=IntentDetectionResult(
                    detected_intent=IntentType.NONE,
                    confidence=0.0,
                    reasoning="Error in processing, defaulted to none",
                    processing_time_ms=0,
                    semantic_query=None,
                ),
                result=error_result,
                error_message=str(e),
                total_processing_time_ms=total_time,
            )

    # ---------- UTIL: CHAT EXISTS ----------

    @staticmethod
    async def _verify_chat_exists(chat_id: str) -> bool:
        """Verify chat exists in Firestore (async wrapped)"""
        try:
            def sync_check():
                chat_doc_ref = firebase_config.db.collection("chats").document(
                    chat_id
                )
                return chat_doc_ref.get().exists

            return await asyncio.to_thread(sync_check)
        except Exception as e:
            print(f"❌ Chat verification error: {str(e)}")
            return False

    # ---------- INTENT + SEMANTIC QUERY ROUTER ----------

    @staticmethod
    async def detect_intent(request: ProcessTextRequest) -> IntentDetectionResult:
        """
        Use router prompt to get:
          - intent: "image" | "video" | "none"
          - semantic_query: short 5-20 word English query.

        Internally map intent → IntentType and expose semantic_query.
        """
        start_time = time.time()

        try:
            print(f"🧠 Starting intent+router detection...")

            openai_start = time.time()
            client = ProcessTextService.get_openai_client()

            # 1) Fetch last 9 messages from this chat for context
            history_messages = await ProcessTextService._get_last_messages(
                request.chatId, limit=9
            )
            print(
                f"🧠 Loaded {len(history_messages)} history messages for router"
            )

            router_system_prompt = """
You are a router for Kabir, the AI travel companion.

Using the last 10 conversation messages, identify:

1) intent → exactly one of:
   - "image" — only if the user last message explicitly asks for a painting, picture, portrait, visual, or image.
   - "video" — only if the user last message explicitly asks for a video, reel, clip, or animation.
   - "none"  — for all other queries, including narration, storytelling, explanation, history, or general chat.
     (All non-image/video requests must map to "none".)

Focus primarily on the LAST user message. Use previous messages only for clarity.

2) semantic_query → a short English search query (5–20 words) that captures:
   - the main subject (e.g., Akbar, Humayun, Shah Jahan, Taj Mahal)
   - optional helpful context (Mughal, painting, portrait, Padshahnamah, history, etc.)

Rules:
- Do NOT include commands like “show me”, “tell me”, “play”, “send”, etc.
- Keep all proper nouns exactly as they are.
- If user message is in non-English, translate meaning to English but preserve all names.

Return ONLY this JSON:

{
  "intent": "<image | video | none>",
  "semantic_query": "<search text>"
}
""".strip()

            # Build messages array as a real conversation
            messages: List[Dict[str, str]] = [
                {"role": "system", "content": router_system_prompt}
            ]

            # Add history (roles/user & assistant)
            for msg in history_messages:
                role = msg.get("role", "user")
                if role not in ("user", "assistant"):
                    role = "user"
                content = (msg.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})

            # Add current user message as last
            messages.append({"role": "user", "content": request.content})

            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=200,
                temperature=0.1,
            )

            openai_time = int((time.time() - openai_start) * 1000)
            print(f"⏱️ OpenAI router call took: {openai_time}ms")

            raw = response.choices[0].message.content.strip()
            print(f"🧠 Raw router JSON: {raw}")

            # Parse JSON safely
            try:
                router_obj = json.loads(raw)
            except Exception as parse_err:
                print(f"⚠️ Router JSON parse failed: {parse_err}")
                # crude fallback: try to extract something
                router_obj = {}

            router_intent_str = (router_obj.get("intent") or "none").strip().lower()
            semantic_query = (router_obj.get("semantic_query") or "").strip()

            # Fallback semantic_query if router returned empty
            if not semantic_query:
                semantic_query = request.content.strip()

            # Map router intent → internal IntentType
            if router_intent_str == "image":
                detected_intent = IntentType.SEARCH_IMAGE
            elif router_intent_str == "video":
                detected_intent = IntentType.SEARCH_VIDEO
            else:
                detected_intent = IntentType.NONE

            processing_time = int((time.time() - start_time) * 1000)
            print(
                f"✅ Router completed: intent={router_intent_str}, "
                f"mapped={detected_intent.value}, semantic_query='{semantic_query}' "
                f"in {processing_time}ms"
            )

            return IntentDetectionResult(
                detected_intent=detected_intent,
                confidence=1.0,  # router doesn't give score; set 1.0 or derive later if needed
                reasoning=f"Router intent={router_intent_str}",
                processing_time_ms=processing_time,
                semantic_query=semantic_query,
            )

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            print(f"❌ Router/intent detection error after {processing_time}ms: {str(e)}")
            # On error, safest is NONE so we do NOT accidentally trigger media search
            return IntentDetectionResult(
                detected_intent=IntentType.NONE,
                confidence=0.0,
                reasoning=f"Error in router/intent detection, defaulted to none: {str(e)}",
                processing_time_ms=processing_time,
                semantic_query=request.content.strip(),
            )

    # ---------- ROUTING ----------

    @staticmethod
    async def route_to_function(
        intent_result: IntentDetectionResult,
        request: ProcessTextRequest,
    ):
        """Route to appropriate function based on detected intent + semantic_query."""
        try:
            intent = intent_result.detected_intent
            semantic_query = (intent_result.semantic_query or request.content).strip()

            print(
                f"🎯 Routing to {intent.value} with semantic_query='{semantic_query[:80]}'..."
            )

            if intent == IntentType.SEARCH_IMAGE:
                return await ProcessTextService.search_image_from_database(
                    request, semantic_query
                )
            elif intent == IntentType.SEARCH_AUDIO:
                # (If you later extend router to support audio, reuse semantic_query here)
                return await ProcessTextService.search_audio_from_database(
                    request, semantic_query
                )
            elif intent == IntentType.SEARCH_VIDEO:
                return await ProcessTextService.search_video_from_database(
                    request, semantic_query
                )
            elif intent == IntentType.NONE:
                # 🛑 Do NOT hit Pinecone or write a new Firestore message
                print("🛑 Intent is NONE – skipping media search and Firestore write.")

                dummy_message = FirestoreMessage(
                    id="none-intent",
                    content=request.content,
                    created_at=datetime.utcnow().isoformat(
                        timespec="milliseconds"
                    ) + "Z",
                    location=request.location,
                    role="assistant",
                    user_id="NoneIntent",
                )

                # Return ImageSearchResult-shaped object so ProcessTextResponse validation passes
                return ImageSearchResult(
                    message="Non-media intent. Media search skipped.",
                    firestore_message=dummy_message,
                    search_metadata=PineconeSearchResult(
                        score=0.0,
                        content="Media search skipped for non-media intent.",
                        metadata={"intent": "none"},
                    ),
                )
            else:
                # safety: unknown enum (should not happen)
                raise ValueError(f"Unsupported intent: {intent}")

        except Exception as e:
            print(f"❌ Error in function routing: {str(e)}")
            return ImageSearchResult(
                message="Error in function routing",
                firestore_message=await ProcessTextService._save_error_message(
                    request, str(e)
                ),
                search_metadata=PineconeSearchResult(
                    score=0.0,
                    content=f"I encountered an error while processing: {str(e)}",
                    metadata={},
                ),
            )

    # ---------- IMAGE SEARCH ----------

    @staticmethod
    async def search_image_from_database(
        request: ProcessTextRequest,
        semantic_query: str,
    ) -> ImageSearchResult:
        """🚀 OPTIMIZED image search using router's semantic_query + parallel ops"""
        function_start = time.time()

        try:
            print(f"🖼️ Starting optimized image search...")
            print(f"🔎 Semantic query for image: '{semantic_query}'")

            # Get cached environment variables and reusable clients
            env_vars = ProcessTextService.get_env_vars()
            index = ProcessTextService.get_pinecone_index(
                env_vars["PINECONE_INDEX_NAME"], env_vars["PINECONE_INDEX_HOST"]
            )
            client = ProcessTextService.get_openai_client()

            # 🚀 PARALLEL OPERATIONS: Chapter check + Embedding creation
            parallel_start = time.time()

            chapter_task = asyncio.to_thread(
                index.query,
                vector=[0.0] * 1536,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )

            embedding_task = client.embeddings.create(
                model="text-embedding-ada-002",
                input=semantic_query,
            )

            chapter_check_response, embedding_response = await asyncio.gather(
                chapter_task, embedding_task
            )

            parallel_time = int((time.time() - parallel_start) * 1000)
            print(f"⏱️ Parallel chapter check + embedding: {parallel_time}ms")

            matches = chapter_check_response.get("matches", [])

            if not matches:
                content = (
                    "Sorry, I don't have an image for this place. "
                    "Kindly upload or generate a relevant one."
                )
                firestore_message = await ProcessTextService._save_message_to_firestore(
                    request, content, image_url=None, user_id="ImageG"
                )

                total_time = int((time.time() - function_start) * 1000)
                print(f"✅ Optimized image search (no matches): {total_time}ms")

                return ImageSearchResult(
                    message="No matches found for chapter",
                    firestore_message=firestore_message,
                    search_metadata=PineconeSearchResult(
                        score=0.0, content=content, metadata={}
                    ),
                )

            # Semantic search with pre-created embedding
            semantic_start = time.time()
            query_vector = embedding_response.data[0].embedding

            search_response = await asyncio.to_thread(
                index.query,
                vector=query_vector,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )
            semantic_time = int((time.time() - semantic_start) * 1000)
            print(f"⏱️ Semantic search: {semantic_time}ms")

            matches = search_response.get("matches", [])
            if not matches:
                raise Exception("No semantic matches found")

            # Process result and save to Firestore
            top_match = matches[0]
            score = top_match["score"]
            metadata = top_match["metadata"]

            original_description = metadata.get("imageDesc", "No description found.")
            long_text = metadata.get("text", "")

            # 🧵 recent chat history for contextual caption
            recent_history = await ProcessTextService._get_last_messages(
                request.chatId,
                limit=6,
            )

            # ✨ format final caption
            formatted_description = await ProcessTextService._format_media_description(
                media_type="image",
                request=request,
                original_label=original_description,
                long_text=long_text,
                chat_history=recent_history,
            )

            content = formatted_description
            if score <= 0.757:
                content += (
                    "\n\nThis is the closest image I could find—feel free to upload a more relevant one!"
                )

            image_url = metadata.get("imageURL", "No image URL found.")

            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, image_url=image_url, user_id="ImageG"
            )

            total_time = int((time.time() - function_start) * 1000)
            print(f"✅ Optimized image search completed: {total_time}ms")

            return ImageSearchResult(
                message="Image search completed successfully",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=score,
                    content=original_description,
                    metadata=metadata,
                ),
            )

        except Exception as e:
            total_time = int((time.time() - function_start) * 1000)
            print(f"❌ Error in optimized image search after {total_time}ms: {str(e)}")

            content = f"Error during image search: {str(e)}"
            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, user_id="ImageG"
            )

            return ImageSearchResult(
                message="Error in image search",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=0.0, content=content, metadata={}
                ),
            )

    # ---------- AUDIO SEARCH ----------

    @staticmethod
    async def search_audio_from_database(
        request: ProcessTextRequest,
        semantic_query: str,
    ) -> AudioSearchResult:
        """🚀 OPTIMIZED audio search using router's semantic_query + parallel ops"""
        function_start = time.time()

        try:
            print(f"🔊 Starting optimized audio search...")
            print(f"🔎 Semantic query for audio: '{semantic_query}'")

            env_vars = ProcessTextService.get_env_vars()
            index = ProcessTextService.get_pinecone_index(
                env_vars["PINECONE_INDEX_NAME3"], env_vars["PINECONE_INDEX_HOST3"]
            )
            client = ProcessTextService.get_openai_client()

            # 🚀 PARALLEL OPERATIONS
            parallel_start = time.time()

            chapter_task = asyncio.to_thread(
                index.query,
                vector=[0.0] * 1536,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )

            embedding_task = client.embeddings.create(
                model="text-embedding-ada-002", input=semantic_query
            )

            chapter_check_response, embedding_response = await asyncio.gather(
                chapter_task, embedding_task
            )

            parallel_time = int((time.time() - parallel_start) * 1000)
            print(f"⏱️ Parallel chapter check + embedding: {parallel_time}ms")

            matches = chapter_check_response.get("matches", [])

            if not matches:
                content = (
                    "Sorry, I don't have an audio clip for this place. "
                    "Kindly upload or generate a relevant one."
                )
                firestore_message = await ProcessTextService._save_message_to_firestore(
                    request, content, image_url=None, user_id="AudioG"
                )
                total_time = int((time.time() - function_start) * 1000)
                print(f"✅ Optimized audio search (no matches): {total_time}ms")
                return AudioSearchResult(
                    message="No matches found for chapter",
                    firestore_message=firestore_message,
                    search_metadata=PineconeSearchResult(
                        score=0.0, content=content, metadata={}
                    ),
                )

            # Semantic search with pre-created embedding
            semantic_start = time.time()
            query_vector = embedding_response.data[0].embedding

            search_response = await asyncio.to_thread(
                index.query,
                vector=query_vector,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )
            semantic_time = int((time.time() - semantic_start) * 1000)
            print(f"⏱️ Semantic search: {semantic_time}ms")

            matches = search_response.get("matches", [])
            if not matches:
                raise Exception("No semantic matches found")

            top_match = matches[0]
            score = top_match["score"]
            metadata = top_match["metadata"]

            original_description = metadata.get("audioDesc", "No description found.")
            long_text = metadata.get("text", "")

            # 🧵 recent chat history for contextual caption
            recent_history = await ProcessTextService._get_last_messages(
                request.chatId,
                limit=6,
            )

            # ✨ format final caption
            formatted_description = await ProcessTextService._format_media_description(
                media_type="audio",
                request=request,
                original_label=original_description,
                long_text=long_text,
                chat_history=recent_history,
            )

            content = formatted_description
            if score <= 0.757:
                content += (
                    "\n\nThis is the closest audio I could find—feel free to upload a more relevant one!"
                )

            audio_url = metadata.get("audioURL", "No audio URL found.")

            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, image_url=audio_url, user_id="AudioG"
            )

            total_time = int((time.time() - function_start) * 1000)
            print(f"✅ Optimized audio search completed: {total_time}ms")

            return AudioSearchResult(
                message="Audio search completed successfully",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=score,
                    content=original_description,
                    metadata=metadata,
                ),
            )

        except Exception as e:
            total_time = int((time.time() - function_start) * 1000)
            print(f"❌ Error in optimized audio search after {total_time}ms: {str(e)}")

            content = f"Error during audio search: {str(e)}"
            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, user_id="AudioG"
            )

            return AudioSearchResult(
                message="Error in audio search",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=0.0, content=content, metadata={}
                ),
            )

    # ---------- VIDEO SEARCH ----------

    @staticmethod
    async def search_video_from_database(
        request: ProcessTextRequest,
        semantic_query: str,
    ) -> VideoSearchResult:
        """🚀 OPTIMIZED video search using router's semantic_query + parallel ops"""
        function_start = time.time()

        try:
            print(f"🎬 Starting optimized video search...")
            print(f"🔎 Semantic query for video: '{semantic_query}'")

            env_vars = ProcessTextService.get_env_vars()
            index = ProcessTextService.get_pinecone_index(
                env_vars["PINECONE_INDEX_NAME2"], env_vars["PINECONE_INDEX_HOST2"]
            )
            client = ProcessTextService.get_openai_client()

            # 🚀 PARALLEL OPERATIONS
            parallel_start = time.time()

            chapter_task = asyncio.to_thread(
                index.query,
                vector=[0.0] * 1536,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )

            embedding_task = client.embeddings.create(
                model="text-embedding-ada-002", input=semantic_query
            )

            chapter_check_response, embedding_response = await asyncio.gather(
                chapter_task, embedding_task
            )

            parallel_time = int((time.time() - parallel_start) * 1000)
            print(f"⏱️ Parallel chapter check + embedding: {parallel_time}ms")

            matches = chapter_check_response.get("matches", [])

            if not matches:
                content = (
                    "Sorry, I don't have a video for this place. "
                    "Kindly upload or generate a relevant one."
                )
                firestore_message = await ProcessTextService._save_message_to_firestore(
                    request, content, image_url=None, user_id="VideoG"
                )
                total_time = int((time.time() - function_start) * 1000)
                print(f"✅ Optimized video search (no matches): {total_time}ms")
                return VideoSearchResult(
                    message="No matches found for chapter",
                    firestore_message=firestore_message,
                    search_metadata=PineconeSearchResult(
                        score=0.0, content=content, metadata={}
                    ),
                )

            # Semantic search with pre-created embedding
            semantic_start = time.time()
            query_vector = embedding_response.data[0].embedding

            search_response = await asyncio.to_thread(
                index.query,
                vector=query_vector,
                top_k=1,
                filter={"chapterId": request.chapterId},
                include_metadata=True,
            )
            semantic_time = int((time.time() - semantic_start) * 1000)
            print(f"⏱️ Semantic search: {semantic_time}ms")

            matches = search_response.get("matches", [])
            if not matches:
                raise Exception("No semantic matches found")

            top_match = matches[0]
            score = top_match["score"]
            metadata = top_match["metadata"]

            original_description = metadata.get("videoDesc", "No description found.")
            long_text = metadata.get("text", "")

            # 🧵 recent chat history for contextual caption
            recent_history = await ProcessTextService._get_last_messages(
                request.chatId,
                limit=6,
            )

            # ✨ format final caption
            formatted_description = await ProcessTextService._format_media_description(
                media_type="video",
                request=request,
                original_label=original_description,
                long_text=long_text,
                chat_history=recent_history,
            )

            content = formatted_description
            if score <= 0.757:
                content += (
                    "\n\nThis is the closest video I could find—feel free to upload a more relevant one!"
                )

            video_url = metadata.get("videoURL", "No video URL found.")

            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, image_url=video_url, user_id="VideoG"
            )

            total_time = int((time.time() - function_start) * 1000)
            print(f"✅ Optimized video search completed: {total_time}ms")

            return VideoSearchResult(
                message="Video search completed successfully",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=score,
                    content=original_description,
                    metadata=metadata,
                ),
            )

        except Exception as e:
            total_time = int((time.time() - function_start) * 1000)
            print(f"❌ Error in optimized video search after {total_time}ms: {str(e)}")

            content = f"Error during video search: {str(e)}"
            firestore_message = await ProcessTextService._save_message_to_firestore(
                request, content, user_id="VideoG"
            )

            return VideoSearchResult(
                message="Error in video search",
                firestore_message=firestore_message,
                search_metadata=PineconeSearchResult(
                    score=0.0, content=content, metadata={}
                ),
            )

    # ---------- LLM FORMATTER FOR MEDIA CAPTION ----------

    @staticmethod
    async def _format_media_description(
        media_type: str,                      # "image" | "audio" | "video"
        request: ProcessTextRequest,
        original_label: str,                  # imageDesc / videoDesc / audioDesc (short label)
        long_text: str,                       # metadata["text"] (rich description)
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Use OpenAI to generate a final, user-facing description for the
        selected media asset, contextualised to the recent chat and
        the user's last question.

        Returns a single string (1–2 sentences).
        """

        client = ProcessTextService.get_openai_client()

        # 1) Compact recent chat history into short lines
        history_snippets: List[str] = []
        for msg in chat_history or []:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if content:
                history_snippets.append(f"{role}: {content[:220]}")

        recent_chat_str = "\n".join(history_snippets[-8:])  # last few lines only

        # 2) Build payload for the model
        payload = {
            "media_type": media_type,
            "user_query": request.content,    # last user message
            "original_label": original_label,
            "long_text": long_text,
            "recent_chat": recent_chat_str,
        }

        system_prompt = """
You are Kabir's media caption writer.

You receive:
- media_type: "image", "audio", or "video"
- user_query: the LAST user message (e.g., "show me his image")
- original_label: a short label for the asset (e.g., "Taj Mahal Drone shot")
- long_text: a longer descriptive paragraph about the asset
- recent_chat: a short transcript of recent user/assistant messages

Your task:
- Write ONE short, user-facing description (1–2 sentences) that:
  - feels like a direct reply to the user's last question,
  - is consistent with the recent_chat context,
  - clearly describes the selected media asset.

Guidelines:
- Use the long_text as your main source of details, but keep the final output concise.
- Resolve pronouns in user_query like "his", "her", "this", "that painting" using recent_chat.
- Do NOT mention 'original_label' or 'metadata' explicitly.
- Do NOT mention that you are an AI or talk about captions, assets, or URLs.
- Write in simple, clear language that matches the user’s current language and tone.

Return ONLY valid JSON in this exact shape:

{
  "description": "<final text to show user>"
}
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            response = await client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=messages,
                max_tokens=200,
                temperature=0.3,
            )
            raw = response.choices[0].message.content.strip()
            print(f"🧩 Media caption raw JSON: {raw}")

            obj = json.loads(raw)
            description = (obj.get("description") or "").strip()

            if not description:
                # Fallback: short version of long_text or original_label
                if long_text:
                    return long_text.strip()[:400]
                return original_label

            return description

        except Exception as e:
            print(f"⚠️ Media caption error: {str(e)}")
            # Fallback on error
            if long_text:
                return long_text.strip()[:400]
            return original_label

    # ---------- FIRESTORE WRITE HELPERS ----------

    @staticmethod
    async def _save_message_to_firestore(
        request: ProcessTextRequest,
        content: str,
        image_url: Optional[str] = None,
        user_id: str = "assistant",
    ) -> FirestoreMessage:
        """Save message to Firestore (async wrapped)"""

        def sync_save():
            chat_doc_ref = firebase_config.db.collection("chats").document(
                request.chatId
            )
            message_data = {
                "content": content,
                "created_at": datetime.utcnow().isoformat(timespec="milliseconds")
                + "Z",
                "location": request.location,
                "role": "assistant",
                "user_id": user_id,
            }

            if image_url:
                message_data["image_url"] = image_url

            doc_ref = chat_doc_ref.collection("messages").document()
            message_id = doc_ref.id
            message_data["id"] = message_id
            doc_ref.set(message_data)

            return FirestoreMessage(**message_data)

        try:
            start_time = time.time()
            result = await asyncio.to_thread(sync_save)
            save_time = int((time.time() - start_time) * 1000)
            print(f"⏱️ Firestore message save: {save_time}ms")
            return result
        except Exception as e:
            save_time = int((time.time() - start_time) * 1000)
            print(f"❌ Firestore save error after {save_time}ms: {str(e)}")

            return FirestoreMessage(
                id="error",
                content=f"Error saving to Firestore: {str(e)}",
                created_at=datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                location=request.location,
                role="assistant",
                user_id="error",
            )

    @staticmethod
    async def _save_error_message(
        request: ProcessTextRequest, error: str
    ) -> FirestoreMessage:
        """Save error message to Firestore"""
        return await ProcessTextService._save_message_to_firestore(
            request, f"Sorry, I encountered an error: {error}", user_id="ErrorG"
        )
