import logging
import time
import httpx
import json
import os
from typing import List, Dict, Any, Optional


# Configure logging
logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, token: str):
        """
        Initialize LLM Client with OpenRouter API.
        
        Args:
            token: OpenRouter API Key (required, must be provided from UI Settings)
        """
        if not token:
            raise ValueError(
                "OpenRouter API Key is required. "
                "Please configure it in the UI Settings modal (click the Settings button)."
            )
        
        self.token = token.strip()
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Use Qwen 2.5-VL for all agents as instructed
        # Can be overridden by environment variables if needed
        self.vision_model = os.environ.get("VISION_MODEL", "qwen/qwen-2-vl-72b-instruct")
        self.coding_model = os.environ.get("CODING_MODEL", "qwen/qwen-2-vl-72b-instruct")
        self.testing_model = os.environ.get("TESTING_MODEL", "qwen/qwen-2-vl-72b-instruct")

    def generate_chat_completion(self, model: str, messages: List[Dict[str, str]], max_tokens: int = 1024, temperature=0.2, token: Optional[str] = None) -> Dict[str, Any]:
        """Generic chat completion wrapper for OpenRouter API."""
        # active_token preference: function arg > instance token
        active_token = (token or self.token or "").strip()
        
        if not active_token:
             raise ValueError(
                 "OpenRouter API Key is missing. "
                 "Please configure it in the UI Settings modal (click the Settings button)."
             )


        headers = {
            "Authorization": f"Bearer {active_token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/figma-to-code", # OpenRouter best practice
            "X-Title": "Figma To Storybook Agent"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        start_time = time.time()
        logger.info(f"🤖 Calling OpenRouter API - Model: {model}")
        
        try:
            # We use a longer timeout for LLM generation
            with httpx.Client(timeout=60.0) as client:
                response = client.post(self.api_url, headers=headers, json=payload)
                
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code != 200:
                error_msg = f"Status: {response.status_code}, Body: {response.text}"
                logger.error(f"❌ OpenRouter API Error ({model}): {error_msg}")
                raise Exception(f"OpenRouter API failed: {error_msg}")

            data = response.json()
            
            # Log the full response for debugging
            logger.debug(f"📦 Full API Response: {json.dumps(data, indent=2)}")
            
            # Extract content carefully handling potential unexpected schemas
            try:
                # Check if response has error field
                if "error" in data:
                    error_detail = data.get("error", {})
                    error_msg = error_detail.get("message", str(error_detail))
                    logger.error(f"❌ API returned error: {error_msg}")
                    raise Exception(f"API Error: {error_msg}")
                
                # Try to extract content
                if "choices" not in data:
                    logger.error(f"❌ Response missing 'choices' field. Available keys: {list(data.keys())}")
                    logger.error(f"❌ Full response: {json.dumps(data, indent=2)}")
                    raise Exception(f"Invalid API response structure: missing 'choices' field. Response keys: {list(data.keys())}")
                
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"❌ Invalid response structure from OpenRouter")
                logger.error(f"❌ Error: {str(e)}")
                logger.error(f"❌ Response data: {json.dumps(data, indent=2)}")
                raise Exception(f"Invalid API response structure: '{str(e)}'. Check logs for full response.")
            
            # Log success
            logger.info(f"✅ Response received in {duration_ms}ms")
            logger.debug(f"📝 Response preview (first 500 chars): {content[:500]}")
            
            return {
                "content": content,
                "model": model,
                "duration_ms": duration_ms,
                "success": True
            }
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"❌ API Call Failed: {str(e)}")
            raise

    def architect_analyze(self, image_url: str, prompt: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Use Vision model to analyze Figma design."""
        logger.info("🎨 Architect Agent: Analyzing design with Vision Model...")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        return self.generate_chat_completion(self.vision_model, messages, max_tokens=1024, temperature=0.1, token=token)

    def developer_code(self, prompt: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Use Coding model to generate React code."""
        logger.info("💻 Developer Agent: Generating React component code...")
        
        messages = [{"role": "user", "content": prompt}]
        # Developer needs higher token limit for full component code
        return self.generate_chat_completion(self.coding_model, messages, max_tokens=4096, temperature=0.1, token=token)
    
    def developer_code_with_vision(self, image_url: str, specs: dict, prompt: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Developer generates code while SEEING the design image for visual verification."""
        logger.info("💻👁️ Developer Agent: Generating code with visual verification...")
        
        import json
        specs_text = json.dumps(specs, indent=2)
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": f"{prompt}\n\n=== ARCHITECT SPECS ===\n{specs_text}\n\n=== YOUR TASK ===\nGenerate code that MATCHES the image above. Verify colors, layout, spacing visually."}
                ]
            }
        ]
        
        return self.generate_chat_completion(self.coding_model, messages, max_tokens=4096, temperature=0.1, token=token)

    def caption_asset(self, image_data_uri: str, token: Optional[str] = None) -> str:
        """
        Generate a short, semantic caption for a UI asset (icon/image).
        Used to give the Developer Agent context about what the asset is.
        """
        prompt = """
        Describe this UI asset in 3-5 words. 
        Examples: "Red Google Logo", "Search Icon", "User Avatar Placeholder", "Blue Submit Button Background".
        Start directly with the description. Do NOT say "This is...".
        """
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # We use the vision model, but with very low tokens as we only need a short caption
        try:
            response = self.generate_chat_completion(self.vision_model, messages, max_tokens=50, temperature=0.1, token=token)
            return response.get("content", "").strip().replace('"', '').replace("'", "")
        except Exception as e:
            logger.warning(f"⚠️ Failed to caption asset: {e}")
            return "Asset"  # Fallback


    def tester_validate(self, prompt: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Use QA model for validation."""
        logger.info("🧪 QA Agent: Running validation tests...")
        
        messages = [{"role": "user", "content": prompt}]
        return self.generate_chat_completion(self.testing_model, messages, temperature=0.1, token=token)

    def validate_connection(self, token: Optional[str] = None) -> bool:
        """
        Pre-flight check: Verify OpenRouter API is reachable.
        """
        logger.info("📡 Running Pre-flight Check: Validating OpenRouter API...")
        
        try:
            # Simple test with cheapest model
            messages = [{"role": "user", "content": "test"}]
            
            test_token = token or self.token
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {test_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.testing_model,
                    "messages": messages,
                    "max_tokens": 5
                },
                timeout=10
            )
            
            # Accept 200 (success) or 402 (insufficient credits but API works)
            if response.status_code in [200, 402]:
                if response.status_code == 402:
                    logger.warning("⚠️  OpenRouter API reachable but needs credits")
                    logger.warning("   The free models should still work for basic requests")
                logger.info("✅ Pre-flight Check Passed: OpenRouter API is reachable")
                return True
            else:
                logger.error(f"❌ Pre-flight Check Failed: Status {response.status_code}")
                logger.error(f"   Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Pre-flight Check Failed: {str(e)}")
            logger.error("   Check your OpenRouter API key in Settings")
            return False
