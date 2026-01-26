from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Figma to Storybook Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 Figma to Storybook Agent API Starting...")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("=" * 60)
    logger.info("🛑 Figma to Storybook Agent API Shutting Down...")
    logger.info("=" * 60)

@app.get("/")
async def root():
    return {"message": "Figma to Storybook Agent API is running"}

@app.get("/health")
async def health_check():
    logger.debug("Health check requested")
    return {"status": "ok"}

from core.start_agent import app_graph
from services.figma_client import FigmaClient
from services.llm_client import LLMClient
from services.upload_handler import UploadHandler
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from fastapi import UploadFile, File, Form
import asyncio
import json

# Global queue for streaming logs
log_queues = {}

class GenerateRequest(BaseModel):
    figma_url: str
    figma_token: str
    hf_token: str

async def log_stream(session_id: str):
    """SSE stream for agent logs"""
    # Get the existing queue (created in /generate endpoint)
    queue = log_queues.get(session_id)
    
    if not queue:
        logger.error(f"❌ No queue found for session: {session_id[:8]}... (SSE connected too late or session expired)")
        # Create a temporary queue and send error
        queue = asyncio.Queue()
        await queue.put({
            "role": "error",
            "content": "Session not found or expired. Please try generating again.",
            "level": "error",
            "progress": 0,
            "phase": "error",
            "timestamp": "",
            "metadata": {}
        })
        await queue.put("DONE")
    
    logger.info(f"📡 SSE stream opened for session: {session_id[:8]}...")
    
    try:
        while True:
            log = await queue.get()
            if log == "DONE":
                logger.info(f"📡 SSE stream closing for session: {session_id[:8]}...")
                break
            yield f"data: {json.dumps(log)}\n\n"
    finally:
        if session_id in log_queues:
            del log_queues[session_id]

@app.get("/stream/{session_id}")
async def stream_logs(session_id: str):
    """SSE endpoint for real-time agent logs"""
    logger.info(f"📡 New SSE connection for session: {session_id[:8]}...")
    return StreamingResponse(
        log_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/generate")
async def generate_component(request: GenerateRequest):
    logger.info("=" * 60)
    logger.info("📥 NEW GENERATION REQUEST RECEIVED")
    logger.info("=" * 60)
    
    # Validate credentials are provided from UI
    if not request.figma_token or not request.hf_token:
        error_msg = (
            "Missing credentials. Please configure your API keys in the UI Settings modal:\n"
            "1. Click the Settings button\n"
            "2. Enter your Figma Access Token\n"
            "3. Enter your OpenRouter API Key\n"
            "4. Click Save & Close"
        )
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg, "session_id": None}
    
    logger.info(f"🔑 Figma Token starts with: {request.figma_token[:10]}...")
    logger.info(f"🔑 OpenRouter Key starts with: {request.hf_token[:10]}...")
    
    # STEP 1: Parse Figma URL (no API calls yet)
    # Figma has two URL formats:
    # Old: https://www.figma.com/file/KEY/Title?node-id=ID
    # New: https://www.figma.com/design/KEY/Title?node-id=ID
    try:
        # Check if URL contains figma.com with either /file/ or /design/
        if "figma.com/file/" in request.figma_url:
            parts = request.figma_url.split("figma.com/file/")[1].split("/")
        elif "figma.com/design/" in request.figma_url:
            parts = request.figma_url.split("figma.com/design/")[1].split("/")
        elif "figma.com/proto/" in request.figma_url:
            parts = request.figma_url.split("figma.com/proto/")[1].split("/")
        else:
            raise ValueError("URL must contain 'figma.com/file/', 'figma.com/design/', or 'figma.com/proto/'")
        
        file_key = parts[0]
        
        # Check if URL contains node-id parameter
        node_id = None
        if "node-id=" in request.figma_url:
            # node-id query param exists
            # Figma API expects ':', URL often provides '-' or '%3A'
            node_id = request.figma_url.split("node-id=")[1].split("&")[0].replace("%3A", ":").replace("-", ":")
            logger.info(f"📋 Parsed Figma URL:")
            logger.info(f"   File Key: {file_key[:15]}...")
            logger.info(f"   Node ID: {node_id[:20]}...")
        else:
            # No node-id found - will need auto-discovery AFTER validation
            logger.info(f"📋 Parsed Figma URL:")
            logger.info(f"   File Key: {file_key[:15]}...")
            logger.info(f"   Node ID: Missing (will auto-discover after validation)")
        
    except Exception as e:
        error_msg = f"Invalid Figma URL format: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg, "session_id": None}


    # STEP 2: Pre-flight Check - TEMPORARILY DISABLED
    logger.info("🛑️ Skipping pre-flight check - will validate during generation...")
    # try:
    #     llm_check = LLMClient(token=request.hf_token)
    #     if not llm_check.validate_connection(token=request.hf_token):
    #         error_msg = "Pre-flight check failed: Hugging Face API is not reachable or token is invalid. Figma limits preserved."
    #         logger.error(f"❌ {error_msg}")
    #         return {"error": error_msg, "session_id": None}
    #     logger.info("✅ Pre-flight Checks Passed: Agents are ready.")
    # except Exception as e:
    #     error_msg = f"Pre-flight check error: {str(e)}"
    #     logger.error(f"❌ {error_msg}")
    #     return {"error": error_msg, "session_id": None}

    # STEP 3: Auto-discovery (only if needed and AFTER validation)
    if node_id is None:
        try:
            logger.info("🔍 URL missing node-id. Attempting auto-discovery...")
            client = FigmaClient(token=request.figma_token)
            found_id = await client.get_first_frame(file_key)
            
            if found_id:
                node_id = found_id
                logger.info(f"✅ Auto-discovery success! Using found node: {node_id}")
            else:
                raise ValueError("URL is missing 'node-id=' and auto-discovery failed to find any frames. Please SELECT a layer in Figma and copy the link.")
        except Exception as e:
            error_msg = f"Auto-discovery failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"error": error_msg, "session_id": None}


    import uuid
    session_id = str(uuid.uuid4())
    
    logger.info(f"🆔 Session ID: {session_id}")
    
    # Create the queue BEFORE starting the agent task to avoid race condition
    queue = asyncio.Queue()
    log_queues[session_id] = queue
    logger.info(f"📦 Created log queue for session: {session_id[:8]}...")

    inputs = {
        "figma_file_key": file_key,
        "figma_node_id": node_id,
        "figma_image_url": "",
        "figma_token": request.figma_token.strip(),
        "hf_token": request.hf_token.strip(),
        "retry_count": 0,
        "messages": [],
        "session_id": session_id,  # Pass session ID for logging
        "input_mode": "figma_url",  # Figma URL mode
        "skip_extraction": False     # Use Figma API extraction
    }
    
    # Run the graph in background
    logger.info(f"🚀 Starting agent pipeline in background...")
    asyncio.create_task(run_agent_with_logging(inputs, session_id))
    
    return {"session_id": session_id}

@app.post("/generate-from-upload")
async def generate_from_upload(
    file: UploadFile = File(...),
    hf_token: str = Form(...),
    input_type: str = Form(...)  # "image", "svg", or "zip"
):
    logger.info("=" * 60)
    logger.info("📥 NEW UPLOAD REQUEST RECEIVED")
    logger.info(f"📎 File: {file.filename}")
    logger.info(f"📋 Type: {input_type}")
    logger.info("=" * 60)
    
    # Validate credentials
    if not hf_token:
        error_msg = (
            "Missing OpenRouter API Key. Please configure it in the UI Settings modal:\n"
            "1. Click the Settings button\n"
            "2. Enter your OpenRouter API Key\n"
            "3. Click Save & Close"
        )
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg, "session_id": None}
    
    logger.info(f"🔑 OpenRouter Key starts with: {hf_token[:10]}...")
    
    try:
        # Process uploaded file
        logger.info("📦 Processing uploaded file (Debug Info)...")
        logger.info(f"   - Filename: {file.filename}")
        logger.info(f"   - Content-Type: {file.content_type}")
        logger.info(f"   - Input Type (Frontend): {input_type}")
        
        image_data_uri, uploaded_assets = await UploadHandler.process_upload(file, input_type)
        logger.info(f"✅ File processed successfully (Main Image: {len(image_data_uri)} chars, Assets: {len(uploaded_assets)})")
        
    
        # Pre-flight check for LLM (TEMPORARILY DISABLED - will validate during actual calls)
        logger.info("🛑️ Skipping pre-flight check - will validate during generation...")
        # try:
        #     llm_check = LLMClient(token=hf_token)
        #     if not llm_check.validate_connection(token=hf_token):
        #         error_msg = "Pre-flight check failed: OpenRouter API is not reachable or token is invalid."
        #         logger.error(f"❌ {error_msg}")
        #         return {"error": error_msg, "session_id": None}
        #     logger.info("✅ Pre-flight Checks Passed: Agents are ready.")
        # except Exception as e:
        #     error_msg = f"Pre-flight check error: {str(e)}"
        #     logger.error(f"❌ {error_msg}")
        #     return {"error": error_msg, "session_id": None}
        
        
        # Create session
        import uuid
        session_id = str(uuid.uuid4())
        logger.info(f"🆔 Session ID: {session_id}")
        
        # Create log queue
        queue = asyncio.Queue()
        log_queues[session_id] = queue
        logger.info(f"📦 Created log queue for session: {session_id[:8]}...")
        
        # Prepare inputs for agent pipeline (UPLOAD MODE)
        inputs = {
            "figma_file_key": "",  # Not used in upload mode
            "figma_node_id": "",   # Not used in upload mode
            "figma_image_url": image_data_uri,  # Use uploaded image
            "uploaded_assets": uploaded_assets, # Pass extracted assets
            "figma_token": "",     # Not needed in upload mode
            "hf_token": hf_token,
            "retry_count": 0,
            "messages": [],
            "session_id": session_id,
            "input_mode": "upload",
            "skip_extraction": True  # Skip Figma API extraction
        }
        
        # Run the graph in background
        logger.info(f"🚀 Starting agent pipeline in UPLOAD mode (bypassing Figma API)...")
        asyncio.create_task(run_agent_with_logging(inputs, session_id))
        
        return {"session_id": session_id}
        
    except ValueError as e:
        error_msg = f"Upload validation error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg, "session_id": None}
    except Exception as e:
        error_msg = f"Upload processing error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg, "session_id": None}

async def run_agent_with_logging(inputs, session_id):
    """Run agent graph and stream logs"""
    queue = log_queues.get(session_id)
    if not queue:
        logger.error(f"❌ No queue found for session: {session_id}")
        return
    
    try:
        # Send initial log
        await queue.put({
            "role": "system",
            "content": "🚀 Starting Agent Pipeline...",
            "level": "info",
            "progress": 0,
            "phase": "initialization",
            "timestamp": "",
            "metadata": {}
        })
        
        logger.info(f"🏃 Running agent graph for session: {session_id[:8]}...")
        
        # Run graph with streaming
        final_state = await app_graph.ainvoke(inputs)
        
        logger.info(f"✅ Agent pipeline completed for session: {session_id[:8]}...")
        
        # Send final result
        await queue.put({
            "role": "result",
            "content": json.dumps({
                "code": final_state.get("generated_code"),
                "specs": final_state.get("technical_specs"),
                "test_results": final_state.get("test_results"),
                "stories": final_state.get("final_output"),
                "status": "completed" if final_state.get("test_results", {}).get("status") == "PASS" else "failed_with_code"
            }),
            "level": "success",
            "progress": 100,
            "phase": "complete",
            "timestamp": "",
            "metadata": {}
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Agent pipeline error for session {session_id[:8]}...: {error_msg}")
        await queue.put({
            "role": "error",
            "content": f"Error: {error_msg}",
            "level": "error",
            "progress": 0,
            "phase": "error",
            "timestamp": "",
            "metadata": {"error": error_msg}
        })
    finally:
        await queue.put("DONE")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
