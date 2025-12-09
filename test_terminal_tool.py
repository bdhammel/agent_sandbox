"""Minimal test for terminal tool early exit."""

import asyncio
from dataclasses import dataclass

from agent import Agent


@dataclass
class Plan:
    steps: list[str]


# Create agent using our custom Agent class
agent = Agent(
    'openai:gpt-4o',
    instructions='Be Helpful',
)


@agent.tool_plain
def secret_plan(password: int) -> Plan:
    """Get the secret plan if the password is correct."""
    if password == 4:
        return Plan(steps=['collect underpants', '?', 'profit!'])
    return Plan(steps=['access denied'])


async def main():
    # Set terminal tools BEFORE running
    agent.terminal_tools = {"secret_plan"}
    
    print(f"Agent type: {type(agent)}")
    print(f"Terminal tools: {agent.terminal_tools}")
    print()
    
    # First run - should exit early on terminal tool
    result = await agent.run("pw=4 whats the plan?")
    
    print()
    print("=== FIRST RESULT (early exit) ===")
    print(f"Output type: {type(result.output)}")
    print(f"Output: {result.output}")
    print(f"Messages count: {len(result.all_messages())}")
    
    # Second run - continue the conversation
    print()
    print("=== CONTINUING CONVERSATION ===")
    result2 = await agent.run("whats step 2?", message_history=result.all_messages())
    
    print()
    print("=== SECOND RESULT ===")
    print(f"Output type: {type(result2.output)}")
    print(f"Output: {result2.output}")



if __name__ == "__main__":
    asyncio.run(main())
