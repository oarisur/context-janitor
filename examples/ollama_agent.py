import ollama
import json
import time
from context_janitor.selection import select_resilient
from context_janitor.models import load_tools

# 1. THE MESSY CATALOG
my_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a specific city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}}
            }
        }
    }
]

# Add 20 distractors to prove the Janitor works
for i in range(20):
    my_tools.append({
        "type": "function",
        "function": {
            "name": f"legacy_system_{i}", 
            "description": f"Do not use. Internal legacy tool {i}."
        }
    })

prompt = "Can you tell me the weather in Tokyo?"

def run_agent():
    print("🧹 1. Context Janitor is pruning the catalog...")
    
    start_janitor = time.time()
    result = select_resilient(
        provider="heuristic",
        prompt=prompt,
        tools=load_tools(my_tools),
        limit=2 
    )
    janitor_ms = (time.time() - start_janitor) * 1000
    
    kept_tool_names = [tool.name for tool in result.selected]
    pruned_tools = [t for t in my_tools if t["function"]["name"] in kept_tool_names]
    
    print(f"✅ Pruned from {len(my_tools)} tools down to {len(pruned_tools)} in {janitor_ms:.2f}ms.")
    print(f"   Kept: {kept_tool_names}\n")
    
    print(f"🤖 2. Sending to Ollama (qwen2.5-coder:3b)...")
    
    try:
        response = ollama.chat(
            model='qwen2.5-coder:3b-instruct-q4_K_M', 
            messages=[{'role': 'user', 'content': prompt}],
            tools=pruned_tools
        )
        
        print("\n🎯 Ollama Response:")
        msg = response['message']
        content = msg.get('content', '')

        # SUCCESS PATH A: Native Tool Call
        if msg.get('tool_calls'):
            print("STATUS: Native Tool Call Detected")
            for tool in msg['tool_calls']:
                print(f"-> Tool: {tool['function']['name']}")
                print(f"-> Args: {tool['function']['arguments']}")
        
        # SUCCESS PATH B: Manual JSON Fallback (Common for small local models)
        elif "{" in content and "name" in content:
            print("STATUS: Manual JSON Fallback Triggered")
            # Strip potential markdown backticks
            clean_json = content.replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(clean_json)
                print(f"-> Tool: {data.get('name')}")
                print(f"-> Args: {data.get('arguments')}")
            except json.JSONDecodeError:
                print(f"-> Error: Model sent malformed JSON: {content}")
        
        # NEUTRAL PATH: Just text
        else:
            print(f"STATUS: Plain Text Response")
            print(f"-> Content: {content}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    run_agent()