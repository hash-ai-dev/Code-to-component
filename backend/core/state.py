from typing import List, Optional, TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Inputs
    figma_file_key: str
    figma_node_id: str
    figma_image_url: str
    figma_token: str
    hf_token: str
    session_id: Optional[str]
    
    # Upload mode support
    input_mode: str  # "figma_url" or "upload"
    skip_extraction: bool  # True if upload mode (skip Figma API calls)
    uploaded_assets: Optional[dict] # {name: data_uri} passed from upload handler
    
    # Internal State
    messages: Annotated[List[dict], add_messages]
    technical_specs: Optional[dict]
    generated_code: Optional[str]
    test_results: Optional[dict]
    extracted_assets: Optional[dict] # {original_name: local_path}
    retry_count: int
    
    # Outputs
    final_output: Optional[str]
    error: Optional[str]

def calculate_progress(phase: str, sub_progress: float) -> float:
    """Calculates overall progress (0-1) based on phase and sub-task progress."""
    phase_weights = {
        "extraction": 0.1,
        "architect": 0.2,
        "developer": 0.5,
        "tester": 0.2
    }
    
    base_progress = 0.0
    for p, weight in phase_weights.items():
        if p == phase:
            return round(base_progress + (weight * sub_progress), 2)
        base_progress += weight
        
    return 1.0
