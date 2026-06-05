# 🤖 Local Text-to-SQL Agent with Ragas Evaluation

An automated, locally-hosted AI agent that translates natural language questions into executable SQL queries, runs them against a database, and evaluates its own performance using a fully local Ragas + Pytest evaluation pipeline.

This project is built for **100% offline execution**, ensuring data privacy by running everything through local LLMs via Ollama, while maintaining enterprise-grade observability using Arize Phoenix.

## ✨ Features
* **Agentic SQL Generation:** Uses LangChain and Deep Agents to explore database schemas, write SQL, check syntax, and execute queries autonomously.
* **Fully Local Stack:** Powered entirely by local models (e.g., Qwen, DeepSeek, Llama) using Ollama. No OpenAI API keys required.
* **Automated AI Grading:** Evaluates the agent's generated SQL against a ground-truth dataset using Ragas (`LLMSQLEquivalence`), determining if the logical execution matches even if the syntax differs.
* **Resilient Parsing:** Includes custom regex fallbacks to gracefully extract SQL from smaller models (4B-8B parameters) that struggle with strict JSON tool-calling.
* **Live Observability:** Integrated with Arize Phoenix for real-time tracing of the agent's thought process, tool usage, and database interactions.
* **Automated Reporting:** Outputs all evaluation scores (Pass/Fail) into a clean `evaluation_results.csv` for data analysis.

---

## 🛠️ Prerequisites

1. **Python 3.10+**
2. **[Ollama](https://ollama.com/)** (Running locally on `http://localhost:11434` or a custom network IP)
3. **Hardware:** At least 8GB RAM (16GB+ recommended for running 7B-30B parameter models).

### Recommended Local Models
Pull these models via Ollama before running the project:
```bash
# Recommended for the Agent (Strong coding logic)
ollama run qwen3-coder:30b-a3b-q4_K_M 
# OR
ollama run deepseek-coder-v2:lite

# Recommended for the Ragas Evaluator Judge (Higher parameter for accurate grading)
ollama run qwen2.5-coder:32b
1.Clone the repository:
```
git clone https://github.com/Aashleshaj/text-to-sql-agent-eval.git
cd text-to-sql-agent-eval
```
2.Create a virtual environment:
```
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
3.Database Setup: Ensure the chinook.db SQLite database is located in the root directory.

🚀 Usage
1. Interactive CLI Mode
Test the agent manually by asking it a natural language question. The agent will explore the schema and output the answer.
```
python agent.py "Which album has the highest total unit price across its tracks?"
```
2. Automated Evaluation Pipeline (Pytest + Ragas)
Run the automated test suite to grade the agent against the synthetic_tests.json dataset.
```
pytest tests/test_agent.py -v -s --cache-clear
```
What happens during evaluation?
1.Pytest feeds a question to the agent.
2.The agent attempts to generate and execute the SQL.
3.A custom parser extracts the SQL safely.
4.Ragas compares the Agent's SQL to the Ground Truth SQL.
5.If the queries match exactly, it auto-passes. If they differ, the Ragas LLM Judge determines if they are semantically equivalent.
6.The score (0.0 or 1.0) is appended to evaluation_results.csv.

📁 Project Structure

├── agent.py                 # Core LangChain Agent logic & Phoenix tracing setup
├── tests/
│   ├── test_agent.py        # Pytest framework, Ragas evaluation, and fallback parsing
│   └── synthetic_tests.json # Ground truth dataset (Questions, Expected SQL, Answers)
├── chinook.db               # Sample SQLite database
├── evaluation_results.csv   # Auto-generated report of test scores
└── README.md

🔍 Observability (Arize Phoenix)
Every time you run the agent or the test suite, Arize Phoenix captures the exact steps the LLM takes.

Run a query or a test.

Open your browser and navigate to: http://localhost:6007

Click on the text-to-sql-agent project to view the spans, prompts, and database errors.

⚠️ Known Quirks & Workarounds
Ragas Collections Bug: Currently, newer Ragas collections metrics crash when paired with custom local LLM wrappers. This project intentionally utilizes the legacy from ragas.metrics import LLMSQLEquivalence to bypass this issue while maintaining accurate local scoring.

Agent Infinite Loops: Small local models (under 7B) may get caught in recursion loops if they make syntax errors. A hard cutoff of recursion_limit: 25 is enforced in the test suite to prevent hanging.

Windows File Lock: Pytest occasionally throws a background PermissionError on teardown due to Phoenix locking the local SQLite database. This does not affect test execution or results.
