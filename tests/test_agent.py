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
from ragas.metrics.collections import SQLSemanticEquivalence

# 1. --- PATH MANIPULATION MUST HAPPEN HERE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
main_folder_path = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, main_folder_path)
# ---------------------------------------------

# 2. --- NOW IT IS SAFE TO IMPORT LOCAL FILES ---
from agent import create_sql_deep_agent, init_tracing

# --- Helper Functions ---
def run_agent_test(agent, question: str):
    """Programmatic invocation for the test framework."""
    try:
        # Enforce an 12-thought limit so a bad query can't freeze your entire test session
        return agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"recursion_limit": 12}
        )
    except Exception as e:
        print(f"\n  -> ⚠️ Test Agent hit safety cutoff or loop limit: {e}")
        # Return a dummy state so the script can gracefully fail the assertion and move to the next test
        return {"messages": [{"role": "assistant", "content": "Failed to resolve query within step limit."}]}

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
    
    # --- ADD THIS DEBUG PRINT ---
    print(f"\n[DEBUG] Question: {test_case['question']}")
    print(f"[DEBUG] Agent's Raw Text Response: {actual_answer}")
    print(f"[DEBUG] Extracted SQL: '{generated_sql}'\n")
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
        # NEW REQUIREMENT: Ragas needs context about the database schema to evaluate SQL logic
        "reference_contexts": [["Chinook schema tables: Album, Artist, Customer, Employee, Genre, Invoice, InvoiceLine, MediaType, Playlist, PlaylistTrack, Track"]]  
    }
    dataset = Dataset.from_dict(data)

    # 4. Initialize Ragas Judge using the native LangChain Wrapper
    # FIXED: Added the correct IP base_url and removed the invalid provider argument
    ragas_llm = LangchainLLMWrapper(
        ChatOllama(
            model="nemotron-3-nano:4b", 
            base_url="http://192.168.1.157:11434",
            temperature=0
        )
    )

    # 5. Run Ragas Evaluation
    # FIXED: Removed the literal '...' placeholder and passed the LLM directly
    metric = SQLSemanticEquivalence(llm=ragas_llm)
    
    evaluation_result = evaluate(
        dataset=dataset, 
        metrics=[metric], 
        llm=ragas_llm 
    )
    
    # 6. Extract scores and assert
    scores = evaluation_result.to_pandas().iloc[0]
    
    print(f"\nGenerated SQL: {generated_sql}")
    
    # Note: The output key changes slightly when using the legacy metric
    sql_score = scores.get('llm_sql_equivalence', 0)
    print(f"SQL Score: {sql_score}")
    
    assert sql_score >= 0.8, f"SQL logic mismatch. Agent wrote: {generated_sql}"