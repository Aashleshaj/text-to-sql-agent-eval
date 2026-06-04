import os
import sys
import json
import pytest
import re
import phoenix as px
from openai import OpenAI
from ragas.llms import llm_factory
from datasets import Dataset
from ragas import evaluate
from langchain_ollama import ChatOllama
from ragas.llms import LangchainLLMWrapper
# from ragas.metrics.collections import SQLSemanticEquivalence
# from ragas.metrics import LLMSQLEquivalence

# 1. --- PATH MANIPULATION MUST HAPPEN HERE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
main_folder_path = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, main_folder_path)
# ---------------------------------------------

# 2. --- NOW IT IS SAFE TO IMPORT LOCAL FILES ---
from agent import create_sql_deep_agent, init_tracing

# --- Helper Functions ---
def run_agent_test(agent, question: str):
    print(f"\n\n================ LIVE AGENT TRACE ================")
    
    current_state = None
    try:
        # Using stream_mode="values" yields the full graph state after every single step
        for step in agent.stream(
            {"messages": [{"role": "user", "content": question}]},
            # config={"recursion_limit": 40},
            stream_mode="values" 
        ):
            current_state = step
            messages = step.get("messages", [])
            
            if messages:
                last_msg = messages[-1]
                role = getattr(last_msg, "type", type(last_msg).__name__)
                content = getattr(last_msg, "content", "")
                
                print(f"\n[{role.upper()}] says:")
                if content:
                    print(f"{content}")
                
                # Print any tools the model tries to use
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"-> 🛠️ ATTEMPTING TO USE TOOL: {last_msg.tool_calls}")
                    
        print("==================================================\n")
        return current_state
        
    except Exception as e:
        print(f"\n[SYSTEM] ⚠️ Agent hit safety cutoff: {e}")
        print("==================================================\n")
        
        # If it crashes, return whatever thoughts we managed to capture before the crash!
        if current_state:
            return current_state
            
        return {"messages": [{"role": "assistant", "content": "Failed to resolve query."}]}
    
def extract_sql_and_answer(output_state: dict):
    """
    Parses the LangGraph state dictionary to extract the final natural 
    language answer and the actual SQLite query executed, with text fallback.
    """
    messages = output_state.get("messages", [])
    
    final_answer = ""
    executed_sql = ""
    
    if messages:
        final_message = messages[-1]
        final_answer = final_message.content if hasattr(final_message, "content") else str(final_message)
        
    # STRATEGY 1: Extract from formal tool calls (Standard LangChain behavior)
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "sql_db_query":
                    executed_sql = tool_call.get("args", {}).get("query", "")
                    if executed_sql:
                        return final_answer, executed_sql
                        
    # STRATEGY 2: Fallback parsing if the 4B model wrote SQL directly into the text
    for msg in messages:
        content = msg.content if hasattr(msg, "content") else str(msg)
        
        # Look for markdown blocks explicitly marked as SQL
        markdown_sql = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if markdown_sql:
            executed_sql = markdown_sql.group(1).strip()
            break
            
        # Look for generic markdown blocks containing a SELECT query
        generic_code = re.search(r"```\s*(SELECT.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if generic_code:
            executed_sql = generic_code.group(1).strip()
            break
            
        # Check if the plain text contains a raw unformatted SELECT statement
        if "select" in content.lower() and "from" in content.lower():
            raw_sql = re.search(r"(SELECT.*?;?)", content, re.DOTALL | re.IGNORECASE)
            if raw_sql:
                executed_sql = raw_sql.group(1).strip()
                break
                    
    return final_answer, executed_sql

def load_dataset():
    """Loads the synthetic test data."""
    file_path = os.path.join(os.path.dirname(__file__), "synthetic_tests.json")
    if not os.path.exists(file_path):
        pytest.skip("synthetic_tests.json not found. Run your generation script first.")
    
    with open(file_path, "r") as f:
        return json.load(f)

# --- Test Suite ---

@pytest.fixture(scope="function")
def agent():
    """Fixture to initialize the Deep Agent once per test run."""
    return create_sql_deep_agent()

@pytest.fixture(scope="session", autouse=True)
def manage_phoenix_lifecycle():
    """
    Starts the Phoenix server before any tests run, 
    and cleanly closes it after all tests finish to prevent Windows file lock errors.
    """
    init_tracing()
    yield  # The tests run here
    px.close_app()  # Gracefully release the lock on phoenix.db

@pytest.mark.parametrize("test_case", load_dataset())
def test_agent_text_to_sql(agent, test_case):
    """
    Evaluates the agent against a specific test case using Ragas.
    """
    # 1. Execute the agent pipeline
    output_state = run_agent_test(agent, test_case["question"])
    
    # 2. Extract the intermediate SQL and final answer
    actual_answer, generated_sql = extract_sql_and_answer(output_state)
    
    # --- DEBUG PRINT ---
    with open("agent_debug_logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"\n{'='*40}\n")
        log_file.write(f"QUESTION: {test_case['question']}\n")
        log_file.write(f"RAW AGENT RESPONSE: {actual_answer}\n")
        log_file.write(f"EXTRACTED SQL: '{generated_sql}'\n")
    # ----------------------------
  
    # Fallback assertion: Ensure the agent actually generated SQL
    assert generated_sql != "", f"Agent failed to generate any SQL for question: {test_case['question']}"

    # 3. Format for Ragas Dataset
    data = {
        "question": [test_case["question"]],
        "answer": [actual_answer],
        "ground_truth": [test_case["expected_answer"]],
        "response": [generated_sql],         
        "reference": [test_case["expected_sql"]],
        "reference_contexts": [["Chinook schema tables: Album, Artist, Customer, Employee, Genre, Invoice, InvoiceLine, MediaType, Playlist, PlaylistTrack, Track"]]  
    }
    dataset = Dataset.from_dict(data)

    # 4. Initialize the legacy Langchain wrapper (Removed format="json")
    ragas_llm = LangchainLLMWrapper(
        ChatOllama(
            model="qwen3-coder:30b-a3b-q4_K_M",
            base_url="http://192.168.1.157:11434",
            temperature=0
        )
    )

    # 5. Run Ragas Evaluation 
    from ragas.metrics import LLMSQLEquivalence
    metric = LLMSQLEquivalence()
    
    evaluation_result = evaluate(
        dataset=dataset,
        metrics=[metric],
        llm=ragas_llm
    )

    # 6. Extract scores
    scores = evaluation_result.to_pandas().iloc[0]
    sql_score = scores.get('llm_sql_equivalence', 0)
    
    # --- SMART BYPASS ---
    # If the queries match exactly, bypass the AI Judge and award a perfect score!
    expected_clean = test_case["expected_sql"].strip().lower()
    generated_clean = generated_sql.strip().lower()
    
    if expected_clean == generated_clean:
        sql_score = 1.0
    # --------------------

    print(f"\nGenerated SQL: {generated_sql}")
    print(f"SQL Score: {sql_score}")

    # --- SAVE TO DATAFRAME & CSV (BEFORE ASSERTION) ---
    import pandas as pd
    
    csv_file = "evaluation_results.csv"
    
    # Create a small DataFrame for this test case
    result_df = pd.DataFrame([{
        "Question": test_case["question"],
        "Expected_SQL": test_case["expected_sql"],
        "Generated_SQL": generated_sql,
        "Score": sql_score
    }])
    
    # Append it to the CSV file
    if not os.path.exists(csv_file):
        result_df.to_csv(csv_file, index=False)
    else:
        result_df.to_csv(csv_file, mode='a', header=False, index=False)
        
    print(f"✅ Saved result to {csv_file}")
    # --------------------------------------------------

    # 7. Finally, run the assertion!
    assert sql_score >= 0.8, f"SQL logic mismatch. Agent wrote: {generated_sql}"