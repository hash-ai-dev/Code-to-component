import os
import re
import sys

# Define mock assets (Real Data URIs for testing)
MOCK_ASSETS = {
    "Google Logo": "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0Ij48cGF0aCBmaWxsPSIjNDI4NUY0IiBkPSJNMjIuNTYgMTIuMjVjMC0uNzgtLjA3LTEuNTMtLjItMi4yNUgxMnY0LjI2aDUuOTJjLS4yNiAxLjM3LTEuMDQgMi41My0yLjIxIDMuMzF2Mi43N2g0LjU3YzIuMDgtMS45MiAzLjI4LTQuNzQgMy4yOC04LjA5eiIvPjxwYXRoIGZpbGw9IiMzNEE4NTMiIGQ9Ik0xMiAyM2M0LjI1IDAgNy44MS0xLjQxIDEwLjQxLTMuODFsLTUuMDgtMy45NGMtMS40MS45NS0zLjIxIDEuNTEtNS4zMyAxLjUxLTQuMSAwLTcuNTctMi43Ny04LjgxLTYuNUgxLjY0djQuMDZDNC4xOSAyMC41MyA3LjcgMjMgMTIgMjN6Ii8+PHBhdGggZmlsbD0iI0ZCQkMwNSIgZD0iTTMuMTkgMTQuMjZjLS4zMS0uOTUtLjQ5LTEuOTctLjQ5LTMuMDFzLjE4LTIuMDYuNDktMy4wMVY0LjE4SDEuNjRDLjU5IDYuMjggMCA4LjU5IDAgMTEuMjVzLjU5IDQuOTcgMS42NCA3LjA3bDEuNTUtNC4wNnoiLz48cGF0aCBmaWxsPSIjRUE0MzM1IiBkPSJNMTIgNC43NWMxLjc3IDAgMy4zNS42MSA0LjYgMS44bC0zLjQ1IDMuNDVjLS45NS0uOTUtMi4yNi0xLjUtMy43Ni0xLjUtNC4xIDAtNy41NyAyLjc3LTguODEgNi41TDEuNjQgNC4xOEMyLjE5IDIuNTMgNy43IDQuNzUgMTIgNC43NXoiLz48L3N2Zz4=",
    "Test Icon": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
}

# Define mock code with TOKENS (Simulating LLM output)
MOCK_CODE = """
import React from 'react';

export default function AssetPipelineTest() {
  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>🛠️ Asset Pipeline Verification</h1>
      <p>This component tests if ##ASSET:Token## replacement works correctly.</p>
      
      <div style={{ display: 'flex', gap: '20px', marginTop: '20px' }}>
        <div style={{ border: '1px solid #ccc', padding: '10px' }}>
          <h3>Google Logo</h3>
          <img src="##ASSET:Google_Logo##" alt="Google Logo" style={{ width: 48, height: 48 }} />
        </div>
        
        <div style={{ border: '1px solid #ccc', padding: '10px' }}>
          <h3>Test Icon (Red Pixel)</h3>
          <img src="##ASSET:Test_Icon##" alt="Test Icon" style={{ width: 48, height: 48, imageRendering: 'pixelated' }} />
        </div>
      </div>
    </div>
  );
}
"""

def verify_pipeline():
    print("🚀 Starting Asset Pipeline Verification...")
    print(f"📦 Loaded {len(MOCK_ASSETS)} mock assets")
    
    code = MOCK_CODE
    replaced_count = 0
    
    # --- REPLACEMENT LOGIC (Mirrors start_agent.py) ---
    print("🔄 Running Token Replacement Logic...")
    for asset_name, data_uri in MOCK_ASSETS.items():
        token = f"##ASSET:{asset_name.replace(' ', '_')}##"
        
        if token in code:
            print(f"   ✅ Found token: {token}")
            code = code.replace(token, data_uri)
            replaced_count += 1
        else:
            print(f"   ⚠️ Token not found in code: {token}")
            
    # --------------------------------------------------
    
    if replaced_count == 2:
        print(f"✅ SUCCESS: Replaced {replaced_count}/2 tokens")
    else:
        print(f"❌ FAILURE: Only replaced {replaced_count}/2 tokens")
        sys.exit(1)
        
    # Check if Data URI is present
    if "data:image/svg+xml;base64" in code:
        print("✅ Verified Data URI is present in code")
    else:
        print("❌ Data URI missing from final code")
        sys.exit(1)

    # Correct path assuming script is run from project root or backend/tests
    # We'll use absolute logic based on this file's location to be safe
    current_file_dir = os.path.dirname(os.path.abspath(__file__)) # .../backend/tests
    project_root = os.path.dirname(os.path.dirname(current_file_dir)) # .../Codetocomponent
    output_dir = os.path.join(project_root, "frontend", "src", "stories", "generated")
    output_file = os.path.join(output_dir, "AssetPipelineTest.tsx")
    
    # Ensure directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(code)
        
    print(f"💾 Saved verification component to: {output_file}")
    print("\n🎉 VERIFICATION COMPLETE! You can now check the component in your browser/Sandpack.")

if __name__ == "__main__":
    verify_pipeline()
