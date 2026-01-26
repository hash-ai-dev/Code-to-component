import httpx
import os
import logging
import time
import asyncio
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class FigmaClient:
    def __init__(self, token: Optional[str] = None):
        self.token = (token or os.getenv("FIGMA_API_TOKEN") or "").strip()
        self.base_url = "https://api.figma.com/v1"
        self.common_headers = {
            "X-Figma-Token": self.token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def get_node(self, file_key: str, node_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Fetch a specific node from a Figma file."""
        auth_token = (token or self.token or "").strip()
        if not auth_token:
            logger.error("❌ Figma Token is missing")
            raise ValueError("Figma Token is missing")
        
        logger.info(f"🔍 Fetching Figma node: {node_id[:20]}...")
        start_time = time.time()
        
        headers = self.common_headers.copy()
        headers["X-Figma-Token"] = auth_token
        
        url = f"{self.base_url}/files/{file_key}/nodes?ids={node_id}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                nodes = data.get("nodes", {})
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                if node_id in nodes:
                    node_data = nodes[node_id]["document"]
                    logger.info(f"✅ Node data fetched successfully in {duration_ms}ms")
                    logger.debug(f"   Node type: {node_data.get('type', 'unknown')}")
                    return node_data
                else:
                    logger.warning(f"⚠️  Node {node_id} not found in response")
                    return {}
                    
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Figma API Error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Figma API returned {e.response.status_code}: {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Error fetching Figma node: {str(e)}")
            raise

    async def get_image_url(self, file_key: str, node_id: str, token: Optional[str] = None) -> str:
        """Get the export URL for a node image (PNG)."""
        auth_token = token or self.token
        
        logger.info(f"🖼️  Generating image URL for node: {node_id[:20]}...")
        start_time = time.time()
        
        headers = self.common_headers.copy()
        headers["X-Figma-Token"] = auth_token
        
        url = f"{self.base_url}/images/{file_key}?ids={node_id}&format=png&scale=2&use_absolute_bounds=true"
        
        try:
            # Increased timeout for complex nodes that take longer to render
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                images = data.get("images", {})
                image_url = images.get(node_id, "")
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                if image_url:
                    logger.info(f"✅ Image URL generated in {duration_ms}ms")
                else:
                    logger.warning(f"⚠️  No image URL returned for node {node_id}")
                
                return image_url
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Figma Image API Error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Figma Image API returned {e.response.status_code}: {e.response.text}")
        except Exception as e:
            logger.error(f"❌ Error generating image URL: {repr(e)}")
            raise

    async def get_first_frame(self, file_key: str, token: Optional[str] = None) -> Optional[str]:
        """Auto-discover the first Frame node in the file."""
        auth_token = token or self.token
        logger.info(f"🔍 Auto-discovering first frame for file: {file_key}...")
        
        headers = self.common_headers.copy()
        headers["X-Figma-Token"] = auth_token
        
        # depth=2 is enough to get Pages -> Frames
        url = f"{self.base_url}/files/{file_key}?depth=2"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                document = data.get("document", {})
                pages = document.get("children", [])
                
                for page in pages:
                    # Look for Frames (type="FRAME" or "COMPONENT" or "SECTION")
                    for node in page.get("children", []):
                        if node.get("type") in ["FRAME", "COMPONENT", "SECTION", "INSTANCE"]:
                            node_id = node["id"]
                            node_name = node["name"]
                            logger.info(f"✅ Found candidate frame: '{node_name}' (ID: {node_id})")
                            return node_id
                            
                logger.warning("⚠️  No top-level Frames found in the first few pages")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error during auto-discovery: {str(e)}")
            return None

    async def get_images_batch(self, file_key: str, node_ids: list[str], format: str = "png", scale: int = 2, token: Optional[str] = None) -> Dict[str, str]:
        """
        Batch export images/SVGs for multiple node IDs.
        Returns a dictionary: {node_id: image_url}
        
        Splits large batches into chunks to avoid 403 errors from Figma API.
        """
        if not node_ids:
            return {}
            
        auth_token = (token or self.token or "").strip()
        
        logger.info(f"🖼️  Batch exporting {len(node_ids)} assets ({format})...")
        
        headers = self.common_headers.copy()
        headers["X-Figma-Token"] = auth_token
        
        # Split into chunks of 20 to avoid API limits
        CHUNK_SIZE = 20
        all_results = {}
        
        for i in range(0, len(node_ids), CHUNK_SIZE):
            chunk = node_ids[i:i+CHUNK_SIZE]
            ids_str = ",".join(chunk)
            
            logger.info(f"   📦 Processing chunk {i//CHUNK_SIZE + 1}/{(len(node_ids)-1)//CHUNK_SIZE + 1} ({len(chunk)} assets)...")
            
            url = f"{self.base_url}/images/{file_key}?ids={ids_str}&format={format}&scale={scale}&use_absolute_bounds=true"
            
            try:
                # Retry loop for 429 Rate Limits
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        async with httpx.AsyncClient(timeout=45.0) as client:
                            response = await client.get(url, headers=headers)
                            
                            if response.status_code == 429:
                                # Rate Limit Hit - Wait and Retry
                                raw_retry = response.headers.get("Retry-After", "5")
                                try:
                                    header_wait = int(float(raw_retry))
                                except:
                                    header_wait = 5
                                    
                                # Exponential backoff but CAP at 30 seconds to avoid hanging
                                wait_time = min(header_wait + (2 ** attempt), 30)
                                
                                logger.warning(f"⏳ Rate limit hit (Retry-After: {raw_retry}). Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                                await asyncio.sleep(wait_time)
                                continue
                                
                            response.raise_for_status()
                            data = response.json()
                            chunk_results = data.get("images", {})
                            all_results.update(chunk_results)
                            logger.info(f"   ✅ Chunk {i//CHUNK_SIZE + 1} complete: {len(chunk_results)} URLs retrieved")
                            break # Success - exit retry loop
                            
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                             # Should be handled by if block above, but double safety
                             continue
                        logger.error(f"❌ Chunk {i//CHUNK_SIZE + 1} failed: {e.response.status_code} - {e.response.text[:200]}")
                        break # Non-retriable error
                    except Exception as e:
                        logger.error(f"❌ Chunk {i//CHUNK_SIZE + 1} attempt {attempt+1} error: {str(e)}")
                        if attempt == max_retries - 1:
                            break
                        await asyncio.sleep(2) # Brief wait on generic error
            
                # Small delay between chunks to be nice to the API
                if i + CHUNK_SIZE < len(node_ids):
                    await asyncio.sleep(1.0)
                        
            except Exception as e:
                logger.error(f"❌ Chunk {i//CHUNK_SIZE + 1} failed completely: {str(e)}")
                continue
        
        logger.info(f"✅ Batch export complete: {len(all_results)}/{len(node_ids)} assets exported successfully")
        return all_results
