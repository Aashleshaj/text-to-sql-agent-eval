import argparse
from phoenix.otel import register
import os
import sys
import phoenix as px
from openinference.instrumentation.langchain import LangChainInstrumentor
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from rich.console import Console
from rich.panel import Panel
from langchain_ollama import ChatOllama

# Load environment variables
load_dotenv()

console = Console()

# --- Move tracing logic into a function ---
def init_tracing():
    import phoenix as px
    from phoenix.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    
    # Set host and port via environment variables to avoid deprecation warnings
    os.environ["PHOENIX_HOST"] = "127.0.0.1"
    os.environ["PHOENIX_PORT"] = "6007"
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://127.0.0.1:6007/v1/traces"
    
    # Launch app without arguments
    session = px.launch_app()
    
    tracer_provider = register(
        project_name="text-to-sql-agent",
        endpoint="http://127.0.0.1:6007/v1/traces"
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    return session


def create_sql_deep_agent():
    """Create and return a text-to-SQL Deep Agent"""

    # Get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Connect to Chinook database
    db_path = os.path.join(base_dir, "chinook.db")
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}", sample_rows_in_table_info=3)

    # Initialize Claude Sonnet 4.5 for toolkit initialization
    # model = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
    OLLAMA_MODEL = "nemotron-3-nano:4b"
    
    model = ChatOllama(
        model=OLLAMA_MODEL,  # Swap with your chosen local model
        temperature=0,             # Text-to-SQL requires 0 temperature for stability
        base_url="http://192.168.1.157:11434",
        num_ctx=32192,             # Ensure enough context for schema and query generation
        timeout=10,
        validate_model_on_init=True,
        logprobs=True,
        stream=True
    )

    # Create SQL toolkit and get tools
    toolkit = SQLDatabaseToolkit(db=db, llm=model)
    sql_tools = toolkit.get_tools()

    # Create the Deep Agent with all parameters
    agent = create_deep_agent(
        model=model,  # Claude Sonnet 4.5 with temperature=0
        memory=["./AGENTS.md"],  # Agent identity and general instructions
        skills=[
            "./skills/"
        ],  # Specialized workflows (query-writing, schema-exploration)
        tools=sql_tools,  # SQL database tools
        subagents=[],  # No subagents needed
        backend=FilesystemBackend(root_dir=base_dir, virtual_mode=False),  # Persistent file storage
    )

    return agent

# Create a dedicated entry point for your test harness in agent.py
def run_agent_test(question: str):
    """Programmatic invocation for the test framework."""
    agent = create_sql_deep_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result


def main():
    """Main entry point for the SQL Deep Agent CLI"""
    parser = argparse.ArgumentParser(
        description="Text-to-SQL Deep Agent powered by LangChain Deep Agents and Claude Sonnet 4.5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py "What are the top 5 best-selling artists?"
  python agent.py "Which employee generated the most revenue by country?"
  python agent.py "How many customers are from Canada?"
        """,
    )
    parser.add_argument(
        "question",
        type=str,
        help="Natural language question to answer using the Chinook database",
    )

    args = parser.parse_args()

    # Display the question
    console.print(
        Panel(f"[bold cyan]Question:[/bold cyan] {args.question}", border_style="cyan")
    )
    console.print()

    # Create the agent
    console.print("[dim]Creating SQL Deep Agent...[/dim]")
    agent = create_sql_deep_agent()

    # Invoke the agent
    console.print("[dim]Processing query...[/dim]\n")

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.question}]}
        )
        # Extract and display the final answer
        final_message = result["messages"][-1]
        answer = (
            final_message.content
            if hasattr(final_message, "content")
            else str(final_message)
        )

        console.print(
            Panel(f"[bold green]Answer:[/bold green]\n\n{answer}", border_style="green")
        )

    except Exception as e:
        console.print(
            Panel(f"[bold red]Error:[/bold red]\n\n{str(e)}", border_style="red")
        )
        # sys.exit(1)
    console.print("\n[dim]Agent execution complete. Phoenix server is running.[/dim]")
    console.print("[dim]View your traces at http://127.0.0.1:6007/[/dim]")
    console.print("[dim]Press Ctrl+C to exit.[/dim]")
    
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down...[/dim]")
    # -------------------------------------------



if __name__ == "__main__":
    main()
