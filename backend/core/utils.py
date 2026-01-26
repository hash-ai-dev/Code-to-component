import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def extract_json(text: str) -> Dict[str, Any]:
    """
    Extracts JSON from a string, anticipating markdown code blocks or raw JSON.
    """
    try:
        # Try to find JSON within ```json ... ``` blocks
        match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Try to find the first { and last }
            match_brackets = re.search(r"(\{.*\})", text, re.DOTALL)
            if match_brackets:
                json_str = match_brackets.group(1)
            else:
                json_str = text

        return json.loads(json_str)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON from: {text[:100]}...")
        return {}

async def emit_log(state: Dict[str, Any], agent: str, message: str, level: str = "info", progress: Optional[float] = None, phase: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
    """
    Emits a log message to the system (and ideally to the frontend via websockets).
    Current implementation logs to backend console to avoid circular dependencies.
    """
    icon_map = {
        "architect": "🎨",
        "developer": "💻",
        "tester": "🧪",
        "system": "⚙️"
    }
    icon = icon_map.get(agent, "")
    
    # Log to backend console
    logger.info(f"{icon} [{agent.upper()}] {message}")
    
    # Note: Real-time streaming to frontend requires access to log_queues in main.py
    # which is hard to reach from here without circular imports. 
    # For now, we rely on backend logs.
