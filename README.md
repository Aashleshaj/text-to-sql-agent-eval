## Project Info
> "I built a privacy-first, locally-hosted Text-to-SQL AI Agent that translates natural language questions into executable database queries. Beyond just building the agent, I engineered a complete testing infrastructure that generates synthetic test cases and uses an LLM-as-a-judge to evaluate the semantic accuracy of the generated SQL, all while tracing the agent's reasoning process for debugging."

---

## Core Tech Stack
* **LLM Engine:** Local Ollama running `nemotron-3-nano:4b` (ensures data privacy and zero API costs).
* **Agent Framework:** LangChain & DeepAgents (for tool calling, database connection, and persistent file-system memory).
* **Observability:** Arize Phoenix (OpenTelemetry tracing to monitor the agent's thought process).
* **Evaluation & Testing:** Pytest and Ragas (using `SQLSemanticEquivalence` to grade the agent).

---

## The 3 Main Pillars of Your Project

### 1. The Deep SQL Agent (`agent.py`)
This is the brain of the operation. It connects to a SQLite database (`chinook.db`) and uses LangChain's `SQLDatabaseToolkit`. 
* **Context Aware:** You configured it to sample 3 rows of data from the tables so the LLM understands the *format* of the data before it writes the SQL.
* **Deterministic:** You intentionally set the model's temperature to `0` to ensure stable, logical code generation.
* **Agentic Capabilities:** It uses tools to dynamically inspect the schema, write a query, execute it, and return a natural language answer to the user.

### 2. Synthetic Data Generation Pipeline (`generate_test_dataset.py`)
To test your agent, you needed data. Instead of writing tests by hand, you built a pipeline to generate them automatically.
* **Creative Prompting:** You spun up a *Generator LLM* with a high temperature (`0.8`) and prompted it to act as a QA Engineer, brainstorming unique, complex questions (JOINs, aggregations) based on the database schema.
* **Ground Truth Creation:** You passed these brainstormed questions to your actual Deep Agent to solve, saving the successful pairs of Questions and SQL into a `synthetic_tests.json` dataset.
* **Bulletproof Parsing:** You implemented strict Regex constraints to extract clean JSON payloads, even if the local model hallucinated markdown formatting around it.

### 3. Automated Evaluation Suite (`test_agent.py`)
This is the most impressive part of your project for an enterprise environment. You built a CI/CD-ready test suite using Pytest.
* **Semantic Equivalence vs. String Matching:** You recognized that comparing two SQL queries purely by text is flawed (e.g., `SELECT name FROM users` vs `SELECT users.name FROM users`). Instead, you integrated **Ragas** to evaluate *semantic equivalence*—using an LLM judge to verify if the logic of the generated query matches the expected query based on the database schema.
* **Safety Rails:** You implemented a `recursion_limit` of 12 to ensure that if the agent gets stuck in a loop trying to fix a bad query, it fails gracefully rather than freezing the test suite indefinitely.
* **Strategy Fallbacks:** You wrote custom parsing logic to catch edge cases where smaller models write SQL directly into the chat instead of using formal tool calls.
