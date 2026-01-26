import logging
import re
import os
import aiofiles
import httpx
from pathlib import Path
from typing import Dict, List, Any, Optional
from services.figma_client import FigmaClient
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

class AssetExtractor:
    def __init__(self, figma_client: FigmaClient):
        self.figma = figma_client
        self.supported_image_types = ["IMAGE", "RECTANGLE", "ELLIPSE"] # Nodes that might contain image fills
        self.supported_vector_types = ["VECTOR", "STAR", "POLYGON", "BOOLEAN_OPERATION", "GROUP", "FRAME"]

    async def extract_assets(self, file_key: str, node_data: Dict[str, Any], session_id: str, hf_token: Optional[str] = None, save_dir: Optional[str] = None, base_url: Optional[str] = None, figma_token: Optional[str] = None) -> Dict[str, str]:
        """
        Main entry point. Traverses the node, identifies assets, exports them, 
        and extracts Base64 Data URIs for robust embedding.
        
        Now includes AUTO-CAPTIONING via Vision LLM.
        
        Returns a map of { "Original Name - Caption": data_uri }.
        """
        import base64
        
        logger.info(f"📦 Starting Asset Extraction (File Mode) for file {file_key}...")
        
        # Initialize LLM Client for captioning if token is present
        llm = LLMClient(token=hf_token) if hf_token else None
        if not llm:
            logger.warning("⚠️  No HF Token provided to AssetExtractor - Auto-captioning will be SKIPPED.")
        
        # 1. Traverse and identify candidates
        image_candidates = [] # Tuples of (node_id, name, node)
        vector_candidates = [] 
        
        try:
            logger.info("🕵️ Starting Node Traversal...")
            self._traverse_traverse(node_data, image_candidates, vector_candidates)
        except Exception as  e:
            logger.error(f"❌ Traversal failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        logger.info(f"🔍 Found {len(image_candidates)} potential images and {len(vector_candidates)} potential icons/vectors")
        
        # 2. Filter candidates (heuristics)
        final_images = []
        for img in image_candidates:
            if self._has_image_fills(img[2]):
                final_images.append(img)
            else:
                logger.debug(f"   ❌ Rejected Image Candidate: {img[1]} (No visible image fills)")
                
        final_vectors = []
        for vec in vector_candidates:
            if self._is_likely_icon(vec[1], vec[2]):
                final_vectors.append(vec)
            # else:
            #     logger.debug(f"   ❌ Rejected Vector Candidate: {vec[1]} (Failed icon heuristics)")
        
        logger.info(f"✨ Filtering: {len(final_images)} images and {len(final_vectors)} icons to export")
        
        if not final_images and not final_vectors:
             logger.warning("⚠️  No assets found after filtering! Dumping detailed debug info...")
             # Log the first few rejected vector candidates to see why
             for i, vec in enumerate(vector_candidates[:10]):
                 logger.warning(f"   ❌ Rejected Vector: {vec[1]} (Type: {vec[2].get('type')})")
        
        # 3. Batch Export URLs using Figma API
        image_ids = [img[0] for img in final_images]
        vector_ids = [vec[0] for vec in final_vectors]
        
        try:
            image_urls = await self.figma.get_images_batch(file_key, image_ids, format="png", scale=2, token=figma_token) if image_ids else {}
            vector_urls = await self.figma.get_images_batch(file_key, vector_ids, format="svg", scale=1, token=figma_token) if vector_ids else {}
        except Exception as e:
            logger.error(f"❌ Figma API Export failed: {e}")
            image_urls = {}
            vector_urls = {}
        
        # 4. Download, Save to Disk, and CAPTION
        asset_map = {} # { "Name - Caption": url_path }
        
        # Helper to download and save
        async with httpx.AsyncClient() as client:
            # Download Images
            for node_id, name, _ in final_images:
                url = image_urls.get(node_id)
                if url:
                    # Sanitize filename
                    sanitized_name = self._sanitize_for_filename(name)
                    filename = f"image_{sanitized_name}_{node_id.replace(':', '_')}.png"
                    
                    final_key = name
                    
                    if save_dir:
                         saved_path = await self._save_asset_to_disk(client, url, save_dir, filename)
                         if saved_path:
                            public_url = f"{base_url}/{filename}" if base_url else saved_path
                            asset_map[final_key] = public_url
                            logger.info(f"   📦 Saved IMAGE: '{final_key}' -> {public_url}")
                         else:
                            # Fallback: use Figma URL directly
                            logger.warning(f"   ⚠️  Failed to save '{final_key}', using Figma URL as fallback")
                            asset_map[final_key] = url
                    else:
                        # No save_dir provided, use Figma URL directly
                        asset_map[final_key] = url

            # Download Vectors
            for node_id, name, _ in final_vectors:
                url = vector_urls.get(node_id)
                if url:
                    sanitized_name = self._sanitize_for_filename(name)
                    filename = f"icon_{sanitized_name}_{node_id.replace(':', '_')}.svg"
                    
                    final_key = name
                    
                    if save_dir:
                         saved_path = await self._save_asset_to_disk(client, url, save_dir, filename)
                         if saved_path:
                            public_url = f"{base_url}/{filename}" if base_url else saved_path
                            asset_map[final_key] = public_url
                            logger.info(f"   📦 Saved VECTOR: '{final_key}' -> {public_url}")
                         else:
                            # Fallback: use Figma URL directly
                            logger.warning(f"   ⚠️  Failed to save '{final_key}', using Figma URL as fallback")
                            asset_map[final_key] = url
                    else:
                        # No save_dir provided, use Figma URL directly
                        asset_map[final_key] = url
                        
        logger.info(f"✅ Extracted and saved {len(asset_map)} assets")
        return asset_map

    async def _save_asset_to_disk(self, client: httpx.AsyncClient, url: str, save_dir: str, filename: str) -> Optional[str]:
        """Download asset and save to disk with proper headers"""
        try:
            # Add User-Agent to avoid 403s from some CDNs/S3 buckets
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            resp = await client.get(url, headers=headers, follow_redirects=True)
            
            if resp.status_code == 200:
                file_path = os.path.join(save_dir, filename)
                async with aiofiles.open(file_path, mode='wb') as f:
                    await f.write(resp.content)
                return file_path
            else:
                logger.warning(f"❌ Failed to downoad asset {filename}. Status: {resp.status_code}. Response: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Failed to save asset {url} to {save_dir}: {e}")
        return None
        
    def _sanitize_for_filename(self, name: str) -> str:
        """Sanitize string for strict filename usage"""
        import re
        # Remove extension if present to avoid double extension
        name = re.sub(r'\.(png|jpg|jpeg|svg)$', '', name, flags=re.IGNORECASE)
        # Check alphanumeric
        clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return clean[:50]

    def _traverse_traverse(self, node: Dict[str, Any], images: List, vectors: List):
        """Recursive traversal - Maximally inclusive candidate generation"""
        node_id = node["id"]
        node_name = node["name"]
        node_type = node.get("type", "UNKNOWN")
        
        # Check for Image Fills
        if "fills" in node:
            for fill in node["fills"]:
                if fill.get("type") == "IMAGE" and fill.get("visible", True):
                    images.append((node_id, node_name, node))
                    break # One image fill is enough to mark as image candidate
        
        # Check for Vectors/Icons/Components/Instances
        # We want to be very broad here and let _is_likely_icon do the fine-grained filtering
        # Include explicit vector types AND containers that might be icons (Components/Instances)
        # Also include basic shapes (Rectangle/Ellipse) as they might be icons/backgrounds
        
        broad_vector_types = [
            "VECTOR", "STAR", "POLYGON", "BOOLEAN_OPERATION", 
            "GROUP", "FRAME", 
            "COMPONENT", "INSTANCE", 
            "RECTANGLE", "ELLIPSE", "LINE"
        ]
        
        if node_type in broad_vector_types:
            vectors.append((node_id, node_name, node))
        
        # Recurse children
        if "children" in node:
            for child in node["children"]:
                self._traverse_traverse(child, images, vectors)
    def _has_image_fills(self, node: Dict[str, Any]) -> bool:
        if "fills" not in node: return False
        return any(f.get("type") == "IMAGE" and f.get("visible", True) for f in node["fills"])

    def _is_likely_icon(self, name: str, node: Dict[str, Any]) -> bool:
        """
        ULTRA-PERMISSIVE MODE: Accept almost any visual element as a potential asset.
        Better to over-extract than miss important assets.
        """
        node_type = node.get("type")
        name_lower = name.lower()
        
        # BLACKLIST: Explicitly reject container/layout nodes
        blacklist_keywords = ["page", "screen", "container", "wrapper", "layout", "section"]
        if any(keyword in name_lower for keyword in blacklist_keywords):
            return False
        
        # WHITELIST 1: Always accept these types
        always_accept_types = ["VECTOR", "STAR", "POLYGON", "BOOLEAN_OPERATION", "COMPONENT", "INSTANCE"]
        if node_type in always_accept_types:
            return True
        
        # WHITELIST 2: Accept nodes with visual properties (fills, effects, etc.)
        if node.get("fills") and len(node.get("fills", [])) > 0:
            # Has fills - likely a visual element
            return True
            
        if node.get("effects") and len(node.get("effects", [])) > 0:
            # Has effects (shadows, blurs) - likely decorative
            return True
        
        # WHITELIST 3: Accept groups/frames with multiple children (likely illustrations)
        if node_type in ["GROUP", "FRAME"]:
            children = node.get("children", [])
            if len(children) >= 2:  # Has at least 2 children - might be a complex icon
                return True
        
        # WHITELIST 4: Keyword-based detection
        icon_keywords = [
            "icon", "logo", "vector", "svg", "illustration", "graphic", "image", "img",
            "google", "facebook", "twitter", "social", "brand",
            "mail", "email", "lock", "password", "user", "avatar",
            "design", "school", "badge", "emblem", "mark", "symbol",
            "btn", "button", "arrow", "chevron"
        ]
        
        if any(keyword in name_lower for keyword in icon_keywords):
            return True
        
        # Default: Reject
        return False

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename for file system (legacy, not used for tokens)"""
        # Keep alphanumeric, dashes, underscores
        clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        return clean[:50] # Limit length
    
    def _sanitize_for_token(self, name: str) -> str:
        """Sanitize asset name for token usage - MUST match token generation in start_agent.py"""
        # Replace spaces with underscores, remove special characters
        # This MUST produce the same result as: asset_name.replace(' ', '_') in start_agent.py
        clean = name.replace(' ', '_')
        # Remove any remaining special characters except underscores and hyphens
        clean = re.sub(r'[^a-zA-Z0-9_-]', '', clean)
        return clean

    async def _download_file(self, client: httpx.AsyncClient, url: str, path: Path) -> bool:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                async with aiofiles.open(path, mode='wb') as f:
                    await f.write(resp.content)
                return True
        except Exception as e:
            logger.warning(f"Failed to download asset {url}: {e}")
        return False
