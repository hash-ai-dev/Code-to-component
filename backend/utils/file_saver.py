import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def save_generated_files(component_code: str, stories_code: str, component_name: str = "Component") -> dict:
    """
    Saves the generated component and story files to the frontend/src/stories/generated directory.
    Returns a dict with the absolute paths of the saved files.
    """
    try:
        # 1. Determine Output Directory
        # Go up two levels from backend/utils to root, then into frontend/src/stories/generated
        current_dir = Path(__file__).parent
        project_root = current_dir.parent.parent
        target_dir = project_root / "frontend" / "src" / "stories" / "generated"
        
        # Ensure directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Sanitize Component Name (remove special chars, spaces)
        safe_name = re.sub(r'[^a-zA-Z0-9]', '', component_name)
        if not safe_name:
            safe_name = "GeneratedComponent"
            
        # 3. Define File Paths
        component_file_path = target_dir / f"{safe_name}.tsx"
        stories_file_path = target_dir / f"{safe_name}.stories.tsx"
        
        # 4. Write Component File
        with open(component_file_path, "w", encoding="utf-8") as f:
            f.write(component_code)
        logger.info(f"✅ Saved component to: {component_file_path}")
            
        # 5. Write Stories File
        with open(stories_file_path, "w", encoding="utf-8") as f:
            f.write(stories_code)
        logger.info(f"✅ Saved stories to: {stories_file_path}")
            
        return {
            "component_path": str(component_file_path),
            "stories_path": str(stories_file_path)
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to save generated files: {str(e)}")
        raise e
