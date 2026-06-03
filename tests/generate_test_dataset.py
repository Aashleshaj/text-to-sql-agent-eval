import json
import os
import sys
import re
import time
from langchain_ollama import ChatOllama
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
# from agent import create_sql_deep_agent
import phoenix as px

# Add the parent directory (project root) to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, project_root)

# --- IMPORT YOUR ACTUAL AGENT LOGIC ---
from agent import create_sql_deep_agent, init_tracing

def extract_sql_and_answer(output_state: dict):
    """Parses the LangGraph state to extract the final answer and executed SQL."""
    messages = output_state.get("messages", [])
    final_answer = ""
    executed_sql = ""
    
    if messages:
        final_message = messages[-1]
        final_answer = final_message.content if hasattr(final_message, "content") else str(final_message)
        
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "sql_db_query":
                    executed_sql = tool_call.get("args", {}).get("query", "")
                    
    return final_answer, executed_sql

def generate_synthetic_tests(num_cases=4):
    """Generates questions, then uses the real Agent to establish the ground truth."""
    
    print("[Tracing] Starting Phoenix server...")
    init_tracing()

    db_path = os.path.join(project_root, "chinook.db")
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
    schema = db.get_table_info()

    # Generator LLM: Only responsible for brainstorming creative questions
    llm = ChatOllama(
        model="nemotron-3-nano:4b", 
        temperature=0.8, # Keep high for creative question variety
        base_url="http://192.168.1.157:11434",
        num_ctx=32192,
        format="json"               
    )

    prompt = PromptTemplate.from_template("""
    You are a Senior QA Automation Engineer designing a rigorous test suite.
    Analyze this schema:
    {schema}

    Generate EXACTLY ONE natural language question about this database.
    CRITICAL: It MUST test a completely different concept than these: [{previous_questions}]

    COMPLEXITY (Rotate through these):
    - EASY: Basic retrieval. 1-2 tables.
    - MEDIUM: Analytical. 2-4 tables, JOINs, GROUP BY.
    

    EXAMPLE OUTPUT:
    {{
        "question": "Which customers spent more than $40 in total?"
    }}

    Return ONLY a valid JSON object with the exact key: "question". Do not write the SQL.
    """)
    chain = prompt | llm
    
    # Initialize your actual Deep Agent to solve the questions
    print("Initializing Deep Agent to generate ground truth SQL...")
    agent = create_sql_deep_agent() 

    test_cases = []
    previous_questions = []

    print(f"Starting generation of {num_cases} test cases...\n")
    
    for i in range(num_cases):
        print(f"[{i+1}/{num_cases}] Brainstorming question...")
        prev_q_str = " | ".join(previous_questions) if previous_questions else "None"
        
        try:
            # 1. Ask LLM to brainstorm a question
            response = chain.invoke({
                "schema": schema, 
                "previous_questions": prev_q_str
            })
            
            raw_text = response.content.strip()
            
            # --- BULLETPROOF JSON EXTRACTION ---
            # This regex finds the first '{' and the last '}' 
            # ignoring any markdown blocks or conversational text around it.
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            
            if match:
                clean_json = match.group(0)
                case = json.loads(clean_json)
            else:
                print("  -> Rejected: Could not find valid JSON in LLM response.")
                continue
            # -----------------------------------
            
            new_question = case.get("question", "")
            
            if new_question:
                print(f"  -> Question: {new_question}")
                print(f"  -> Asking Deep Agent to solve it...")
                
                # 2. RUN THE ACTUAL AGENT
                output_state = agent.invoke({"messages": [{"role": "user", "content": new_question}]})
                
                # 3. Extract what the agent did
                actual_answer, generated_sql = extract_sql_and_answer(output_state)
                
                if not generated_sql:
                    print("  -> Rejected: Agent failed to generate SQL for this question. Skipping.")
                    continue
                    
                # 4. Save as a verified test case
                test_case = {
                    "question": new_question,
                    "expected_sql": generated_sql,
                    "expected_answer": actual_answer
                }
                
                test_cases.append(test_case)
                previous_questions.append(new_question)
                print("  -> Success: Test case saved!\n")
            else:
                print("  -> Warning: Model failed to generate 'question' key.\n")
            time.sleep(3)    
        except Exception as e:
            print(f"  -> Failed iteration: {e}\n")
            
    file_path = os.path.join(os.path.dirname(__file__), "synthetic_tests.json")
    with open(file_path, "w") as f:
        json.dump(test_cases, f, indent=4)
        
    print(f"\nSuccessfully saved {len(test_cases)} verified test cases to 'synthetic_tests.json'")
    print("\n[Tracing] Waiting 5 seconds for background traces to flush...")
    time.sleep(5) # CRITICAL: Gives the background thread time to save the logs
    
    try:
        # Use the explicit Client to fetch from the local server we started
        client = px.Client() 
        df = client.get_spans_dataframe()
        
        if df is not None and not df.empty:
            df.to_csv("agent_traces.csv", index=False)
            print(f"[Tracing] Success! Saved {len(df)} trace events to agent_traces.csv")
        else:
            print("[Tracing] Warning: No traces found. Did the agent actually run?")
    except Exception as e:
        print(f"[Tracing] Failed to export logs: {e}")

if __name__ == "__main__":
    generate_synthetic_tests(num_cases=4)