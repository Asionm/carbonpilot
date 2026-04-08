# configs/llm_wrapper.py
from dotenv import load_dotenv
import os
import json
import logging
import httpx
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

load_dotenv(override=True)

# ────────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if os.getenv("LLM_DEBUG", "0") == "1" else logging.INFO)

def make_logging_http_client(provider_name: str = "unknown") -> httpx.Client:
    """Create an httpx client that logs requests/responses (body only in DEBUG)."""

    def log_request(request: httpx.Request):
        try:
            body = request.content.decode() if request.content else ""
            logger.info(f"[{provider_name.upper()} HTTP OUT] {request.method} {request.url}")
            if logger.isEnabledFor(logging.DEBUG):
                if "application/json" in request.headers.get("content-type", ""):
                    try:
                        logger.debug(
                            f"[{provider_name.upper()} HTTP OUT JSON]\n%s",
                            json.dumps(json.loads(body), ensure_ascii=False, indent=2),
                        )
                    except Exception:
                        logger.debug(f"[{provider_name.upper()} HTTP OUT RAW]\n%s", body)
        except Exception as e:
            logger.error(f"[{provider_name.upper()} HTTP OUT log error] {e}", exc_info=True)

    def log_response(response: httpx.Response):
        try:
            logger.info(
                f"[{provider_name.upper()} HTTP IN] {response.status_code} {response.request.method} {response.request.url}"
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[{provider_name.upper()} HTTP IN HDR] %s", dict(response.headers))
                try:
                    # Try to read the response content safely
                    if not response.is_stream_consumed and response.is_closed:
                        # If response is closed but not consumed, we can't read it
                        logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <closed stream, content not available>")
                    elif not response.is_stream_consumed:
                        # Try to read the stream
                        response.read()
                        content = response.content
                        if content:
                            try:
                                decoded_content = content.decode()
                                logger.debug(f"[{provider_name.upper()} HTTP IN BODY]\n%s", decoded_content)
                            except Exception:
                                logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <binary content, length: {len(content)}>")
                        else:
                            logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <empty response>")
                    else:
                        # Stream already consumed
                        content = response.content
                        if content:
                            try:
                                decoded_content = content.decode()
                                logger.debug(f"[{provider_name.upper()} HTTP IN BODY]\n%s", decoded_content)
                            except Exception:
                                logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <binary content, length: {len(content)}>")
                        else:
                            logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <empty response>")
                except Exception as e:
                    logger.debug(f"[{provider_name.upper()} HTTP IN BODY] <cannot read content: {str(e)}>")
        except Exception as e:
            logger.error(f"[{provider_name.upper()} HTTP IN log error] {e}", exc_info=True)

    return httpx.Client(
        timeout=60,
        event_hooks={"request": [log_request], "response": [log_response]},
    )
# ────────────────────────────────────────────────────────────────────────────────
# LLM Wrapper
# ────────────────────────────────────────────────────────────────────────────────
class LLMWrapper:

    def __init__(self, streaming: bool = False, sse_callback=None):
        llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
        http_client = make_logging_http_client(llm_provider)

        self.think_mode = os.getenv("LLM_THINK_MODE", "hide").lower()  # off/hide/show/legacy_strip
        self.streaming = streaming
        self.sse_callback = sse_callback  # Store the SSE callback

        if llm_provider == "openai":
            extra_body = {
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", 8192)),
                "enable_thinking": False,  # Disable thinking for non-streaming calls
            }
            
            # Only add stream parameter if we're using streaming
            if streaming:
                extra_body["stream"] = True

            self.llm = ChatOpenAI(
                base_url=os.getenv("LLM_OPENAI_API_BASE"),
                api_key=os.getenv("LLM_OPENAI_API_KEY"),
                model=os.getenv("LLM_MODEL_NAME"),
                temperature=float(os.getenv("LLM_TEMPERATURE", 0.7)),
                extra_body=extra_body,
                http_client=http_client,
                streaming=streaming
            )

        elif llm_provider == "ollama":
            model_kwargs = {}
            reasoning = None

            stop_token = os.getenv("LLM_OLLAMA_STOP_TOKEN")
            if stop_token:
                model_kwargs["stop"] = [stop_token]

            mode = self.think_mode
            if mode == "off":
                model_kwargs["think"] = False
                reasoning = False
            elif mode == "hide":
                model_kwargs["hidethinking"] = True
                reasoning = True
            elif mode == "show":
                model_kwargs["think"] = True
                reasoning = True
            elif mode == "legacy_strip":
                reasoning = None
            else:
                reasoning = None

            self.llm = ChatOllama(
                model=os.getenv("LLM_MODEL_NAME"),
                temperature=float(os.getenv("LLM_TEMPERATURE", 0.7)),
                num_predict=int(os.getenv("LLM_MAX_TOKENS", 8192)),
                base_url=os.getenv("LLM_OLLAMA_BASE_URL", "http://localhost:11434"),
                http_client=http_client,
                reasoning=reasoning,
                model_kwargs=model_kwargs or {},
                streaming=streaming  # Set streaming based on parameter
            )

        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    # ────────────────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────────────────
    def generate_response(self, prompt: str) -> str:

        msg = self.llm.invoke(prompt)

        meta = getattr(msg, "response_metadata", {}) or {}
        logger.info(
            f"[LLM meta] finish_reason={meta.get('finish_reason')} usage={meta.get('token_usage')}"
        )

        content = getattr(msg, "content", str(msg))


        ak = getattr(msg, "additional_kwargs", {}) or {}
        reasoning_content = (
            ak.get("reasoning_content")
            or ak.get("thinking")
            or ak.get("reasoning")
        )

        mode = getattr(self, "think_mode", "hide")


        if mode in ("hide", "legacy_strip"):
            import re

            content = re.sub(r"\\(.*?\\)\s*\n?\s*", "", content, flags=re.DOTALL)


        if mode == "show" and reasoning_content:
            logger.debug("[THINKING]\n%s", reasoning_content)

        return content


    def generate_prob(self, prompt: str):
        import json
        
        # Create a dedicated http client for this call to capture raw response
        http_client = httpx.Client(timeout=60)
        
        try:
            # Prepare the request data
            api_base = os.getenv("LLM_OPENAI_API_BASE", "").rstrip("/")
            api_key = os.getenv("LLM_OPENAI_API_KEY")
            model = os.getenv("LLM_MODEL_NAME")
            
            # Check if we're using Ollama, if so, return None as Ollama doesn't support logprobs
            llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
            if llm_provider == "ollama":
                logger.warning("Ollama doesn't support logprobs, returning None")
                return None
            
            url = f"{api_base}/chat/completions"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}" if api_key else "",
            }
            
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": float(os.getenv("LLM_TEMPERATURE", 0.7)),
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", 8192)),
                "logprobs": True,
                "top_logprobs": 5,
                "stream": False,
                "enable_thinking": False
            }
            
            # Make the request directly
            response = http_client.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            # Parse the JSON response
            response_data = response.json()
            
            # Extract logprobs from the raw response - support both structures
            choices = response_data.get("choices", [])
            if choices:
                first_choice = choices[0]
                
                # Try first structure: logprobs directly in choice object
                logprobs = first_choice.get("logprobs")
                
                # If not found, try second structure: logprobs in message object
                if logprobs is None:
                    message = first_choice.get("message", {})
                    logprobs = message.get("logprobs")
                
                # Extract content if logprobs exists
                if logprobs is not None:
                    content = logprobs.get("content")
                    if content is not None:
                        return content
            
            logger.error(f"Could not extract logprobs from raw response: {response_data}")
            return None
            
        except Exception as e:
            logger.error(f"Error in generate_prob with direct HTTP call: {e}", exc_info=True)
            
            # Send error to SSE if callback is available
            if self.sse_callback:
                try:
                    self.sse_callback("error", {
                        "type": "llm_error",
                        "message": f"Error in LLM probability generation: {str(e)}",
                        "details": str(e),
                        "component": "llm_wrapper.generate_prob"
                    })
                except Exception as sse_error:
                    logger.error(f"Failed to send error to SSE: {sse_error}")
            
            return None
        finally:
            http_client.close()

    def get_langchain_llm(self):
        """Return the LLM instance, which can be configured for streaming or not"""
        return self.llm

    @classmethod
    def get_streaming_instance(cls):
        """Factory method to get a streaming LLM instance"""
        return cls(streaming=True)

    @classmethod
    def get_non_streaming_instance(cls):
        """Factory method to get a non-streaming LLM instance"""
        return cls(streaming=False)