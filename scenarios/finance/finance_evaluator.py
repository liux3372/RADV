"""Green agent (evaluator) for the finance agent scenario."""
import argparse
import os
import uvicorn
from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

# Import tool provider for communicating with participants
from tool_provider import ToolProvider

system_prompt = '''
You are the green agent, the evaluator for the finance agent benchmark.

Your task is to analyze an answer and:
1. Break it down into individual checks that can be automatically evaluated
2. Provide a performance score (0.0 to 1.0) that reflects the overall quality of the answer

You will receive a structured input:
- the URL of the finance agent participant
- the question to ask

### Evaluation Flow:

1. You will receive an assessment request containing:
   - The URL of the finance agent participant
   - The question to ask (in the config)
2. Send the question to the finance agent using the talk_to_agent tool
3. Wait for the agent's response. The response may contain:
   - The answer (often prefixed with "FINAL ANSWER:")
   - Sources (in JSON format)
   - Additional context or reasoning
4. Extract the main answer text from the response (the content after "FINAL ANSWER:" if present, or the main response text)
5. Use the question as context to understand what needs to be evaluated
6. Convert the answer into structured evaluation checks
7. Calculate a performance score (0.0 to 1.0) based on the answer's completeness, accuracy, clarity, and source quality

### Creating Evaluation Checks:

Each check must use one of these available operators:

- **edgar_research_operator**: This operator checks that the given criteria is present in the text as a complete, meaningful concept. It verifies factual content such as numerical figures (accepting rounded values), names, dates, and relationships between facts. Each check should represent a complete piece of information rather than fragmenting related facts into separate checks. The format, writing style, and length of the answer do not affect this check.

Guidelines for creating checks:

1. Break down complex answers into multiple simple checks only when the answer contains distinct, separable components.

2. Create checks that are specific, measurable, and objective.

3. Ensure each criteria is clear, precise, and unambiguous. Do not write full sentences for the criteria if not necessary. It can just be figures or phrases.

4. Convert the answer into a list of specific evaluation checks. Break down complex requirements into multiple simple checks where appropriate.

5. Return the result as a JSON array of objects with 'operator' and 'criteria' fields.

**Important**: The question and reasoning are provided ONLY for context to help you understand the answer. Your checks must ONLY evaluate the answer itself - not the question or reasoning. The checks will be applied exclusively to the answer text.

Create meaningful checks that capture substantive elements of the answer. Each check should:
- Evaluate a significant aspect of the answer
- Be clearly defined and testable
- Make sense as a standalone evaluation criterion

**Very important**:
- Do not split sentences or phrases into multiple checks if they are related to the same underlying concept.
- Some answers might be a bit verbose and contain more information than originally asked in the question. Do not make more checks than what is asked in the question. For example, if a question asks about a specific number, and the answer contains the number but also the calculation, do not make two checks: one for the number and one for the calculation. Make only one check for the number.
- Particularly make sure that the logical connections are kept within the same check and not split into multiple checks.

### Output Format:

After receiving the answer from the finance agent, analyze it and return a JSON object with two fields:

1. **checks**: An array of evaluation checks (same format as before)
2. **performance_score**: A numerical score from 0.0 to 1.0 (or 0 to 100) representing the overall quality of the answer

The format should be:

```json
{
  "checks": [
    {
      "operator": "edgar_research_operator",
      "criteria": "specific criteria to check"
    },
    {
      "operator": "edgar_research_operator",
      "criteria": "another specific criteria"
    }
  ],
  "performance_score": 0.85
}
```

### Performance Score Calculation:

Calculate the performance score based on:
- **Completeness**: Does the answer address all aspects of the question? (0-0.3 points)
- **Accuracy**: Are the facts correct and well-sourced? (0-0.3 points)
- **Clarity**: Is the answer clear and well-structured? (0-0.2 points)
- **Source Quality**: Are sources provided and relevant? (0-0.2 points)

The score should be a float between 0.0 and 1.0, where:
- 0.9-1.0: Excellent answer that fully addresses the question with accurate, well-sourced information
- 0.7-0.89: Good answer that addresses most aspects but may have minor gaps
- 0.5-0.69: Adequate answer that addresses the question but has notable gaps or issues
- 0.3-0.49: Poor answer that partially addresses the question but has significant issues
- 0.0-0.29: Very poor answer that fails to address the question adequately

**Important**: Always include a performance_score in your response. If you cannot determine a score, use 0.5 as a default, but try to provide a meaningful assessment based on the answer quality.

The JSON should be valid and parseable. Focus on creating checks that accurately capture the key information in the answer and providing a meaningful performance score.
'''

def main():
    parser = argparse.ArgumentParser(description="Run the A2A finance evaluator.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind the server")
    parser.add_argument("--port", type=int, default=9000, help="Port to bind the server")
    parser.add_argument("--card-url", type=str, help="External URL to provide in the agent card")
    args = parser.parse_args()

    tool_provider = ToolProvider()
    
    skill = AgentSkill(
        id='evaluate_finance_agent',
        name='Evaluate Finance Agent',
        description='Evaluate a finance agent on its ability to answer financial questions accurately with proper source citation. Returns evaluation checks and a performance score (0.0-1.0).',
        tags=['finance', 'evaluation'],
        examples=["""
        {
        "participants": {
            "finance_agent": "http://127.0.0.1:9099"
        },
        "config": {
            "question": "What was Apple's revenue in 2023?"
        }
        }
        """]
    )
    
    # Default to gemini-2.5-flash (newer model with better rate limits)
    # Can be overridden via GEMINI_MODEL env var
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    root_agent = Agent(
        name="finance_evaluator",
        model=model,
        description="Evaluate finance agents on their ability to answer financial questions accurately with proper source citation.",
        instruction=system_prompt,
        tools=[FunctionTool(func=tool_provider.talk_to_agent)],
        after_agent_callback=lambda callback_context: tool_provider.reset()
    )

    agent_card = AgentCard(
        name="finance_evaluator",
        description='Evaluate finance agents on their ability to answer financial questions accurately with proper source citation.',
        url=args.card_url or f'http://{args.host}:{args.port}/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    a2a_app = to_a2a(root_agent, agent_card=agent_card)
    uvicorn.run(a2a_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

