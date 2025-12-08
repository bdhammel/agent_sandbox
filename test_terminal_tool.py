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
    
    # Use agent.run() directly
    result = await agent.run("pw=4 whats the plan?")
    
    print()
    print("=== RESULT ===")
    print(f"Output type: {type(result.output)}")
    print(f"Output: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
