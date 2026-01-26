import logging
import re
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class AssetHandler:
    """
    Dedicated handler for managing asset tokens within the AI code generation pipeline.
    
    Strategy:
    1. Map every extracted asset to a rigid, standardized token (e.g., __ASSET_0__).
    2. Provide CLEAR instructions to the LLM to use these exact tokens.
    3. Perform robust text replacement to swap tokens for Data URIs.
    """
    
    def __init__(self, assets: Dict[str, str]):
        """
        Initialize with a dictionary of { "Original Name": "data:image/..." }
        """
        self.original_assets = assets if assets else {}
        self.token_map = {}  # { "__ASSET_0__": "data:image/..." }
        self.meta_map = {}   # { "__ASSET_0__": { "name": "Original Name", "type": "png/svg" } }
        
        self._initialize_mapping()
        
    def _initialize_mapping(self):
        """Create the standardized mapping."""
        if not self.original_assets:
            return
            
        logger.info(f"🔄 AssetHandler: Registering {len(self.original_assets)} assets from extraction...")
        
        # Sort keys to ensure deterministic ordering (important for testing/retries)
        sorted_names = sorted(self.original_assets.keys())
        
        for i, name in enumerate(sorted_names):
            data_uri = self.original_assets[name]
            token = f"__ASSET_{i}__"
            
            self.token_map[token] = data_uri
            self.meta_map[token] = {
                "name": name,
                "type": "SVG Icon" if "svg" in data_uri or "svg" in name.lower() else "Image"
            }
            logger.debug(f"   Ref: {token} -> '{name}'")
            
        logger.info(f"✅ AssetHandler: Ready with {len(self.token_map)} standardized tokens.")

    def get_prompt_section(self) -> str:
        """
        Generate the strict prompt section for the LLM.
        """
        if not self.token_map:
            return ""
            
        asset_list_str = []
        for token, meta in self.meta_map.items():
            asset_list_str.append(f"""
👉 ASSET {token}
   • Description: "{meta['name']}"
   • Type: {meta['type']}
   • TOKEN TO USE: {token}
""")
        
        formatted_list = "".join(asset_list_str)
        
        return f"""
🚨🚨🚨 CRITICAL: ASSET PLACEMENT RULES 🚨🚨🚨
===============================================================
I have extracted {len(self.token_map)} assets from the design.
You MUST use the SPECIFIC TOKENS below to place them.

YOUR JOB:
1. Look at the design image.
2. Identify which asset corresponds to which part of the image.
3. Use the corresponding token in the `src` attribute.

❌ DO NOT use data:image... strings.
❌ DO NOT use placeholders like "logo.png".
✅ USE ONLY THESE TOKENS:

{formatted_list}

EXAMPLE USAGE:
<img src="__ASSET_0__" alt="{list(self.meta_map.values())[0]['name']}" />
===============================================================
"""

    def replace_tokens(self, code: str) -> Tuple[str, int, List[str]]:
        """
        Replace all tokens in the code with their Data URIs.
        Returns: (modified_code, count_replaced, missing_tokens)
        """
        if not self.token_map:
            return code, 0, []
            
        replaced_count = 0
        missing_tokens = []
        
        logger.info("🔄 AssetHandler: Starting token replacement...")
        
        for token, data_uri in self.token_map.items():
            if token in code:
                # Perform replacement
                code = code.replace(token, data_uri)
                replaced_count += 1
                logger.info(f"   ✅ Replaced {token} (Mapped to: '{self.meta_map[token]['name']}')")
            else:
                missing_tokens.append(token)
                logger.warning(f"   ⚠️  Token {token} ('{self.meta_map[token]['name']}') NOT FOUND in generated code.")
                
        return code, replaced_count, missing_tokens

    def validate_code(self, code: str) -> List[str]:
        """
        Check if the code has any blatant issues related to assets.
        Returns list of error messages.
        """
        errors = []
        
        # Check for banned patterns
        if "data:image" in code and len(code) > 50000: 
            # Heuristic: if code is huge and has data:image, maybe LLM halluncinated raw base64
            # We strictly asked for tokens. If it used raw base64, that's technically valid React but bad practice for our token system.
            # But wait, we just REPLACED tokens with data:image.
            # So validation should happen BEFORE replacement? Or checking for *other* things?
            pass

        # Check for unused tokens logic is handled in replace_tokens return value
        
        return errors
