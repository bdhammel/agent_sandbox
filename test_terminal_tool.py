"""Minimal test for terminal tool early exit."""

import asyncio
from dataclasses import dataclass

from agent import Agent


@dataclass
class Plan:
    steps: list[str]


@dataclass
class Deps:
    early_exit: bool = False


# Create agent using our custom Agent class
agent = Agent(
    'openai:gpt-4o',
    deps_type=Deps,
    instructions='Be Helpful',
)


@agent.tool
def secret_plan(ctx, password: int) -> Plan:
    """Get the secret plan if the password is correct."""
    if password == 4:
        ctx.deps.early_exit = True
        return Plan(steps=['collect underpants', '?', 'profit!'])
    return Plan(steps=['access denied'])


async def main():
    
    print(f"Agent type: {type(agent)}")
    print()
    deps = Deps()
    
    # First run - should exit early on terminal tool
    result = await agent.run("pw=4 whats the plan?", deps=deps)
    
    print()
    print("=== FIRST RESULT (early exit) ===")
    print(f"Output type: {type(result.output)}")
    print(f"Output: {result.output}")
    print(f"Messages count: {len(result.all_messages())}")
    print("Messages:")
    for msg in result.all_messages():
        print(f"- {msg}")
        print()
    
    # Second run - continue the conversation
    print()
    print("=== CONTINUING CONVERSATION ===")

    deps = Deps()
    result2 = await agent.run("whats step 2?", message_history=result.all_messages(), deps=deps)
    
    print()
    print("=== SECOND RESULT ===")
    print(f"Output type: {type(result2.output)}")
    print(f"Output: {result2.output}")



if __name__ == "__main__":
    asyncio.run(main())
