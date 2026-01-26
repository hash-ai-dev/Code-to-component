import base64
import logging
import os
import tempfile
import zipfile
import io
from typing import Optional, Tuple
from fastapi import UploadFile

logger = logging.getLogger(__name__)

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/svg+xml", "application/zip", "application/x-zip-compressed"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".zip"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

class UploadHandler:
    """Handle file uploads for direct design input (bypasses Figma API)"""
    
    @staticmethod
    def validate_upload(file: UploadFile) -> Tuple[bool, Optional[str]]:
        """
        Validate uploaded file type and size.
        
        Returns:
            (is_valid, error_message)
        """
        # Check file extension
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        
        # Check content type
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            return False, f"Invalid content type: {file.content_type}"
        
        return True, None
    
    @staticmethod
    async def process_image_upload(file: UploadFile) -> Tuple[str, dict]:
        """
        Process uploaded image (PNG/JPG) and convert to base64 data URI.
        
        Args:
            file: Uploaded image file
            
        Returns:
            (main_image_uri, assets_dict) - assets_dict is empty for single image
        """
        try:
            # Read file content
            content = await file.read()
            
            # Check file size (raw)
            if len(content) > MAX_FILE_SIZE:
                 raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            # OPTIMIZE IMAGE WITH PILLOW (Check for API limits)
            try:
                from PIL import Image
                import io
                
                # Open image
                img = Image.open(io.BytesIO(content))
                
                # Resize if too large (max 2048px on longest side)
                max_dim = 2048
                if max(img.size) > max_dim:
                    ratio = max_dim / max(img.size)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    logger.info(f"📉 Resized image from {img.width/ratio:.0f}x{img.height/ratio:.0f} to {img.size}")
                
                # Convert to RGB if needed (handle transparency separately)
                output_buffer = io.BytesIO()
                
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                     # Keep PNG for transparency
                     img.save(output_buffer, format="PNG", optimize=True)
                     mime_type = "image/png"
                else:
                     # Convert to JPEG for better compression
                     img = img.convert("RGB")
                     img.save(output_buffer, format="JPEG", quality=85)
                     mime_type = "image/jpeg"
                
                # Use optimized content
                content = output_buffer.getvalue()
                logger.info(f"✅ Optimized image size: {len(content)/1024:.1f} KB")
                
            except ImportError:
                 logger.warning("⚠️ Pillow not installed - skipping image optimization. Large images may fail API.")
                 mime_type = file.content_type or "image/png"
            except Exception as e:
                 logger.warning(f"⚠️ Image optimization failed: {e} - using original file.")
                 mime_type = file.content_type or "image/png"

            # Convert to base64
            base64_data = base64.b64encode(content).decode('utf-8')
            
            # Create data URI
            data_uri = f"data:{mime_type};base64,{base64_data}"
            
            logger.info(f"✅ Processed image upload: {file.filename} ({len(content)} bytes)")
            
            # For single image upload, logic treats it as Main Design with NO assets
            return data_uri, {}
            
        except Exception as e:
            logger.error(f"❌ Failed to process image upload: {str(e)}")
            raise
    
    @staticmethod
    async def process_svg_upload(file: UploadFile) -> Tuple[str, dict]:
        """
        Process uploaded SVG file and convert to base64 data URI.
        
        Returns:
            (main_image_uri, assets_dict)
        """
        try:
            # Read SVG content as text
            content = await file.read()
            
            # Check file size for SVG specifically
            MAX_SVG_SIZE = 3 * 1024 * 1024 # 3MB
            
            if len(content) > MAX_SVG_SIZE:
                size_mb = len(content) / (1024 * 1024)
                raise ValueError(
                    f"This SVG is too complex for AI analysis ({size_mb:.1f}MB). "
                    "Please export it as a PNG image from Figma and upload that instead."
                )
            
            # Check overall file size (safety)
            if len(content) > MAX_FILE_SIZE:
                 raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            # Convert to base64
            base64_data = base64.b64encode(content).decode('utf-8')
            
            # Create data URI for SVG
            data_uri = f"data:image/svg+xml;base64,{base64_data}"
            
            logger.info(f"✅ Processed SVG upload: {file.filename} ({len(content)} bytes)")
            
            return data_uri, {}
            
        except Exception as e:
            logger.error(f"❌ Failed to process SVG upload: {str(e)}")
            raise
    
    @staticmethod
    async def process_upload(file: UploadFile, input_type: str) -> Tuple[str, dict]:
        """
        Process uploaded file based on input type.
        """
        # Validate first
        is_valid, error = UploadHandler.validate_upload(file)
        if not is_valid:
            raise ValueError(error)
            
        # AUTO-DETECT ZIP based on extension override
        filename = file.filename or ""
        if filename.lower().endswith(".zip") and input_type != "zip":
            logger.info("⚠️ Auto-detected ZIP file despite incorrect input_type. Switching to ZIP mode.")
            input_type = "zip"
        
        # Process based on type
        if input_type == "zip":
            return await UploadHandler.process_zip_upload(file)
        elif input_type == "svg":
            return await UploadHandler.process_svg_upload(file)
        else:  # image (png/jpg)
            return await UploadHandler.process_image_upload(file)
    
    @staticmethod
    async def process_zip_upload(file: UploadFile) -> Tuple[str, dict]:
        """
        Extract ALL images from ZIP, identify 'Main Design', and return rest as assets.
        """
        try:
            # Read ZIP content
            content = await file.read()
            
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB")
            
            extracted_images = [] # List of (filename, data_uri, size_bytes)
            
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                image_extensions = ('.png', '.jpg', '.jpeg', '.svg')
                all_files = zf.namelist()
                logger.info(f"📦 ZIP contains {len(all_files)} files: {all_files}")
                
                for filename in all_files:
                    if filename.endswith('/') or filename.startswith('.') or "__MACOSX" in filename:
                        continue
                    
                    if filename.lower().endswith(image_extensions):
                        image_data = zf.read(filename)
                        
                        # Determine MIME
                        ext = os.path.splitext(filename)[1].lower()
                        if ext == '.png': mime_type = 'image/png'
                        elif ext in ['.jpg', '.jpeg']: mime_type = 'image/jpeg'
                        elif ext == '.svg': mime_type = 'image/svg+xml'
                        else: continue
                        
                        b64_data = base64.b64encode(image_data).decode('utf-8')
                        data_uri = f"data:{mime_type};base64,{b64_data}"
                        
                        extracted_images.append({
                            "name": filename,
                            "uri": data_uri,
                            "size": len(image_data)
                        })
                        logger.info(f"   found valid asset: {filename} ({len(image_data)} bytes)")
            
            if not extracted_images:
                raise ValueError(f"No valid images found in ZIP. Files found: {all_files}")
            
            # Logic to identify MAIN VS ASSETS
            main_image = None
            assets = {}
            
            # 1. Look for explicit "Main_Design" or "Main" naming
            for img in extracted_images:
                name_lower = img["name"].lower()
                if "main" in name_lower or "design" in name_lower or "preview" in name_lower or "screenshot" in name_lower:
                    main_image = img
                    break
            
            # 2. If no explicit name, pick the LARGEST file (most likely the full page screenshot)
            if not main_image:
                main_image = max(extracted_images, key=lambda x: x["size"])
                logger.info(f"   ℹ️ No file named 'Main_Design' found. Selected largest file as Main: {main_image['name']}")
                
            # Pop main image from the list so the rest become assets
            # We create the assets dict now
            for img in extracted_images:
                if img == main_image:
                    continue
                
                # Sanitize name for asset key (remove extension)
                nice_name = os.path.splitext(os.path.basename(img["name"]))[0]
                nice_name = nice_name.replace(" ", "_").replace("-", "_")
                
                # Key format compatible with Agent assets
                key = f"{nice_name}"
                assets[key] = img["uri"]
            
            logger.info(f"✅ ZIP Processed: Main='{main_image['name']}' ({len(main_image['uri'])} chars), Assets={list(assets.keys())}")
            
            return main_image["uri"], assets

        except zipfile.BadZipFile:
            logger.error("❌ Invalid ZIP file")
            raise ValueError("Invalid ZIP file format")
        except Exception as e:
            logger.error(f"❌ Failed to process ZIP upload: {str(e)}")
            raise
