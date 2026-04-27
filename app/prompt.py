REVIEW_PROMPT_TEMPLATE = """You are a senior staff-level software engineer and code reviewer.

TASK:
Analyze the given Git diff and perform a professional code review.

INPUT:
- The input is a Git diff containing code changes across files.

EVALUATION CRITERIA:
1. Code Quality (readability, maintainability, structure)
2. Bugs & Logical Errors
3. Security Issues (OWASP, secrets, unsafe patterns)
4. Performance Issues
5. Best Practices Violations

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "summary": "Short overall assessment (2-3 lines)",
  "score": <float between 0 and 10>,
  "issues": [
    {{
      "type": "bug | security | performance | style | best_practice",
      "severity": "low | medium | high | critical",
      "file": "filename",
      "line": <line number or null>,
      "title": "Short issue title",
      "description": "Clear explanation of the issue",
      "suggestion": "Concrete fix or improvement"
    }}
  ],
  "strengths": [
    "Optional: good practices observed"
  ]
}}

SCORING RULES:
- 9-10: Production-ready
- 7-8: Minor issues
- 5-6: Moderate issues
- 3-4: Significant problems
- 0-2: Critical issues

STRICT RULES:
- Output ONLY valid JSON
- No markdown,no explanations outside the JSON
- Do NOT hallucinate files
- If no issues found, return empty issues array
- Prefer top 5 most critical issues only

INPUT DIFF:
{diff}"""

MAX_DIFF_CHARS = 12_000

print("Prompt template and builder loaded")  # Debug statement

def perform_review(diff: str) -> dict:
    """Perform the code review by calling the LLM with the built prompt."""
    prompt = build_prompt(diff)
    # Here you would call your LLM API with the prompt and parse the response
    # For example:
    # response = llm_api_call(prompt)
    # return parse_llm_response(response)
    return {
        "summary": "This is a placeholder summary.",
        "score": 7.5,
        "issues": [
            {
                "type": "bug",
                "severity": "medium",
                "file": "example.py",
                "line": 42,
                "title": "Potential null pointer dereference",
                "description": "The variable 'data' could be null here, which may cause a crash.",
                "suggestion": "Add a null check before accessing 'data'."
            }
        ],
        "strengths": [
            "Good use of functions to modularize code."
        ]
    }

print`("Review function defined")  # Debug statement`
def build_prompt(diff: str) -> str:
    """Build the review prompt, truncating diff if necessary."""
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[... diff truncated for length ...]"
    return REVIEW_PROMPT_TEMPLATE.format(diff=diff)
